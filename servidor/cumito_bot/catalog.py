"""
Catálogo para la app 3.0: buscar artistas, álbumes y playlists, el perfil de
un artista, y el inicio con mixes ("Para farmear aura", "Perreo en modo
avión"...) armados según el género de lo último que escuchaste.

Todo sale de YouTube Music (ytmusicapi). El género de cada artista se le
pregunta a MusicBrainz (gratis, sin clave) y se guarda para no repetir.
Las funciones *_sync corren en un hilo (LANES.light).
"""
from __future__ import annotations

import datetime
import hashlib
import json
import logging
import re
import time
import urllib.parse
import urllib.request

from .extractor import _artists, _ym_art, radio_sync, video_id, ytmusic

log = logging.getLogger("cumito.catalog")


def _big(thumbs, size=544):
    if not thumbs:
        return None
    url = thumbs[-1].get("url") if isinstance(thumbs[-1], dict) else None
    return re.sub(r"=w\d+-h\d+", f"=w{size}-h{size}", url) if url else None


def _song(r, art=None):
    vid = r.get("videoId")
    if not vid:
        return None
    return {"title": r.get("title") or "Sin título", "webpage_url": f"https://www.youtube.com/watch?v={vid}",
            "duration": r.get("duration_seconds") or _len(r.get("duration")), "uploader": _artists(r),
            "art_url": _ym_art(r.get("thumbnails") or [], vid) if r.get("thumbnails") else (art or _ym_art([], vid))}


def _len(v):
    try:
        n = 0
        for p in str(v).split(":"):
            n = n * 60 + int(p)
        return n or None
    except Exception:
        return None


def _playlist_url(browse_id):
    pid = browse_id[2:] if browse_id and browse_id.startswith("VL") else browse_id
    return f"https://www.youtube.com/playlist?list={pid}" if pid else None


def _row(r):
    """Un resultado de búsqueda de cualquier tipo -> lo que muestra la app."""
    t = r.get("resultType")
    if t in ("song", "video"):
        s = _song(r)
        if s:
            s["type"] = "song"
        return s
    if t == "artist" and r.get("browseId"):
        return {"type": "artist", "name": r.get("artist") or r.get("title"), "id": r["browseId"],
                "art_url": _big(r.get("thumbnails"), 400)}
    if t in ("album", "single", "ep") and r.get("browseId"):
        return {"type": "album", "title": r.get("title"), "artist": _artists(r), "year": r.get("year"),
                "id": r["browseId"], "art_url": _big(r.get("thumbnails"), 400)}
    if t == "playlist" and r.get("browseId"):
        return {"type": "playlist", "title": r.get("title"), "author": r.get("author"),
                "count": r.get("itemCount"), "url": _playlist_url(r["browseId"]), "art_url": _big(r.get("thumbnails"), 400)}
    return None


FILTERS = {"songs": "songs", "artists": "artists", "albums": "albums", "playlists": "playlists"}


def _videos(query: str, limit: int) -> list[dict]:
    """YouTube normal (no YouTube Music): podcasts, capítulos, videos de cualquier cosa."""
    from .extractor import search_sync as yt_search
    out = []
    for v in yt_search(query, limit, 0, "videos"):
        if v.get("webpage_url"):
            out.append({**v, "type": "song", "video": True})
    return out


def search_sync(query: str, kind: str, limit: int = 20) -> dict:
    """kind: all | songs | videos | artists | albums | playlists."""
    yt = ytmusic()
    if kind == "videos":
        return {"results": _videos(query, limit)}
    if kind == "all":
        # los videos de YouTube se buscan a la vez que lo de YouTube Music
        import concurrent.futures
        ex = concurrent.futures.ThreadPoolExecutor(max_workers=1)
        fut = ex.submit(_videos, query, 8)
        try:
            res = _search_all(yt, query)
        finally:
            ex.shutdown(wait=False)
        try:
            vids = fut.result(timeout=15)
        except Exception as e:
            log.warning("Videos de YouTube: %s", str(e)[:120])
            vids = []
        seen = {s.get("webpage_url") for s in res.get("songs") or []}
        res["videos"] = [v for v in vids if v["webpage_url"] not in seen][:6]
        return res
    if kind in FILTERS:
        rows = yt.search(query, filter=FILTERS[kind], limit=limit)
        if kind == "playlists" and len(rows) < 4:
            rows += yt.search(query, filter="community_playlists", limit=limit)
        return {"results": [x for x in (_row(r) for r in rows) if x][:limit]}
    return _search_all(yt, query)


