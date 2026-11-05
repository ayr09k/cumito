"""
"Modo solo" del celular: cada uno escucha SU música en su teléfono, aparte
de lo que suena en Discord.

La lista y el reproductor viven en el celular. El servidor solo:
  - deja lista cada canción (yt-dlp + la baja al disco, ver audio_cache) y le
    dice al celular de dónde descargarla (https://.../audio/<archivo>);
  - convierte lo que se busca o pega (texto, link, playlist, Spotify) en una
    lista de canciones;
  - lleva la cuenta de quién está escuchando qué ("Ana está escuchando...")
    para el inicio de los demás, y lo anota en las estadísticas (Wrapped);
  - arma las recomendaciones del inicio ("Para ti").
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import time

from . import audio_cache, spotify
from .extractor import _is_url, radio_sync, video_id
from .lanes import LANES

log = logging.getLogger("cumito.solo")

PAUSED_KEEP_S = 15 * 60     # alguien en pausa sigue apareciendo 15 min
RECS_TTL_S = 20 * 60


class Solo:
    def __init__(self, bot, on_change):
        self.bot = bot
        self.on_change = on_change
        self.listening: dict[str, dict] = {}
        self._recs: dict[tuple, tuple[float, list]] = {}

    # ---------- quién escucha qué ----------
    def listing(self) -> list[dict]:
        now = time.time()
        out = []
        for who, e in list(self.listening.items()):
            age = now - e["at"]
            if e["paused"]:
                alive = age < PAUSED_KEEP_S
            else:
                left = (e.get("duration") or 600) - e.get("elapsed", 0)
                alive = age < left + 90
            if not alive:
                self._close_play(self.listening.pop(who))
                continue
            out.append({k: e[k] for k in ("who", "title", "uploader", "art_url", "webpage_url", "duration",
                                          "elapsed", "paused", "at")})
        return out

    async def sweep(self):
        """Cada minuto: si alguien dejó de escuchar (se le acabó la canción
        con el celular apagado, etc.), que deje de salir en el inicio."""
        while True:
            await asyncio.sleep(60)
            n = len(self.listening)
            self.listing()
            if len(self.listening) != n:
                self.on_change()

    def _close_play(self, e):
        row = e.get("_row") if e else None
        if not row:
            return
        heard = e.get("elapsed", 0) + (0 if e["paused"] else time.time() - e["at"])
        if e.get("duration"):
            heard = min(heard, e["duration"])
        skipped = bool(e.get("duration")) and heard < e["duration"] - 15
        asyncio.create_task(self._db(self.bot.db.play_end, row, heard, skipped))

    async def _db(self, fn, *args):
        try:
            return await self.bot.db.run(fn, *args)
        except Exception:
            log.exception("Estadísticas del modo solo")

    async def status(self, who: str, d: dict):
        """El celular avisa qué está sonando en él (al empezar, pausar,
        adelantar, y cada tanto)."""
        t = d.get("track")
        prev = self.listening.get(who)
        if not isinstance(t, dict) or not t.get("webpage_url"):
            if prev:
                self._close_play(self.listening.pop(who))
                self.on_change()
            return
        e = {"who": who, "title": str(t.get("title") or "")[:200], "uploader": t.get("uploader"),
             "art_url": t.get("art_url"), "webpage_url": t.get("webpage_url"),
             "duration": t.get("duration") or 0, "elapsed": float(d.get("elapsed") or 0),
             "paused": bool(d.get("paused")), "at": time.time()}
        same = prev is not None and prev["webpage_url"] == e["webpage_url"] and not d.get("started")
        if same:
            e["_row"] = prev.get("_row")
        else:
            if prev:
                self._close_play(prev)
            e["_row"] = await self._db(self.bot.db.play_start, dict(e, who=who))
        self.listening[who] = e
        if not same or prev["paused"] != e["paused"] or abs(
                prev["elapsed"] + (0 if prev["paused"] else e["at"] - prev["at"]) - e["elapsed"]) > 5:
            self.on_change()

    # ---------- dejar una canción lista para el celular ----------
    async def get(self, url: str, title: str | None = None, pre: bool = False) -> dict:
        from .bot import extract
        if not url:
            return {"error": "Falta la canción"}
        if not audio_cache.publishes():
            return {"error": "El modo solo no está activado en el servidor"}
        path = audio_cache.ready_path({"webpage_url": url})
        info = {}
        if path is None:
            try:
                info = await extract(url, title_hint=title, urgent=not pre)
            except Exception as e:
                return {"error": f"No pude obtener esa canción: {str(e)[:120]}"}
            path = audio_cache.ready_path(info) or await audio_cache.fetch(info, urgent=not pre)
            if path is None:
                return {"error": "No pude bajar esa canción"}
            # el enlace con que se pidió también la encuentra la próxima vez
            if info.get("webpage_url") != url:
                audio_cache.alias(url, path)
        out = {"src": audio_cache.public_src(path)}
        for k in ("title", "uploader", "duration", "art_url", "webpage_url"):
            if info.get(k):
                out[k] = info[k]
        return out

    # ---------- lo que se busca o pega -> lista de canciones ----------
    async def add(self, query: str, as_playlist: bool = False) -> dict:
        from .bot import is_playlist, playlist_entries, search
        query = (query or "").strip()
        if not query:
            return {"tracks": []}
        try:
            if as_playlist or is_playlist(query):
                tracks, name = await playlist_entries(query)
                return {"tracks": tracks, "name": name}
            if spotify.is_spotify(query):
                sp = await LANES.light(spotify.resolve, query)
                return {"tracks": sp["tracks"][:1]}
            if _is_url(query):
                return {"tracks": [{"webpage_url": query, "title": "Cargando…"}]}
            res = await search(query, limit=1, kind="music")
            return {"tracks": res[:1]}
        except Exception as e:
            return {"tracks": [], "error": f"No pude abrir eso: {str(e)[:120]}"}

    # ---------- "Para ti" ----------
    async def recs(self, seeds: list) -> dict:
        seeds = [s for s in (seeds or []) if isinstance(s, str) and video_id(s)][:3]
        if not seeds:   # todavía no escuchó nada solo: lo último que sonó en el grupo
            seeds = [h.get("webpage_url") for h in list(self.bot.history)[:3] if video_id(h.get("webpage_url"))]
        if not seeds:
            return {"items": []}
        key = tuple(seeds)
        hit = self._recs.get(key)
        if hit and time.time() - hit[0] < RECS_TTL_S:
            return {"items": hit[1]}
        skip = tuple(v for v in (video_id(s) for s in seeds) if v)
        lists = []
        for s in seeds[:2]:
            try:
                lists.append(await LANES.light(radio_sync, s, 10, skip))
            except Exception as e:
                log.warning("Recomendaciones: %s", str(e)[:120])
        items, seen = [], set()
        for row in itertools.zip_longest(*lists):
            for t in row:
                if not t:
                    continue
                v = video_id(t.get("webpage_url"))
                if v and v not in seen:
                    seen.add(v)
                    items.append(t)
        items = items[:14]
        if items:
            self._recs[key] = (time.time(), items)
            if len(self._recs) > 50:
                self._recs.pop(next(iter(self._recs)))
        return {"items": items}
