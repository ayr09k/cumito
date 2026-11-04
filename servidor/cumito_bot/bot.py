"""
BotCore: el bot de Discord de Cumito (extracción con yt-dlp, FFmpeg vía
imageio-ffmpeg). Tanto los comandos de barra en Discord como las apps del
grupo (vía relay) disparan las mismas acciones y el mismo aviso de "esto
cambió" hacia quien esté escuchando.
"""
from __future__ import annotations

import asyncio
import json
import re
import logging
import os
import shlex
import shutil
import sys
import sysconfig
import time
from collections import deque
from pathlib import Path

import discord
import yt_dlp
from discord import app_commands

from .extractor import (  # noqa: F401  (lo usan el bot y las búsquedas)
    COOKIES_PATH, SEARCH_YTDL_OPTS, YTDL_OPTS, _best_thumb, _extract_one, _extract_sync, _is_url, _opts,
    _worker_init, _youtube_title,
)

log = logging.getLogger("cumito.bot")

def ffmpeg_path() -> str:
    p = shutil.which("ffmpeg")
    if p:
        return p
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


FFMPEG_BEFORE = "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5 -loglevel error"
FFMPEG_OPTIONS = "-vn"
# Lo que diga FFmpeg (el que reproduce el audio) se guarda aquí, para poder
# ver por qué una canción no suena.
FFMPEG_LOG_PATH = Path(__file__).resolve().parent.parent / "ffmpeg.log"


def _ffmpeg_before(headers: dict | None) -> str:
    """YouTube solo entrega el audio si FFmpeg lo pide con los mismos datos
    de "navegador" (User-Agent, cookies...) con los que yt-dlp encontró la
    canción. Sin esto, la canción "suena" en la app pero sale en silencio."""
    if not headers:
        return FFMPEG_BEFORE
    raw = "".join(f"{k}: {v}\r\n" for k, v in headers.items() if v)
    return f"{FFMPEG_BEFORE} -headers {shlex.quote(raw)}"


def _ffmpeg_stderr():
    try:
        if FFMPEG_LOG_PATH.exists() and FFMPEG_LOG_PATH.stat().st_size > 2_000_000:
            FFMPEG_LOG_PATH.unlink()  # que no crezca sin fin
        return open(FFMPEG_LOG_PATH, "ab")
    except Exception:
        return None

# Lo último que sonó: se guarda en disco para que no se pierda si el
# servidor se reinicia. Se muestra en la pantalla de "¿Qué escucharemos hoy?".
HISTORY_PATH = Path(__file__).resolve().parent.parent / "history.json"
HISTORY_MAX = 10
STREAM_FRESH_S = 2 * 60 * 60  # cuánto se confía en un enlace de audio ya resuelto

# La sesión (lo que suena, en qué segundo iba y la lista): se guarda todo el
# rato, así si el servidor se reinicia (una actualización, un corte) retoma
# la música donde iba en vez de quedarse callado.
SESSION_PATH = Path(__file__).resolve().parent.parent / "session.json"
SESSION_MAX_AGE_S = 12 * 60 * 60   # una sesión más vieja que esto ya no se retoma
SESSION_EVERY_S = 10               # mientras suena, cada cuánto se anota el segundo

# Registro de actividad: quién hizo qué (se ve en Cumito > Ajustes > Actividad)
ACTIVITY_PATH = Path(__file__).resolve().parent.parent / "activity.json"
ACTIVITY_MAX = 300

DEFAULT_VOLUME = 0.6
MIN_VOLUME = 0.0
MAX_VOLUME = 1.5


def fmt_duration(seconds):
    if not seconds:
        return "?"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


_POOL = None


def _extract_pool():
    """Dos "ayudantes" en procesos aparte, siempre listos (yt-dlp ya cargado),
    con prioridad baja. Antes esto corría en el mismo proceso que el audio y
    lo hacía trabarse mientras se preparaba otra canción."""
    global _POOL
    if _POOL is None:
        import multiprocessing
        from concurrent.futures import ProcessPoolExecutor
        _POOL = ProcessPoolExecutor(max_workers=2, mp_context=multiprocessing.get_context("spawn"),
                                    initializer=_worker_init)
    return _POOL


async def extract(query: str, title_hint: str | None = None) -> dict:
    global _POOL
    loop = asyncio.get_running_loop()
    try:
        return await loop.run_in_executor(_extract_pool(), _extract_sync, query, title_hint)
    except Exception as e:
        from concurrent.futures.process import BrokenProcessPool
        if not isinstance(e, BrokenProcessPool):
            raise
        log.warning("Los ayudantes se cayeron; los reinicio y sigo")
        _POOL = None
        return await loop.run_in_executor(None, _extract_sync, query, title_hint)


