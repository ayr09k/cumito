"""
La base de datos de Cumito (SQLite, un solo archivo: cumito.db al lado de
run.py). Vive solo en la VM, nunca va al repositorio.

Guarda:
  - plays:        cada canción que sonó (para las estadísticas / el Wrapped)
  - albums:       los Discos que arma el grupo (nombre, color, portada)
  - album_tracks: las canciones de cada Disco
  - lyrics:       letras ya buscadas (para no volver a pedirlas)
  - kv:           memoria chica para lo demás (p. ej. enlaces de Spotify)
  - favs:         las favoritas de cada uno (el corazón de la app del celular)

Todo se hace en UN hilo aparte: el loop principal (el que atiende a las
apps y al bot) nunca se queda esperando al disco.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import io
import json
import logging
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

log = logging.getLogger("cumito.db")

HERE = Path(__file__).resolve().parent.parent
DB_PATH = HERE / "cumito.db"
COVERS_DIR = HERE / "portadas"
COVER_PX = 512
COVER_MAX_BYTES = 6 * 1024 * 1024   # lo que se acepta subir (antes de achicarla)
ALBUM_MAX_TRACKS = 500
ALBUM_NAME_MAX = 40

SCHEMA = """
CREATE TABLE IF NOT EXISTS plays(
    id INTEGER PRIMARY KEY, ts REAL NOT NULL, who TEXT, title TEXT, uploader TEXT,
    url TEXT, duration INTEGER, art TEXT, listened INTEGER DEFAULT 0, skipped INTEGER DEFAULT 0);
CREATE INDEX IF NOT EXISTS plays_ts ON plays(ts);
CREATE TABLE IF NOT EXISTS albums(
    id INTEGER PRIMARY KEY, name TEXT NOT NULL, owner TEXT, color TEXT, cover TEXT,
    note TEXT, created REAL, updated REAL);
CREATE TABLE IF NOT EXISTS album_tracks(
    id INTEGER PRIMARY KEY, album_id INTEGER NOT NULL, pos INTEGER NOT NULL, title TEXT, url TEXT,
    duration INTEGER, uploader TEXT, art TEXT, added_by TEXT, added_at REAL);