def _search_all(yt, query: str) -> dict:
    rows = yt.search(query, limit=40)
    top, sections = None, {"songs": [], "artists": [], "albums": [], "playlists": []}
    for r in rows:
        x = _row(r)
        if not x:
            continue
        if top is None and (r.get("category") or "").lower() in ("top result", "mejor resultado", "resultado principal"):
            top = x
        key = {"song": "songs", "artist": "artists", "album": "albums", "playlist": "playlists"}[x["type"]]
        if len(sections[key]) < 8:
            sections[key].append(x)
    if top is None:
        top = (sections["artists"] or sections["songs"] or [None])[0]
    return {"top": top, **sections}


def artist_sync(browse_id: str) -> dict:
    yt = ytmusic()
    a = yt.get_artist(browse_id)
    songs = a.get("songs") or {}
    top = [s for s in (_song(r) for r in songs.get("results") or []) if s]
    def albums(key):
        return [{"type": "album", "title": r.get("title"), "year": r.get("year"), "id": r.get("browseId"),
                 "art_url": _big(r.get("thumbnails"), 400)} for r in (a.get(key) or {}).get("results") or [] if r.get("browseId")]
    return {"id": browse_id, "name": a.get("name"), "art_url": _big(a.get("thumbnails"), 900),
            "description": (a.get("description") or "")[:400], "top": top[:10],
            "all_songs": songs.get("browseId"), "albums": albums("albums"), "singles": albums("singles")}


def artist_songs_sync(browse_id: str, limit: int = 200) -> list[dict]:
    yt = ytmusic()
    pid = browse_id[2:] if browse_id.startswith("VL") else browse_id
    pl = yt.get_playlist(pid, limit=limit)
    return [s for s in (_song(r) for r in pl.get("tracks") or []) if s]


def album_sync(browse_id: str) -> dict:
    yt = ytmusic()
    a = yt.get_album(browse_id)
    art = _big(a.get("thumbnails"), 544)
    tracks = []
    for r in a.get("tracks") or []:
        s = _song(r, art)
        if s:
            s["art_url"] = art or s["art_url"]
            tracks.append(s)
    return {"id": browse_id, "title": a.get("title"), "artist": _artists(a), "year": a.get("year"),
            "art_url": art, "tracks": tracks}


# ---------------- géneros y títulos de los mixes ----------------
KNOWN = {
    "reggaeton": ["bad bunny", "daddy yankee", "feid", "karol g", "j balvin", "ozuna", "rauw alejandro", "myke towers",
                  "sech", "farruko", "nicky jam", "maluma", "wisin", "yandel", "arcangel", "young miko", "jhayco",
                  "manuel turizo", "don omar", "tego calderon", "zion", "lunay", "blessd", "ryan castro", "kapo", "dei v"],
    "trap": ["anuel aa", "eladio carrion", "duki", "bizarrap", "quevedo", "trueno", "ysy a", "khea", "mora", "cris mj"],
    "hiphop": ["drake", "kendrick lamar", "travis scott", "eminem", "j. cole", "kanye west", "21 savage", "future",
               "lil baby", "playboi carti", "tyler, the creator", "post malone", "a$ap rocky"],
    "pop": ["taylor swift", "dua lipa", "ariana grande", "olivia rodrigo", "shakira", "sabrina carpenter", "billie eilish",
            "the weeknd", "harry styles", "bruno mars", "ed sheeran", "selena gomez", "miley cyrus", "tini", "danna"],
    "bachata": ["romeo santos", "aventura", "prince royce", "juan luis guerra"],
    "salsa": ["marc anthony", "hector lavoe", "ruben blades", "celia cruz", "willie colon", "gilberto santa rosa", "grupo niche"],
    "regional": ["peso pluma", "fuerza regida", "natanael cano", "grupo frontera", "junior h", "ivan cornejo", "carin leon",
                 "gabito ballesteros", "tito double p", "eslabon armado", "xavi"],
    "rock": ["queen", "the beatles", "nirvana", "arctic monkeys", "linkin park", "soda stereo", "guns n' roses", "ac/dc", "coldplay"],
    "electronic": ["david guetta", "calvin harris", "avicii", "skrillex", "marshmello", "fred again..", "peggy gou", "martin garrix"],
    "rnb": ["sza", "frank ocean", "daniel caesar", "brent faiyaz", "h.e.r.", "summer walker", "usher", "beyonce"],
    "kpop": ["bts", "blackpink", "newjeans", "twice", "stray kids", "seventeen", "le sserafim", "aespa", "rosé", "jungkook"],
    "balada": ["luis miguel", "camilo sesto", "jose jose", "alejandro sanz", "juanes", "laura pausini", "ricardo arjona"],
}
TAGS = [
    ("reggaeton", ("reggaeton", "reggaetón", "urbano latino", "latin urban", "dembow", "perreo", "moombahton")),
    ("trap", ("latin trap", "trap latino", "trap", "drill")),
    ("regional", ("regional mexican", "regional mexicano", "corridos", "corrido", "banda", "norteño", "sierreño", "mariachi")),
    ("bachata", ("bachata",)),
    ("salsa", ("salsa", "merengue", "timba", "son cubano")),
    ("kpop", ("k-pop", "kpop", "korean")),
    ("hiphop", ("hip hop", "hip-hop", "rap", "boom bap")),
    ("rnb", ("r&b", "rnb", "soul", "neo soul", "contemporary r&b")),
    ("electronic", ("electronic", "edm", "house", "techno", "dubstep", "trance", "drum and bass", "electro")),
    ("rock", ("rock", "punk", "grunge", "metal", "indie rock", "alternative")),
    ("balada", ("ballad", "balada", "bolero", "latin ballad")),
    ("pop", ("pop", "latin pop", "dance-pop", "synthpop", "electropop")),
]
NAMES = {"reggaeton": "Reggaetón", "trap": "Trap", "hiphop": "Hip hop", "pop": "Pop", "bachata": "Bachata", "salsa": "Salsa",
         "regional": "Regional mexicano", "rock": "Rock", "electronic": "Electrónica", "rnb": "R&B", "kpop": "K-pop",
         "balada": "Baladas", "otros": "Tu mezcla"}