def _flat_search(prefix: str, query: str, limit: int) -> list[dict]:
    q = query if _is_url(query) else f"{prefix}{max(1, min(limit, 20))}:{query}"
    with yt_dlp.YoutubeDL(_opts(SEARCH_YTDL_OPTS)) as ydl:
        info = ydl.extract_info(q, download=False)
        entries = info.get("entries") if isinstance(info, dict) else None
        if entries is None:
            entries = [info] if info else []
        out = []
        for e in entries[:limit]:
            if not e:
                continue
            webpage = (
                e.get("webpage_url")
                or e.get("url")
                or (f"https://www.youtube.com/watch?v={e['id']}" if e.get("id") and prefix == "ytsearch" else None)
            )
            if not webpage:
                continue
            out.append({
                "title": e.get("title") or "Sin título",
                "webpage_url": webpage,
                "duration": e.get("duration"),
                "uploader": e.get("uploader") or e.get("channel"),
                "art_url": _best_thumb(e),
            })
        return out


_ytmusic = None


def _music_search(query: str, limit: int) -> list[dict]:
    """Buscar como YouTube Music, en su sección "Canciones": ahí salen las
    versiones de audio oficiales (no el videoclip, ni covers, ni en vivo).
    Usa ytmusicapi (trae artista, duración y portada cuadrada); si no está o
    falla, usa yt-dlp, que solo trae el nombre."""
    global _ytmusic
    try:
        if _ytmusic is None:
            from ytmusicapi import YTMusic
            _ytmusic = YTMusic()
        rows = _ytmusic.search(query, filter="songs", limit=max(1, min(limit, 60)))
        out = []
        for r in rows:
            vid = r.get("videoId")
            if not vid:
                continue
            thumbs = r.get("thumbnails") or []
            art = thumbs[-1]["url"] if thumbs else f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
            # las portadas de YouTube Music se pueden pedir más grandes
            art = re.sub(r"=w\d+-h\d+", "=w400-h400", art)
            out.append({
                "title": r.get("title") or "Sin título",
                "webpage_url": f"https://www.youtube.com/watch?v={vid}",
                "duration": r.get("duration_seconds"),
                "uploader": ", ".join(a.get("name") for a in (r.get("artists") or []) if a.get("name")) or None,
                "art_url": art,
            })
            if len(out) >= limit:
                break
        if out:
            return out
    except Exception as e:
        log.warning("ytmusicapi no pudo buscar (%s); uso yt-dlp", str(e)[:120])
    from urllib.parse import quote_plus
    url = f"https://music.youtube.com/search?q={quote_plus(query)}#songs"
    opts = dict(SEARCH_YTDL_OPTS, playlistend=max(1, min(limit, 40)))
    with yt_dlp.YoutubeDL(_opts(opts)) as ydl:
        info = ydl.extract_info(url, download=False)
    out = []
    for e in (info or {}).get("entries") or []:
        if not e or not e.get("id"):
            continue
        out.append({
            "title": e.get("title") or "Sin título",
            "webpage_url": f"https://www.youtube.com/watch?v={e['id']}",
            "duration": e.get("duration"),
            "uploader": None,
            "art_url": f"https://i.ytimg.com/vi/{e['id']}/hqdefault.jpg",
        })
        if len(out) >= limit:
            break
    return out


PLAYLIST_MAX = 200   # tope por playlist, para que una lista gigante no trabe nada
PREFETCH_AHEAD = 5   # cuántas canciones de la cola se dejan listas de antemano


def is_playlist(query: str) -> bool:
    q = query.strip().lower()
    if not _is_url(q):
        return False
    if "soundcloud.com" in q and "/sets/" in q:
        return True
    # un enlace de UNA canción copiado desde dentro de una playlist trae
    # "v=...&list=...": eso se toma como esa sola canción
    if "v=" in q or "youtu.be/" in q:
        return False
    return "list=" in q or "/playlist" in q


async def playlist_entries(url: str, limit: int = PLAYLIST_MAX) -> list[dict]:
    """Todas las canciones de una playlist (hasta `limit`), en versión
    liviana: título, enlace, duración y portada. El audio de cada una se
    prepara recién cuando le toca sonar (o justo antes, ver _prefetch_next)."""
    loop = asyncio.get_running_loop()

    def _run():
        opts = _opts(SEARCH_YTDL_OPTS)
        opts["playlistend"] = limit
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        out = []
        for e in (info or {}).get("entries") or []:
            if not e:
                continue
            webpage = e.get("webpage_url") or e.get("url") or (
                f"https://www.youtube.com/watch?v={e['id']}" if e.get("id") else None)
            if not webpage or (e.get("title") or "").lower() in ("[private video]", "[deleted video]"):
                continue
            out.append({
                "title": e.get("title") or "Sin título",
                "webpage_url": webpage,
                "duration": e.get("duration"),
                "uploader": e.get("uploader") or e.get("channel"),
                "art_url": _best_thumb(e),
            })
        return out[:limit], (info or {}).get("title")

    return await loop.run_in_executor(None, _run)