CREATE INDEX IF NOT EXISTS album_tracks_album ON album_tracks(album_id, pos);
CREATE TABLE IF NOT EXISTS lyrics(key TEXT PRIMARY KEY, data TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS kv(key TEXT PRIMARY KEY, value TEXT, ts REAL);
CREATE TABLE IF NOT EXISTS favs(
    who TEXT NOT NULL, url TEXT NOT NULL, title TEXT, uploader TEXT, duration INTEGER, art TEXT, ts REAL,
    PRIMARY KEY(who, url));
"""

PERIODS = {"week": 7 * 86400, "month": 30 * 86400, "year": 365 * 86400, "all": None}


def _clean_artist(name):
    """'Bad Bunny, Bomba Estéreo' -> 'Bad Bunny'; 'Bad Bunny - Topic' -> 'Bad Bunny'"""
    if not name:
        return None
    a = str(name).split(",")[0].split(" & ")[0]
    for tail in (" - Topic", "VEVO", " Official"):
        if a.endswith(tail):
            a = a[: -len(tail)]
    return a.strip() or None


def process_cover(b64: str) -> bytes:
    """La imagen que mandó alguien -> JPEG cuadrado de 512 px (recortada al
    centro). Si Pillow no está, se guarda tal cual (si es JPEG/PNG chica)."""
    raw = base64.b64decode(b64.split(",", 1)[-1], validate=False)
    if len(raw) > COVER_MAX_BYTES:
        raise ValueError("La imagen es muy pesada (máx. 6 MB)")
    try:
        from PIL import Image, ImageOps
    except ImportError:
        if raw[:3] == b"\xff\xd8\xff" or raw[:8] == b"\x89PNG\r\n\x1a\n":
            if len(raw) <= 1_500_000:
                return raw
        raise ValueError("No pude leer esa imagen")
    try:
        im = Image.open(io.BytesIO(raw))
        im = ImageOps.exif_transpose(im)
        im.draft("RGB", (COVER_PX * 2, COVER_PX * 2))
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, (16, 14, 22))
            bg.paste(im, mask=im.split()[-1])
            im = bg
        else:
            im = im.convert("RGB")
        im = ImageOps.fit(im, (COVER_PX, COVER_PX), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, "JPEG", quality=86, optimize=True, progressive=True)
        return out.getvalue()
    except Exception as e:
        raise ValueError("No pude leer esa imagen") from e


class Store:
    def __init__(self, path: Path = DB_PATH, covers: Path = COVERS_DIR):
        self.path = Path(path)
        self.covers = Path(covers)
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="cumito-db")
        self._con: sqlite3.Connection | None = None
        self.albums_rev = int(time.time()) % 100000   # cambia cada vez que se toca un Disco

    # ---------- infraestructura ----------
    def _db(self) -> sqlite3.Connection:
        if self._con is None:
            self._con = sqlite3.connect(str(self.path), check_same_thread=False)
            self._con.row_factory = sqlite3.Row
            self._con.execute("PRAGMA journal_mode=WAL")
            self._con.execute("PRAGMA synchronous=NORMAL")
            self._con.executescript(SCHEMA)
            self._con.commit()
        return self._con

    async def run(self, fn, *args):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self._pool, fn, *args)

    def close(self):
        def _c():
            if self._con is not None:
                self._con.close()
                self._con = None
        try:
            self._pool.submit(_c).result(timeout=3)
        except Exception:
            pass
        self._pool.shutdown(wait=False)

    # ---------- reproducciones / estadísticas ----------
    def play_start(self, track: dict) -> int:
        con = self._db()
        cur = con.execute(
            "INSERT INTO plays(ts, who, title, uploader, url, duration, art) VALUES(?,?,?,?,?,?,?)",
            (time.time(), track.get("who"), track.get("title"), track.get("uploader"),
             track.get("webpage_url"), track.get("duration"), track.get("art_url")))
        con.commit()
        return cur.lastrowid

    def play_end(self, row_id: int, listened: float, skipped: bool, track: dict | None = None):
        con = self._db()
        sets, vals = ["listened=?", "skipped=?"], [int(listened), 1 if skipped else 0]
        if track:  # lo que se supo recién al prepararla (título/portada reales)
            for col, key in (("title", "title"), ("uploader", "uploader"), ("url", "webpage_url"),
                             ("art", "art_url"), ("duration", "duration")):
                if track.get(key):
                    sets.append(f"{col}=?")
                    vals.append(track.get(key))
        con.execute(f"UPDATE plays SET {', '.join(sets)} WHERE id=?", (*vals, row_id))
        con.commit()

    def stats(self, period: str = "month", who: str | None = None) -> dict:
        con = self._db()
        span = PERIODS.get(period, PERIODS["month"])
        since = time.time() - span if span else 0
        q = "SELECT ts, who, title, uploader, url, duration, art, listened, skipped FROM plays WHERE ts>=?"
        args: list = [since]
        if who:
            q += " AND who=?"
            args.append(who)
        rows = con.execute(q, args).fetchall()
        songs, artists, people = {}, {}, {}
        hours = [0] * 24
        days = set()
        listened = 0
        for r in rows:
            listened += r["listened"] or 0
            key = r["url"] or r["title"]
            s = songs.setdefault(key, {"title": r["title"], "uploader": r["uploader"], "webpage_url": r["url"],
                                       "art_url": r["art"], "duration": r["duration"], "plays": 0})
            s["plays"] += 1
            if r["art"]:
                s["art_url"] = r["art"]
            a = _clean_artist(r["uploader"])
            if a:
                ar = artists.setdefault(a, {"name": a, "plays": 0, "art_url": r["art"]})
                ar["plays"] += 1
            if r["who"]:
                p = people.setdefault(r["who"], {"name": r["who"], "plays": 0, "listened": 0})
                p["plays"] += 1
                p["listened"] += r["listened"] or 0
            lt = time.localtime(r["ts"])
            hours[lt.tm_hour] += 1
            days.add((lt.tm_year, lt.tm_yday))
        top = lambda d, n: sorted(d.values(), key=lambda x: -x["plays"])[:n]
        first = con.execute("SELECT MIN(ts) FROM plays").fetchone()[0]
        return {
            "period": period if period in PERIODS else "month",
            "who": who,
            "plays": len(rows),
            "minutes": round(listened / 60),
            "days": len(days),
            "skipped": sum(1 for r in rows if r["skipped"]),
            "top_songs": top(songs, 10),
            "top_artists": top(artists, 8),
            "top_people": top(people, 8),
            "hours": hours,
            "first_ts": first,
        }

    # ---------- Discos ----------
    def _album_row(self, con, r) -> dict:
        n, total = con.execute(
            "SELECT COUNT(*), COALESCE(SUM(duration),0) FROM album_tracks WHERE album_id=?", (r["id"],)).fetchone()
        arts = [x[0] for x in con.execute(
            "SELECT art FROM album_tracks WHERE album_id=? AND art IS NOT NULL ORDER BY pos LIMIT 4",
            (r["id"],)).fetchall()]
        return {"id": r["id"], "name": r["name"], "owner": r["owner"], "color": r["color"],
                "cover": r["cover"], "note": r["note"], "count": n, "duration": total,
                "arts": arts, "created": r["created"], "updated": r["updated"]}

    def albums(self) -> list[dict]:
        con = self._db()
        rows = con.execute("SELECT * FROM albums ORDER BY updated DESC").fetchall()
        return [self._album_row(con, r) for r in rows]

    def album(self, album_id: int) -> dict | None:
        con = self._db()
        r = con.execute("SELECT * FROM albums WHERE id=?", (album_id,)).fetchone()
        if r is None:
            return None
        out = self._album_row(con, r)
        out["tracks"] = [
            {"id": t["id"], "title": t["title"], "webpage_url": t["url"], "duration": t["duration"],
             "uploader": t["uploader"], "art_url": t["art"], "added_by": t["added_by"], "added_at": t["added_at"]}
            for t in con.execute("SELECT * FROM album_tracks WHERE album_id=? ORDER BY pos", (album_id,))
        ]
        return out

    def _save_cover(self, cover_b64: str) -> str:
        data = process_cover(cover_b64)
        h = hashlib.sha1(data).hexdigest()[:20]
        self.covers.mkdir(parents=True, exist_ok=True)
        p = self.covers / f"{h}.jpg"
        if not p.exists():
            tmp = p.with_suffix(".tmp")
            tmp.write_bytes(data)
            tmp.replace(p)
        return h

    def cover(self, h: str) -> str | None:
        if not h or not all(c in "0123456789abcdef" for c in h):
            return None
        p = self.covers / f"{h}.jpg"
        try:
            return base64.b64encode(p.read_bytes()).decode("ascii")
        except OSError:
            return None

    def album_create(self, name: str, owner: str | None, color: str | None = None,
                     cover_b64: str | None = None, note: str | None = None) -> dict:
        name = (name or "").strip()[:ALBUM_NAME_MAX] or "Disco sin nombre"
        cover = self._save_cover(cover_b64) if cover_b64 else None
        con = self._db()
        now = time.time()
        cur = con.execute("INSERT INTO albums(name, owner, color, cover, note, created, updated) "
                          "VALUES(?,?,?,?,?,?,?)",
                          (name, owner, _color(color), cover, (note or "")[:200] or None, now, now))
        con.commit()
        self.albums_rev += 1
        return self.album(cur.lastrowid)

    def album_update(self, album_id: int, name=None, color=None, cover_b64=None, remove_cover=False,
                     note=None) -> dict | None:
        con = self._db()
        if con.execute("SELECT 1 FROM albums WHERE id=?", (album_id,)).fetchone() is None:
            return None
        sets, vals = ["updated=?"], [time.time()]
        if name is not None:
            sets.append("name=?")
            vals.append(name.strip()[:ALBUM_NAME_MAX] or "Disco sin nombre")
        if color is not None:
            sets.append("color=?")
            vals.append(_color(color))
        if note is not None:
            sets.append("note=?")
            vals.append(note[:200] or None)
        if cover_b64:
            sets.append("cover=?")
            vals.append(self._save_cover(cover_b64))
        elif remove_cover:
            sets.append("cover=NULL")
        con.execute(f"UPDATE albums SET {', '.join(sets)} WHERE id=?", (*vals, album_id))
        con.commit()
        self.albums_rev += 1
        return self.album(album_id)

    def album_delete(self, album_id: int) -> str | None:
        con = self._db()
        r = con.execute("SELECT name FROM albums WHERE id=?", (album_id,)).fetchone()
        if r is None:
            return None
        con.execute("DELETE FROM album_tracks WHERE album_id=?", (album_id,))
        con.execute("DELETE FROM albums WHERE id=?", (album_id,))
        con.commit()
        self.albums_rev += 1
        return r["name"]

    def album_add(self, album_id: int, tracks: list[dict], who: str | None) -> int:
        """Agrega canciones al final (sin repetir la misma). Devuelve cuántas."""
        con = self._db()
        if con.execute("SELECT 1 FROM albums WHERE id=?", (album_id,)).fetchone() is None:
            return 0
        have = {x[0] for x in con.execute("SELECT url FROM album_tracks WHERE album_id=?", (album_id,))}
        pos = con.execute("SELECT COALESCE(MAX(pos), -1) FROM album_tracks WHERE album_id=?",
                          (album_id,)).fetchone()[0]
        n_now = len(have)
        added = 0
        for t in tracks:
            url = t.get("webpage_url")
            if not url or url in have or n_now + added >= ALBUM_MAX_TRACKS:
                continue
            have.add(url)
            pos += 1
            added += 1
            con.execute("INSERT INTO album_tracks(album_id, pos, title, url, duration, uploader, art, added_by, "
                        "added_at) VALUES(?,?,?,?,?,?,?,?,?)",
                        (album_id, pos, (t.get("title") or "Sin título")[:200], url, t.get("duration"),
                         t.get("uploader"), t.get("art_url"), who, time.time()))
        if added:
            con.execute("UPDATE albums SET updated=? WHERE id=?", (time.time(), album_id))
            self.albums_rev += 1
        con.commit()
        return added

    def album_remove(self, album_id: int, track_id: int) -> bool:
        con = self._db()
        cur = con.execute("DELETE FROM album_tracks WHERE album_id=? AND id=?", (album_id, track_id))
        con.commit()
        if cur.rowcount:
            self._renumber(con, album_id)
            self.albums_rev += 1
        return bool(cur.rowcount)

    def album_move(self, album_id: int, track_id: int, to: int) -> bool:
        con = self._db()
        ids = [x[0] for x in con.execute("SELECT id FROM album_tracks WHERE album_id=? ORDER BY pos", (album_id,))]
        if track_id not in ids:
            return False
        ids.remove(track_id)
        ids.insert(max(0, min(len(ids), int(to))), track_id)
        con.executemany("UPDATE album_tracks SET pos=? WHERE id=?", [(i, t) for i, t in enumerate(ids)])
        con.execute("UPDATE albums SET updated=? WHERE id=?", (time.time(), album_id))
        con.commit()
        self.albums_rev += 1
        return True

    @staticmethod
    def _renumber(con, album_id):
        ids = [x[0] for x in con.execute("SELECT id FROM album_tracks WHERE album_id=? ORDER BY pos", (album_id,))]
        con.executemany("UPDATE album_tracks SET pos=? WHERE id=?", [(i, t) for i, t in enumerate(ids)])
        con.commit()

    # ---------- favoritas de cada uno ----------
    FAVS_MAX = 2000

    def favs(self, who: str) -> list[dict]:
        rows = self._db().execute("SELECT * FROM favs WHERE who=? ORDER BY ts DESC", (who,)).fetchall()
        return [{"title": r["title"], "webpage_url": r["url"], "uploader": r["uploader"],
                 "duration": r["duration"], "art_url": r["art"], "ts": r["ts"]} for r in rows]

    def fav_set(self, who: str, track: dict, on: bool) -> bool:
        url = str((track or {}).get("webpage_url") or "")
        if not who or not url.startswith("http"):
            return False
        con = self._db()
        if on:
            n = con.execute("SELECT COUNT(*) FROM favs WHERE who=?", (who,)).fetchone()[0]
            if n >= self.FAVS_MAX:
                return False
            con.execute("INSERT OR REPLACE INTO favs(who, url, title, uploader, duration, art, ts) VALUES(?,?,?,?,?,?,?)",
                        (who, url, (track.get("title") or "Sin título")[:200], track.get("uploader"),
                         track.get("duration"), track.get("art_url"), time.time()))
        else:
            con.execute("DELETE FROM favs WHERE who=? AND url=?", (who, url))
        con.commit()
        return True

    # ---------- letras y memoria chica ----------
    def lyrics_get(self, key: str, max_age: float | None = None) -> dict | None:
        r = self._db().execute("SELECT data, ts FROM lyrics WHERE key=?", (key,)).fetchone()
        if r is None or (max_age and time.time() - r["ts"] > max_age):
            return None
        try:
            return json.loads(r["data"])
        except Exception:
            return None

    def lyrics_put(self, key: str, data: dict):
        con = self._db()
        con.execute("INSERT OR REPLACE INTO lyrics(key, data, ts) VALUES(?,?,?)",
                    (key, json.dumps(data, ensure_ascii=False), time.time()))
        con.commit()

    def kv_get(self, key: str, max_age: float | None = None):
        r = self._db().execute("SELECT value, ts FROM kv WHERE key=?", (key,)).fetchone()
        if r is None or (max_age and time.time() - r["ts"] > max_age):
            return None
        try:
            return json.loads(r["value"])
        except Exception:
            return None

    def kv_put(self, key: str, value):
        con = self._db()
        con.execute("INSERT OR REPLACE INTO kv(key, value, ts) VALUES(?,?,?)",
                    (key, json.dumps(value, ensure_ascii=False), time.time()))
        con.commit()

    def size(self) -> int:
        total = 0
        for p in (self.path, self.path.with_name(self.path.name + "-wal")):
            try:
                total += p.stat().st_size
            except OSError:
                pass
        try:
            total += sum(p.stat().st_size for p in self.covers.glob("*.jpg"))
        except OSError:
            pass
        return total


def _color(c):
    c = (c or "").strip()
    if len(c) == 7 and c.startswith("#") and all(x in "0123456789abcdefABCDEF" for x in c[1:]):
        return c.upper()
    return None