TITLES = {
    "reggaeton": ["Perreo en modo avión", "Para farmear aura", "Hasta abajo y sin frenos", "Perreo con estudio universitario",
                  "Modo discoteca desde la cama", "Pa' olvidar a tu ex en 3 minutos", "Dembow pa' la ducha"],
    "trap": ["Llorar pero con flow", "Para farmear aura", "Flow de villano", "Trap pa' manejar de noche",
             "Corazón roto, cadena puesta", "Ansiedad con buen beat"],
    "hiphop": ["Barras pa' la ducha", "Modo protagonista", "Rap con cara seria", "Caminar como si fuera un videoclip",
               "Confianza prestada"],
    "pop": ["Main character energy", "Cantar en el carro a todo pulmón", "Fingir un videoclip en el bus",
            "Pop pa' ignorar mensajes", "Delulu pero feliz"],
    "bachata": ["Bachata para extrañar con dignidad", "Amargue elegante", "Mensajes que no mandé",
                "Despecho con buena postura"],
    "salsa": ["Salsa pa' que te saquen a bailar", "Sabor de abuela con flow", "Fiesta en la sala de la tía",
              "Salsa pa' limpiar la casa"],
    "regional": ["Bélico pero tierno", "Corridos pa' sentirte jefe", "Tumbado y con sentimiento", "Pa' la carne asada"],
    "rock": ["Guitarrazos pa' sentirte inmortal", "Headbang en la oficina", "Rock pa' ganarle al tráfico",
             "Energía de concierto en tu cuarto"],
    "electronic": ["Rave en tu cuarto", "BPM pa' no dormir", "Bajos que se sienten en el pecho", "After en modo solo"],
    "rnb": ["R&B pa' escribir a las 2 a. m.", "Suave pero peligroso", "Vibras de luces bajas", "Romance con mala señal"],
    "kpop": ["Coreografía mental", "Stan sin descanso", "Brillo de idol", "Energía de comeback"],
    "balada": ["Llorar en HD", "Baladas pa' ver la lluvia", "Karaoke del despecho", "Sentimientos en alta definición"],
    "otros": ["Para farmear aura", "Banda sonora de tu villano", "Lo que sonaría en tu película", "Puro vicio auditivo",
              "Modo personaje principal"],
}
UA = "Cumito/3.0 (+https://github.com/ayr09k/cumito)"
_mb_last = [0.0]
# géneros ya averiguados (se guardan en un archivo al lado del servidor)
from pathlib import Path
import threading
_GPATH = Path(__file__).resolve().parent.parent / "generos.json"
_G: dict | None = None
_GL = threading.Lock()


def _genres() -> dict:
    global _G
    if _G is None:
        try:
            _G = json.loads(_GPATH.read_text(encoding="utf-8"))
        except Exception:
            _G = {}
    return _G