async def search(query: str, limit: int = 8, offset: int = 0, kind: str = "all") -> list[dict]:
    """Varios resultados livianos para el mosaico del buscador (sin resolver
    el audio de cada uno, eso se hace recién cuando se elige y se agrega a
    la cola). Si YouTube no responde, busca en SoundCloud.

    offset: para "Buscar más" -- se piden offset+limit y se devuelven solo
    los nuevos."""
    loop = asyncio.get_running_loop()
    offset = max(0, int(offset or 0))

    def _run():
        if kind == "music" and not _is_url(query):
            try:
                results = _music_search(query, offset + limit)[offset:]
                if results:
                    return results
            except Exception as e:
                log.warning("Búsqueda en YouTube Music falló (%s). Busco en YouTube normal...", str(e)[:120])
        try:
            results = _flat_search("ytsearch", query, offset + limit)[offset:]
            if results:
                return results
        except Exception as e:
            log.warning("Búsqueda en YouTube falló (%s). Probando en SoundCloud...", str(e)[:120])
        if _is_url(query):
            return []
        try:
            return _flat_search("scsearch", query, offset + limit)[offset:]
        except Exception:
            return []

    return await loop.run_in_executor(None, _run)


class BotCore:
    """Un BotCore por servidor de Discord configurado (por ahora, uno solo)."""

    def __init__(self, token, guild_id, voice_channel_id, host_display_name, on_change):
        self.token = token
        self.guild_id = guild_id
        self.voice_channel_id = voice_channel_id
        self.host_display_name = host_display_name
        self._notify = on_change    # callback() -> avisa que algo cambió

        intents = discord.Intents.default()
        self.client = discord.Client(intents=intents)
        self.tree = app_commands.CommandTree(self.client)

        self.queue: deque = deque()
        self.current: dict | None = None
        self.paused = False
        self.volume = DEFAULT_VOLUME
        self.ready = asyncio.Event()
        self._started_at = None
        self._paused_total = 0.0
        self._paused_since = None
        self._current_source: discord.PCMVolumeTransformer | None = None
        self.history: deque = deque(self._load_history(), maxlen=HISTORY_MAX)
        self._stopped_on_purpose = False  # skip/stop: que no se confunda con una falla
        self._prefetch_task = None        # el trabajo de dejar listas las siguientes
        self._next_uid = 1                # id único de cada canción en la cola
        self._save_handle = None          # guardado de la sesión (agrupado)
        self._restored = False            # la sesión anterior se retoma una sola vez
        self._closing = False             # apagándose: ya no se toca la cola
        self.activity: deque = deque(self._load_activity(), maxlen=ACTIVITY_MAX)
        self._next_act_id = max((a.get("id", 0) for a in self.activity), default=0) + 1

        self._register_commands()
        self.client.event(self.on_ready)

    # ---------- ciclo de vida ----------
    async def on_ready(self):
        if not discord.opus.is_loaded():
            for name in ("libopus.so.0", "libopus.so", "opus"):
                try:
                    discord.opus.load_opus(name)
                    break
                except Exception:
                    pass
        log.info("Bot listo. Opus (audio de voz) cargado: %s", discord.opus.is_loaded())
        self.ready.set()
        self.on_change()
        if not self._restored:
            self._restored = True
            asyncio.create_task(self._restore_session())
            asyncio.create_task(self._keep_saving())

    async def _setup_hook(self):
        # discord.py llama esto justo después de iniciar sesión y antes de
        # conectarse: recién aquí el bot sabe su propio ID de aplicación, que
        # es lo que hace falta para registrar /play, /skip, etc. (Si se hace
        # antes, Discord lo rechaza con "MissingApplicationID".)
        try:
            await self.tree.sync()
        except Exception:
            logging.getLogger("cumito.bot").exception("No se pudieron registrar los comandos de barra")

    async def start(self):
        self.client.setup_hook = self._setup_hook
        await self.client.start(self.token)

    async def close(self):
        # primero se anota dónde iba (con el bot todavía en el canal) y
        # recién después se desconecta, sin que eso mueva la cola
        if not self._closing:
            self._save_session()
            self._closing = True
        await self.client.close()

    # ---------- todo cambio: avisar a las apps + guardar la sesión ----------
    def on_change(self):
        self._schedule_save()
        self._notify()

    def _schedule_save(self):
        if self._closing or self._save_handle is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        def run():
            self._save_handle = None
            self._save_session()
        self._save_handle = loop.call_later(1.5, run)

    @staticmethod
    def _slim(track):
        return {k: v for k, v in track.items() if k not in ("loading", "failed", "uid")}

    def _save_session(self):
        if self._closing:
            return
        guild = self.client.get_guild(self.guild_id) if self.ready.is_set() else None
        vc = guild.voice_client if guild else None
        data = {
            "saved_at": time.time(),
            "current": ({**self._slim(self.current), "pos": round(self._elapsed())} if self.current else None),
            "queue": [self._slim(t) for t in self.queue],
            "volume": self.volume,
            "channel_id": vc.channel.id if vc is not None and vc.channel is not None else None,
        }
        try:
            tmp = SESSION_PATH.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            tmp.replace(SESSION_PATH)
        except Exception:
            log.exception("No se pudo guardar la sesión")

    async def _keep_saving(self):
        while not self._closing:
            await asyncio.sleep(SESSION_EVERY_S)
            if self.current and not self.paused:
                self._save_session()

    async def _restore_session(self):
        """Después de un reinicio: vuelve a cargar la lista y, si hay gente en
        un canal de voz, entra y sigue la canción desde el segundo en que iba."""
        try:
            data = json.loads(SESSION_PATH.read_text(encoding="utf-8"))
        except Exception:
            return
        if time.time() - float(data.get("saved_at") or 0) > SESSION_MAX_AGE_S:
            return
        tracks = [t for t in data.get("queue") or [] if isinstance(t, dict) and t.get("webpage_url")]
        cur = data.get("current")
        if isinstance(cur, dict) and cur.get("webpage_url"):
            cur["start_at"] = float(cur.pop("pos", 0) or 0)
            tracks.insert(0, cur)
        if not tracks:
            return
        try:
            self.volume = max(MIN_VOLUME, min(MAX_VOLUME, float(data.get("volume", self.volume))))
        except (TypeError, ValueError):
            pass
        self._enqueue(tracks)
        log.info("Sesión anterior recuperada: %d canciones", len(tracks))
        guild = await self._guild()
        if guild is None:
            return
        humans = lambda ch: ch is not None and any(not m.bot for m in getattr(ch, "members", []))
        ch = guild.get_channel(int(data["channel_id"])) if data.get("channel_id") else None
        if not humans(ch):
            ch = self._pick_channel(guild)
        if not humans(ch):
            self.on_change()  # nadie escuchando: la lista queda lista para cuando vuelvan
            return
        try:
            await self._voice_client(connect=True, channel=ch)
        except Exception:
            log.exception("No pude volver a entrar al canal de voz")
            self.on_change()
            return
        if cur:
            self.log_activity("Cumito", "restored", "se reinició y siguió donde iba",
                              title=cur.get("title"), sub=cur.get("uploader"), art=cur.get("art_url"))
        await self._play_next()

    # ---------- registro de actividad ----------
    @staticmethod
    def _load_activity():
        try:
            data = json.loads(ACTIVITY_PATH.read_text(encoding="utf-8"))
            return [a for a in data if isinstance(a, dict) and a.get("text")][-ACTIVITY_MAX:]
        except Exception:
            return []

    def log_activity(self, who, kind, text, title=None, sub=None, art=None):
        who = (str(who).strip() or "Alguien")[:32] if who else "Alguien"
        now = time.time()
        last = self.activity[-1] if self.activity else None
        if (kind in ("volume", "move") and last and last.get("kind") == kind
                and last.get("who") == who and now - last.get("ts", 0) < 10):
            # mover la barrita de volumen no llena el registro: se actualiza
            last.update(text=text, ts=now)
        else:
            self.activity.append({"id": self._next_act_id, "ts": now, "who": who, "kind": kind,
                                  "text": text, "title": title, "sub": sub, "art": art})
            self._next_act_id += 1
        try:
            ACTIVITY_PATH.write_text(json.dumps(list(self.activity), ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass
        self.on_change()

    def activity_list(self, limit=150):
        return list(self.activity)[-limit:]

    # ---------- historial ("lo último que sonó") ----------
    @staticmethod
    def _load_history():
        try:
            data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
            return [t for t in data if isinstance(t, dict) and t.get("webpage_url")][:HISTORY_MAX]
        except Exception:
            return []

    def _remember(self, track):
        entry = {
            "title": track.get("title") or "Sin título",
            "webpage_url": track.get("webpage_url"),
            "duration": track.get("duration"),
            "art_url": track.get("art_url"),
            "uploader": track.get("uploader"),
        }
        if not entry["webpage_url"]:
            return
        # si ya estaba, se sube al primer lugar en vez de repetirse
        for old in list(self.history):
            if old.get("webpage_url") == entry["webpage_url"]:
                self.history.remove(old)
        self.history.appendleft(entry)
        try:
            HISTORY_PATH.write_text(json.dumps(list(self.history), ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass

    # ---------- estado para quien esté escuchando ----------
    def _elapsed(self):
        if not self.current or self._started_at is None:
            return 0
        now = time.monotonic()
        paused_extra = (now - self._paused_since) if self._paused_since else 0
        return max(0, now - self._started_at - self._paused_total - paused_extra)

    def snapshot(self):
        return {
            "host_label": self.host_display_name,
            "now_playing": (
                {
                    "title": self.current["title"],
                    "duration": self.current["duration"],
                    "paused": self.paused,
                    "elapsed": round(self._elapsed()),
                    "art_url": self.current.get("art_url"),
                    "uploader": self.current.get("uploader"),
                    "req": self.current.get("req"),
                }
                if self.current else None
            ),
            "queue": [
                {"uid": t.get("uid"), "req": t.get("req"), "title": t["title"], "duration": t.get("duration"),
                 "uploader": t.get("uploader"),
                 "ready": self._is_ready(t), "loading": bool(t.get("loading")),
                 "prepared": bool(t.get("prepared")),
                 # la portada solo se manda cuando ya está lista: así la app
                 # muestra claramente cuáles faltan por preparar
                 "art_url": t.get("art_url") if t.get("prepared") else None}
                for t in self.queue
            ],
            "recent": list(self.history)[:8],
            "volume": round(self.volume, 2),
            "activity_last": self.activity[-1] if self.activity else None,
        }

    async def _guild(self):
        await self.ready.wait()
        return self.client.get_guild(self.guild_id)

    def _pick_channel(self, guild):
        """A qué canal entrar si nadie dijo uno: al que tenga más gente
        conectada (sin contar bots). Si no hay nadie en ningún canal, al de
        respaldo de config.json (si se puso uno)."""
        best, best_count = None, 0
        for ch in guild.voice_channels:
            count = sum(1 for m in ch.members if not m.bot)
            if count > best_count:
                best, best_count = ch, count
        if best is not None:
            return best
        if self.voice_channel_id:
            return guild.get_channel(self.voice_channel_id)
        return None

    async def _voice_client(self, connect=True, channel=None):
        """El bot sigue a la gente:
        - si se pide un canal (el de quien usó /play), va a ese -- y si ya
          estaba en otro, se cambia;
        - si no, se queda donde esté; y si no está en ninguno, entra al
          canal con más gente."""
        guild = await self._guild()
        if guild is None:
            return None
        vc = guild.voice_client
        if vc is not None and channel is not None and vc.channel != channel:
            await vc.move_to(channel)
        if vc is None and connect:
            target = channel or self._pick_channel(guild)
            if target is None:
                return None
            vc = await target.connect()
        return vc

    # ---------- acciones (las llaman los comandos de Discord Y el relay) ----------
    async def action_playlist_preview(self, url):
        """Para la pantalla de "¿Quieres poner esta playlist?": nombre y
        canciones (solo lo liviano), sin agregar nada todavía."""
        try:
            tracks, name = await playlist_entries(url)
        except Exception as e:
            return {"url": url, "title": None, "entries": [], "error": str(e)[:160]}
        return {
            "url": url,
            "title": name,
            "entries": [{"title": t.get("title"), "duration": t.get("duration"),
                         "uploader": t.get("uploader"), "art_url": t.get("art_url")} for t in tracks],
        }

    async def action_play(self, query, channel=None, as_playlist=False, req=None, who=None):
        """req: código que manda la app con cada canción que agrega desde el
        buscador; vuelve en el estado para que la app sepa en qué posición
        de la cola quedó ("Añadido · #3 en la lista")."""
        vc = await self._voice_client(connect=True, channel=channel)
        if vc is None:
            return "Entra a un canal de voz primero y vuelve a intentarlo."
        if as_playlist or is_playlist(query):
            try:
                tracks, name = await playlist_entries(query)
            except Exception as e:
                return f"No pude abrir esa playlist: {str(e)[:160]}"
            if not tracks:
                return "Esa playlist está vacía o es privada."
            self._enqueue(tracks)
            self._last_added = {"title": f"{len(tracks)} canciones de la playlist" + (f" «{name}»" if name else "")}
            self.log_activity(who, "playlist", f"agregó una playlist de {len(tracks)} canciones",
                              title=name, art=tracks[0].get("art_url"))
            if not vc.is_playing() and not vc.is_paused():
                await self._play_next()
            else:
                self._prefetch_next()
            return None
        try:
            data = await extract(query)
            self._last_added = data
        except Exception as e:
            msg = str(e)
            if "confirm you" in msg or "Sign in" in msg:
                return ("YouTube bloqueó esa canción y tampoco la encontré en SoundCloud. "
                        "Prueba escribiendo el nombre de otra forma.")
            return f"No pude obtener eso: {msg[:160]}"
        if req:
            data["req"] = str(req)[:40]
        self._enqueue([data])
        self.log_activity(who, "add", "agregó 1 canción", title=data.get("title"),
                          sub=data.get("uploader"), art=data.get("art_url"))
        if not vc.is_playing() and not vc.is_paused():
            await self._play_next()
        return None

    async def action_search(self, query, limit=8, offset=0, kind="all"):
        try:
            return await search(query, limit=limit, offset=offset, kind=kind)
        except Exception:
            return []

    async def _play_next(self):
        if self._closing:
            return
        guild = await self._guild()
        vc = guild.voice_client if guild else None
        if vc is None or not vc.is_connected():
            return
        if not self.queue:
            self.current = None
            self.paused = False
            self._current_source = None
            self.on_change()
            return
        track = self.queue.popleft()
        start_at = float(track.pop("start_at", 0) or 0)  # retomar a mitad (después de un reinicio)
        if start_at < 3:
            start_at = 0
        self.current = track
        self.paused = False
        self._started_at = time.monotonic()
        self._paused_total = 0.0
        self._paused_since = None
        self._remember(track)
        self.on_change()
        # si justo se está preparando en segundo plano, se espera a que
        # termine (máx. ~30 s) en vez de pedirla dos veces
        for _ in range(60):
            if not track.get("loading"):
                break
            await asyncio.sleep(0.5)
        try:
            # Si la canción ya se resolvió al agregarla a la cola (hace menos
            # de STREAM_FRESH_S), se usa tal cual: así el skip es casi
            # instantáneo. Los enlaces de audio de YouTube vencen después de
            # unas horas, así que si es más vieja se vuelve a pedir.
            from_cache = bool(track.get("stream_url")) and time.time() - track.get("resolved_at", 0) < STREAM_FRESH_S
            if from_cache:
                data = track
            else:
                data = await extract(track["webpage_url"], title_hint=track.get("title"))
            log.info("Reproduciendo: %s", data.get("title"))
            source = discord.FFmpegPCMAudio(
                data["stream_url"], executable=ffmpeg_path(),
                before_options=_ffmpeg_before(data.get("http_headers")) + (f" -ss {int(start_at)}" if start_at else ""),
                options=FFMPEG_OPTIONS, stderr=_ffmpeg_stderr(),
            )
            source = discord.PCMVolumeTransformer(source, volume=self.volume)
        except Exception:
            log.exception("No se pudo preparar '%s'; paso a la siguiente", track.get("title"))
            return await self._play_next()

        self._current_source = source
        started = time.monotonic()

        def after(error):
            on_purpose, self._stopped_on_purpose = self._stopped_on_purpose, False
            failed_fast = not on_purpose and (error or time.monotonic() - started < 3)
            if error:
                log.error("Error reproduciendo '%s': %s", track.get("title"), error)
            elif failed_fast:
                log.warning("'%s' terminó al instante: revisa ffmpeg.log", track.get("title"))
            if failed_fast and from_cache and self.current is track:
                # el enlace guardado ya no servía: se vuelve a pedir una vez
                retry = {k: v for k, v in track.items() if k not in ("stream_url", "http_headers", "resolved_at")}
                self.queue.appendleft(retry)
            if self._closing:
                return
            asyncio.run_coroutine_threadsafe(self._play_next(), self.client.loop)

        try:
            vc.play(source, after=after)
            # el reloj de la canción arranca cuando de verdad empieza a sonar,
            # no cuando se empezó a prepararla (así la app no se adelanta)
            self._started_at = time.monotonic() - start_at
            self._paused_total = 0.0
            self.on_change()
            self._prefetch_next()
        except Exception:
            log.exception("No se pudo empezar a reproducir '%s'", track.get("title"))
            return await self._play_next()

    # ---------- cola: ids, estados y preparación por tandas ----------
    @staticmethod
    def _is_ready(t):
        return bool(t.get("stream_url")) and time.time() - t.get("resolved_at", 0) < STREAM_FRESH_S

    # La cola tiene dos partes: arriba las PREPARADAS (listas para sonar,
    # se pueden reordenar) y abajo las que todavía no (p. ej. el resto de una
    # playlist de 200). Siempre suenan primero las preparadas, en su orden.
    def _ready_count(self):
        n = 0
        for t in self.queue:
            if not t.get("prepared"):
                break
            n += 1
        return n

    def _enqueue(self, tracks):
        for t in tracks:
            t["uid"] = self._next_uid
            self._next_uid += 1
            t.pop("loading", None)
            if "prepared" not in t:
                t["prepared"] = bool(t.get("stream_url"))
            if t["prepared"]:
                # una canción ya lista (p. ej. del buscador) va al final de las listas
                self.queue.insert(self._ready_count(), t)
            else:
                self.queue.append(t)

    def _move_to_ready(self, item):
        """Recién preparada: pasa al final del grupo de listas."""
        try:
            self.queue.remove(item)
        except ValueError:
            return
        self.queue.insert(self._ready_count(), item)

    async def _prepare(self, item):
        """Deja lista UNA canción de la cola (su enlace de audio y portada)."""
        if item.get("loading") or (item.get("prepared") and self._is_ready(item)):
            return
        item["loading"] = True
        self.on_change()
        try:
            data = await extract(item["webpage_url"], title_hint=item.get("title"))
            data.pop("uid", None)
            item.update(data)
            item["prepared"] = True
            item.pop("failed", None)
            self._move_to_ready(item)
        except Exception as e:
            item["failed"] = True
            log.warning("No se pudo preparar '%s': %s", item.get("title"), str(e)[:120])
        finally:
            item["loading"] = False
            self.on_change()

    def _prefetch_next(self):
        """Mantiene al menos PREFETCH_AHEAD canciones preparadas, tomando las
        que faltan EN ORDEN y de a una (para no saturar la VM)."""
        if self._prefetch_task and not self._prefetch_task.done():
            return

        async def run():
            while True:
                if self._ready_count() >= PREFETCH_AHEAD:
                    return
                pending = [t for t in self.queue
                           if not t.get("prepared") and not t.get("loading") and not t.get("failed")]
                if not pending:
                    return
                await self._prepare(pending[0])

        self._prefetch_task = asyncio.create_task(run())

    def _find(self, index, uid=None):
        """La canción de la cola por posición, comprobando el id si viene (por
        si la cola cambió mientras alguien tocaba en la app)."""
        q = list(self.queue)
        if uid is not None:
            for i, t in enumerate(q):
                if t.get("uid") == uid:
                    return i, t
            return None, None
        if 0 <= index < len(q):
            return index, q[index]
        return None, None

    async def action_prepare(self, index, uid=None):
        """Tocaron una canción que aún no está lista: prepararla ya, aunque
        esté lejos en la cola."""
        _, item = self._find(index, uid)
        if item is not None:
            item.pop("failed", None)
            asyncio.create_task(self._prepare(item))

    async def action_play_index(self, index, uid=None, who=None):
        """Poner YA una canción cualquiera de la cola (la pasa al frente y
        salta la actual)."""
        i, item = self._find(index, uid)
        if item is None:
            return
        del self.queue[i]
        self.queue.appendleft(item)
        self.log_activity(who, "play_now", "puso a sonar", title=item.get("title"),
                          sub=item.get("uploader"), art=item.get("art_url"))
        guild = await self._guild()
        vc = guild.voice_client if guild else None
        if vc and (vc.is_playing() or vc.is_paused()):
            self._stopped_on_purpose = True
            vc.stop()  # dispara _play_next con esta canción al frente
        else:
            if vc is None:
                vc = await self._voice_client(connect=True)
            if vc is not None:
                await self._play_next()

    async def action_pause(self, who=None):
        guild = await self._guild()
        vc = guild.voice_client if guild else None
        if vc and vc.is_playing():
            vc.pause()
            self.paused = True
            self._paused_since = time.monotonic()
            self.log_activity(who, "pause", "pausó la música")

    async def action_resume(self, who=None):
        guild = await self._guild()
        vc = guild.voice_client if guild else None
        if vc and vc.is_paused():
            vc.resume()
            self.paused = False
            if self._paused_since:
                self._paused_total += time.monotonic() - self._paused_since
                self._paused_since = None
            self.log_activity(who, "resume", "reanudó la música")

    async def action_skip(self, who=None):
        guild = await self._guild()
        vc = guild.voice_client if guild else None
        if vc and (vc.is_playing() or vc.is_paused()):
            cur = self.current or {}
            self.log_activity(who, "skip", "saltó", title=cur.get("title"), sub=cur.get("uploader"),
                              art=cur.get("art_url"))
            self._stopped_on_purpose = True
            vc.stop()  # dispara _play_next vía "after"

    async def action_stop(self, who=None):
        """Detiene y vacía la cola, pero se queda conectado al canal."""
        if self.current or self.queue:
            self.log_activity(who, "stop", "detuvo la música y vació la lista")
        self.queue.clear()
        guild = await self._guild()
        vc = guild.voice_client if guild else None
        if vc and (vc.is_playing() or vc.is_paused()):
            self._stopped_on_purpose = True
            vc.stop()
        self.current = None
        self._current_source = None
        self.on_change()

    async def action_stop_and_leave(self, who=None):
        """El botón de 'detener bot': para todo, vacía la cola Y se
        desconecta del canal de voz. No mata el programa, solo la sesión
        actual de audio."""
        self.log_activity(who, "leave", "sacó a Cumito del canal de voz")
        self.queue.clear()
        self.current = None
        self._current_source = None
        guild = await self._guild()
        vc = guild.voice_client if guild else None
        if vc:
            await vc.disconnect(force=True)
        self.on_change()

    async def action_queue_remove(self, index, who=None, uid=None):
        i, item = self._find(index, uid)
        if item is not None:
            q = list(self.queue)
            gone = q.pop(i)
            self.queue = deque(q)
            self.log_activity(who, "remove", "quitó de la lista", title=gone.get("title"),
                              sub=gone.get("uploader"), art=gone.get("art_url") if gone.get("prepared") else None)
            self._prefetch_next()

    async def action_queue_move(self, uid, to_index, who=None):
        """Reordenar: solo dentro del grupo de canciones preparadas."""
        i, item = self._find(-1, uid)
        if item is None or not item.get("prepared"):
            return
        n = self._ready_count()
        to_index = max(0, min(n - 1, int(to_index)))
        if to_index == i:
            return
        q = list(self.queue)
        q.pop(i)
        q.insert(to_index, item)
        self.queue = deque(q)
        self.log_activity(who, "move", "cambió el orden de la lista")

    async def action_queue_clear(self, who=None):
        """Vacía la cola sin tocar lo que está sonando ahora mismo."""
        if self.queue:
            n = len(self.queue)
            self.queue.clear()
            self.log_activity(who, "clear", f"vació la lista ({n} canciones)")

    async def action_set_volume(self, value, who=None):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return
        self.volume = max(MIN_VOLUME, min(MAX_VOLUME, value))
        if self._current_source is not None:
            self._current_source.volume = self.volume
        self.log_activity(who, "volume", f"puso el volumen al {round(self.volume * 100)}%")

    # ---------- comandos de barra en Discord ----------
    def _register_commands(self):
        tree = self.tree

        @tree.command(name="play", description="Reproduce una canción o video de YouTube")
        @app_commands.describe(busqueda="Enlace de YouTube o nombre de la canción")
        async def play(interaction: discord.Interaction, busqueda: str):
            await interaction.response.defer()
            # entra al canal de voz de quien lo pidió (si está en uno)
            voice = getattr(interaction.user, "voice", None)
            err = await self.action_play(busqueda, channel=voice.channel if voice else None,
                                         who=interaction.user.display_name)
            if err:
                await interaction.followup.send(f"❌ {err}")
            else:
                t = getattr(self, "_last_added", None) or {}
                extra = " (desde SoundCloud: YouTube no la dejó sacar)" if t.get("source") == "soundcloud" else ""
                await interaction.followup.send(f"➕ Añadido: **{t.get('title') or busqueda}**{extra}")

        @tree.command(name="skip", description="Salta la canción actual")
        async def skip(interaction: discord.Interaction):
            await self.action_skip(who=interaction.user.display_name)
            await interaction.response.send_message("⏭️ Canción saltada")

        @tree.command(name="pause", description="Pausa la reproducción")
        async def pause(interaction: discord.Interaction):
            await self.action_pause(who=interaction.user.display_name)
            await interaction.response.send_message("⏸️ Pausado")

        @tree.command(name="resume", description="Reanuda la reproducción")
        async def resume(interaction: discord.Interaction):
            await self.action_resume(who=interaction.user.display_name)
            await interaction.response.send_message("▶️ Reanudado")

        @tree.command(name="stop", description="Detiene la música y vacía la cola (sin salir del canal)")
        async def stop(interaction: discord.Interaction):
            await self.action_stop(who=interaction.user.display_name)
            await interaction.response.send_message("⏹️ Detenido")

        @tree.command(name="leave", description="Detiene todo y saca al bot del canal de voz")
        async def leave(interaction: discord.Interaction):
            await self.action_stop_and_leave(who=interaction.user.display_name)
            await interaction.response.send_message("👋 Listo, salí del canal")

        @tree.command(name="volume", description="Cambia el volumen (0 a 100)")
        @app_commands.describe(porcentaje="Un número de 0 a 100")
        async def volume(interaction: discord.Interaction, porcentaje: app_commands.Range[int, 0, 150]):
            await self.action_set_volume(porcentaje / 100, who=interaction.user.display_name)
            await interaction.response.send_message(f"🔊 Volumen al {porcentaje}%")

        @tree.command(name="queue", description="Muestra la cola de reproducción")
        async def queue_cmd(interaction: discord.Interaction):
            snap = self.snapshot()
            lines = []
            if snap["now_playing"]:
                lines.append(f"🎶 Ahora: {snap['now_playing']['title']}")
            for i, t in enumerate(snap["queue"][:10], 1):
                lines.append(f"{i}. {t['title']}")
            await interaction.response.send_message("\n".join(lines) or "La cola está vacía")
