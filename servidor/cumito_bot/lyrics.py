"""
Letras sincronizadas (para el modo karaoke) desde LRCLIB, una base de
letras libre y gratuita. Solo es una consulta por internet: corre en el
carril liviano y lo encontrado se guarda en la base de datos.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request

API = "https://lrclib.net/api"
UA = "Cumito (https://github.com/ayr09k/cumito)"

# lo que YouTube le pega al título y estorba para encontrar la letra
_NOISE = re.compile(
    r"\s*[\(\[\{][^\)\]\}]*\b(official|oficial|video|audio|lyric|letra|visualizer|visualiser|remaster|"
    r"hd|4k|mv|en vivo|live|explicit|clean|prod|remaster\w*|remasterizad\w*)\b[^\)\]\}]*[\)\]\}]",
    re.I)
_FEAT = re.compile(r"\s*[\(\[]?\s*(ft\.?|feat\.?|featuring|con)\s+[^\)\]\-]*[\)\]]?", re.I)


def clean_title(title: str) -> str:
    t = _NOISE.sub("", title or "")
    t = _FEAT.sub("", t)
    t = re.sub(r"\s*\|.*$", "", t)            # "Canción | Álbum"
    t = re.sub(r"\s+-\s+(topic)$", "", t, flags=re.I)
    return re.sub(r"\s{2,}", " ", t).strip(" -–—") or (title or "")


def clean_artist(artist: str | None) -> str | None:
    if not artist:
        return None
    a = str(artist).split(",")[0].split(" & ")[0]
    a = re.sub(r"\s*-\s*Topic$|VEVO$|\s+Official$|\s+Oficial$", "", a, flags=re.I)
    return a.strip() or None


def split_title(title: str, artist: str | None):
    """En YouTube muchas veces el título es "Artista - Canción" y el canal no
    es el artista. Si el título trae un guion, se usa eso."""
    t = clean_title(title)
    if " - " in t:
        a, s = t.split(" - ", 1)
        norm = lambda x: re.sub(r"\W", "", (x or "").lower())
        if not artist or norm(a) in norm(artist) or norm(artist) in norm(a) or not _looks_like_artist(artist):
            return s.strip(), a.strip()
    return t, clean_artist(artist)


def _looks_like_artist(name):
    n = (name or "").lower()
    return not any(x in n for x in ("records", "music", "tv", "channel", "oficial", "official", "label"))


def _get(path, params):
    url = f"{API}/{path}?{urllib.parse.urlencode({k: v for k, v in params.items() if v not in (None, '')})}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def _pack(row, title, artist):
    return {
        "found": True,
        "title": row.get("trackName") or title,
        "artist": row.get("artistName") or artist,
        "synced": row.get("syncedLyrics") or None,
        "plain": row.get("plainLyrics") or None,
        "instrumental": bool(row.get("instrumental")),
    }


def fetch(title: str, artist: str | None, duration: int | None) -> dict:
    """Busca la letra. Prefiere la versión sincronizada (con tiempos)."""
    song, art = split_title(title, artist)
    best = None
    if art:
        row = _get("get", {"track_name": song, "artist_name": art, "duration": duration or None})
        if row and (row.get("syncedLyrics") or row.get("plainLyrics") or row.get("instrumental")):
            if row.get("syncedLyrics") or row.get("instrumental"):
                return _pack(row, song, art)
            best = row
    # búsqueda más suelta: se elige la de duración más parecida, con tiempos
    for params in ({"track_name": song, "artist_name": art}, {"q": f"{song} {art or ''}".strip()}):
        if not params.get("artist_name") and "q" not in params:
            continue
        rows = _get("search", params) or []
        rows = [r for r in rows if r.get("syncedLyrics") or r.get("plainLyrics")]
        if not rows:
            continue
        def score(r):
            d = abs((r.get("duration") or 0) - (duration or r.get("duration") or 0))
            # primero que dure casi lo mismo (si no, suele ser otra canción); después, que tenga tiempos
            return (0 if d <= 8 else 1, 0 if r.get("syncedLyrics") else 1, d)
        rows.sort(key=score)
        top = rows[0]
        if duration and abs((top.get("duration") or 0) - duration) > 15 and best is None:
            continue   # muy distinta: seguramente es otra canción
        if top.get("syncedLyrics") or best is None:
            return _pack(top, song, art)
    if best:
        return _pack(best, song, art)
    return {"found": False, "title": song, "artist": art, "synced": None, "plain": None, "instrumental": False}