def _first_artist(t):
    return (str(t.get("uploader") or "").split(",")[0].split(" & ")[0].split(" x ")[0]).strip()


def genre_of(artist: str, store=None) -> str:
    """El grupo de género de un artista (reggaeton, pop, ...)."""
    a = artist.lower().strip()
    if not a:
        return "otros"
    for g, names in KNOWN.items():
        if a in names:
            return g
    with _GL:
        hit = _genres().get(a)
    if hit and time.time() - hit[1] < 90 * 86400:
        return hit[0]
    g = "otros"
    try:
        wait = 1.1 - (time.time() - _mb_last[0])
        if wait > 0:
            time.sleep(wait)
        _mb_last[0] = time.time()
        url = "https://musicbrainz.org/ws/2/artist/?fmt=json&limit=1&query=" + urllib.parse.quote(f'artist:"{artist}"')
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode())
        arts = data.get("artists") or []
        tags = []
        if arts:
            tags = sorted((arts[0].get("tags") or []), key=lambda x: -int(x.get("count") or 0))
        names = " | ".join(t.get("name", "").lower() for t in tags[:8])
        for gname, keys in TAGS:
            if any(k in names for k in keys):
                g = gname
                break
    except Exception as e:
        log.info("MusicBrainz no respondió para %s: %s", artist, str(e)[:80])
        return "otros"
    with _GL:
        _genres()[a] = [g, time.time()]
        try:
            _GPATH.write_text(json.dumps(_genres(), ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return g


def _pick(pool, salt):
    day = datetime.date.today().isoformat()
    i = int(hashlib.sha1((salt + day).encode()).hexdigest(), 16) % len(pool)
    return pool[i]


def home_sync(seeds: list, store=None) -> dict:
    """seeds: las últimas canciones (no de radio) del modo solo, la más nueva primero."""
    seeds = [s for s in seeds if isinstance(s, dict) and video_id(s.get("webpage_url"))][:5]
    if not seeds:
        return {"mixes": [], "radios": [], "playlists": []}
    groups: dict[str, list] = {}
    for s in seeds:
        groups.setdefault(genre_of(_first_artist(s), store), []).append(s)
    order = sorted(groups.items(), key=lambda kv: -len(kv[1]))
    mixes, used_titles, seen = [], set(), set()
    for g, items in order[:3]:
        seed = items[0]
        try:
            tracks = radio_sync(seed["webpage_url"], 25, tuple(seen))
        except Exception as e:
            log.info("Mix sin radio (%s): %s", seed.get("title"), str(e)[:80])
            continue
        tracks = [dict(seed, radio=False)] + [t for t in tracks if t.get("webpage_url") != seed["webpage_url"]]
        pool = [t for t in TITLES.get(g, TITLES["otros"]) if t not in used_titles] or TITLES["otros"]
        title = _pick(pool, g + seed["webpage_url"])
        used_titles.add(title)
        mixes.append({"title": title, "genre": NAMES.get(g, "Tu mezcla"), "seed": seed.get("title"),
                      "art_url": tracks[0].get("art_url"), "tracks": tracks[:26]})
        seen.update(video_id(t["webpage_url"]) for t in tracks)
    # radios de tus artistas (con su foto)
    radios, names = [], []
    for s in seeds:
        a = _first_artist(s)
        if a and a.lower() not in [n.lower() for n in names]:
            names.append(a)
    yt = ytmusic()
    for a in names[:4]:
        r = {"name": a, "seed": s_by_artist(seeds, a), "art_url": None, "id": None}
        try:
            hit = yt.search(a, filter="artists", limit=1)
            if hit:
                r["art_url"] = _big(hit[0].get("thumbnails"), 300)
                r["id"] = hit[0].get("browseId")
        except Exception:
            pass
        radios.append(r)
    # playlists que te van
    playlists = []
    if names:
        try:
            rows = yt.search(names[0], filter="playlists", limit=6) or yt.search(names[0], filter="community_playlists", limit=6)
            playlists = [x for x in (_row(r) for r in rows) if x and x["type"] == "playlist"][:6]
        except Exception as e:
            log.info("Sin playlists recomendadas: %s", str(e)[:80])
    return {"mixes": mixes, "radios": radios, "playlists": playlists}


def s_by_artist(seeds, artist):
    for s in seeds:
        if _first_artist(s).lower() == artist.lower():
            return {k: s.get(k) for k in ("title", "uploader", "webpage_url", "art_url", "duration")}
    return None
