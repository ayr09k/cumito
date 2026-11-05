"""
BotCore: el bot de Discord de Cumito (extracción con yt-dlp, FFmpeg vía
imageio-ffmpeg). Tanto los comandos de barra en Discord como las apps del
grupo (vía relay) disparan las mismas acciones y el mismo aviso de "esto
cambió" hacia quien esté escuchando.
"""
from __future__ import annotations

import asyncio
import json
import logging
import random
import shlex
import shutil
import time
from collections import deque
from pathlib import Path

import discord
from discord import app_commands

from . import audio_cache
from . import lyrics as lyrics_mod
from . import spotify
from .db import Store
from .extractor import (  # noqa: F401  (lo usan el bot y las búsquedas)
    COOKIES_PATH, SEARCH_PREFIX, _extract_sync, _is_url, playlist_sync, radio_sync, search_sync, video_id,
)
from .lanes import LANES

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
# "Volumen parejo": que una canción no suene mucho más fuerte o bajita que
# otra. dynaudnorm cuesta casi nada (medido: ~6 % más que solo decodificar;
# loudnorm costaba 7 veces más, por eso no se usa).
FFMPEG_NORMALIZE = "-af dynaudnorm=f=200:g=11:m=4:p=0.9"
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
LOCAL_WAIT_S = 6              # cuánto se espera a que baje una canción antes de ponerla directo
CACHE_AHEAD = 2               # cuántas de la cola se dejan bajadas

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


async def extract(query: str, title_hint: str | None = None, urgent: bool = False) -> dict:
    """Preparar una canción en un ayudante (urgente o de fondo, ver lanes.py)."""
    return await LANES.heavy(_extract_sync, query, title_hint, urgent=urgent)


PLAYLIST_MAX = 200   # tope por playlist, para que una lista gigante no trabe nada
PREFETCH_AHEAD = 5   # cuántas canciones de la cola se dejan listas de antemano


def is_playlist(query: str) -> bool:
    q = query.strip().lower()
    if spotify.is_spotify(q):
        return spotify.kind(q) in ("album", "playlist")
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
    prepara recién cuando le toca sonar (o justo antes, ver _prefetch_next).
    Las de Spotify se leen de su página y se buscan en YouTube al prepararse."""
    if spotify.is_spotify(url):
        data = await LANES.light(spotify.resolve, url)
        return data["tracks"][:limit], data.get("title")
    return await LANES.heavy(playlist_sync, url, limit, urgent=True)


async def search(query: str, limit: int = 8, offset: int = 0, kind: str = "all") -> list[dict]:
    """Varios resultados livianos para el mosaico del buscador (sin resolver
    el audio de cada uno, eso se hace recién cuando se elige y se agrega a
    la cola). Corre en el ayudante urgente."""
    offset = max(0, int(offset or 0))
    return await LANES.heavy(search_sync, query, limit, offset, kind, urgent=True)


class BotCore:
    """Un BotCore por servidor de Discord configurado (por ahora, uno solo)."""

    FEATURES = ["prev", "seek", "repeat", "shuffle", "sleep", "normalize", "radio", "lyrics", "react",
                "albums", "stats", "spotify"]

    def __init__(self, token, guild_id, voice_channel_id, host_display_name, on_change, store=None):
        self.token = token
        self.guild_id = guild_id
        self.voice_channel_id = voice_channel_id
        self.host_display_name = host_display_name
        self._notify = on_change    # callback() -> avisa que algo cambió

        intents = discord.Intents.default()
        self.client = discord.Client(intents=intents)
        self.tree = app_commands.CommandTree(self.client)
        self.db = store or Store()
        try:
            audio_cache.startup()
        except Exception:
            log.exception("No se pudo abrir la carpeta del caché de audio")

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
        self._stop_reason = None          # por qué se cortó la canción: skip/stop/seek/prev/jump (None = terminó)
        self._seeking = False             # la próxima que suena es la misma, desde otro segundo
        self._resume_paused = False       # (y si estaba en pausa, que siga en pausa)
        self._prefetch_task = None        # el trabajo de dejar listas las siguientes
        self._next_uid = 1                # id único de cada canción en la cola
        self._save_handle = None          # guardado de la sesión (agrupado)
        self._restored = False            # la sesión anterior se retoma una sola vez
        self._closing = False             # apagándose: ya no se toca la cola
        self.activity: deque = deque(self._load_activity(), maxlen=ACTIVITY_MAX)
        self._next_act_id = max((a.get("id", 0) for a in self.activity), default=0) + 1

        # 2.0
        self.played: deque = deque(maxlen=50)   # lo que ya sonó en esta sesión (para "atrás")
        self.repeat = "off"                     # off / one / all
        self.radio = False                      # cuando se acaba la lista, sigue con parecidas
        self.normalize = False                  # volumen parejo
        self.sleep_at = None                    # temporizador: hora (epoch) en que se apaga
        self.sleep_eot = False                  # ... o al terminar la canción actual
        self._sleep_task = None
        self._radio_task = None
        self.reaction = None                    # la última reacción (las apps la animan)
        self._next_react = 1
        self._react_last: dict = {}
        self._lyrics_inflight: dict = {}

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
        LANES.shutdown()
        self.db.close()

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
        return {k: v for k, v in track.items() if k not in ("loading", "failed", "uid", "_row")}

    def _save_session(self):
        if self._closing:
            return
        guild = self.client.get_guild(self.guild_id) if self.ready.is_set() else None
        vc = guild.voice_client if guild else None
        data = {
            "saved_at": time.time(),
            "current": ({**self._slim(self.current), "pos": round(self._elapsed())} if self.current else None),
            "queue": [self._slim(t) for t in self.queue],
            "played": [self._slim(t) for t in list(self.played)[-20:]],
            "volume": self.volume,
            "repeat": self.repeat,
            "radio": self.radio,
            "normalize": self.normalize,
            "sleep_at": self.sleep_at,
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
        # los ajustes se recuerdan siempre (aunque no haya lista)
        if data.get("repeat") in ("off", "one", "all"):
            self.repeat = data["repeat"]
        self.radio = bool(data.get("radio"))
        self.normalize = bool(data.get("normalize"))
        sleep_at = data.get("sleep_at")
        if isinstance(sleep_at, (int, float)) and sleep_at > time.time() + 5:
            self._arm_sleep(sleep_at)
        for t in data.get("played") or []:
            if isinstance(t, dict) and t.get("webpage_url"):
                self.played.append(t)
        tracks = [t for t in data.get("queue") or [] if isinstance(t, dict) and t.get("webpage_url")]
        cur = data.get("current")
        if isinstance(cur, dict) and cur.get("webpage_url"):
            cur["start_at"] = float(cur.pop("pos", 0) or 0)
            tracks.insert(0, cur)
        if not tracks:
            self.on_change()
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
        if (kind in ("volume", "move", "seek") and last and last.get("kind") == kind
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
        cur = self.current
        return {
            "host_label": self.host_display_name,
            "now_playing": (
                {
                    "title": cur["title"],
                    "duration": cur["duration"],
                    "paused": self.paused,
                    "elapsed": round(self._elapsed()),
                    "art_url": cur.get("art_url"),
                    "uploader": cur.get("uploader"),
                    "req": cur.get("req"),
                    "who": cur.get("who"),
                    "webpage_url": cur.get("webpage_url") if not str(cur.get("webpage_url", "")).startswith(
                        SEARCH_PREFIX) else None,
                    "source": cur.get("source"),
                    "radio": bool(cur.get("radio")),
                }
                if cur else None
            ),
            "queue": [
                {"uid": t.get("uid"), "req": t.get("req"), "title": t["title"], "duration": t.get("duration"),
                 "uploader": t.get("uploader"), "who": t.get("who"),
                 "ready": self._is_ready(t), "loading": bool(t.get("loading")),
                 "prepared": bool(t.get("prepared")), "radio": bool(t.get("radio")),
                 # la portada solo se manda cuando ya está lista: así la app
                 # muestra claramente cuáles faltan por preparar
                 "art_url": t.get("art_url") if t.get("prepared") else None}
                for t in self.queue
            ],
            "recent": list(self.history)[:8],
            "volume": round(self.volume, 2),
            "activity_last": self.activity[-1] if self.activity else None,
            # 2.0 (las apps viejas no los miran)
            "server_v": 2,
            "features": self.FEATURES + (["solo"] if audio_cache.publishes() else []),
            "repeat": self.repeat,
            "radio": self.radio,
            "normalize": self.normalize,
            "sleep": ({"at": self.sleep_at, "eot": self.sleep_eot}
                      if (self.sleep_at or self.sleep_eot) else None),
            "can_prev": bool(self.played) or (bool(cur) and self._elapsed() > 5),
            "reaction": self.reaction,
            "albums_rev": self.db.albums_rev,
            "app_id": self._app_id(),   # para que las apps muestren "Escuchando en Cumito" en Discord
        }

    def _app_id(self):
        try:
            v = self.client.application_id
            return str(v) if isinstance(v, int) else None
        except Exception:
            return None

    async def _guild(self):
        await self.ready.wait()
        return self.client.get_guild(self.guild_id)

    async def _vc(self):
        guild = await self._guild()
        return guild.voice_client if guild else None

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

    def _cut(self, vc, reason):
        """Cortar lo que suena a propósito (dispara _after_track)."""
        self._stop_reason = reason
        vc.stop()

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
        query = (query or "").strip()
        if not query:
            return "Escribe qué canción quieres."
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
            for t in tracks:
                t["who"] = who
            self._enqueue(tracks)
            self._last_added = {"title": f"{len(tracks)} canciones de la playlist" + (f" «{name}»" if name else "")}
            self.log_activity(who, "playlist", f"agregó una playlist de {len(tracks)} canciones",
                              title=name, art=tracks[0].get("art_url"))
            if not vc.is_playing() and not vc.is_paused():
                await self._play_next()
            else:
                self._prefetch_next()
            return None
        hint = None
        if spotify.is_spotify(query):
            try:
                sp = await LANES.light(spotify.resolve, query)
                t0 = sp["tracks"][0]
                query, hint = t0["webpage_url"], t0["title"]
            except Exception as e:
                return f"No pude leer ese enlace de Spotify: {str(e)[:120]}"
        try:
            data = await extract(query, title_hint=hint, urgent=True)
            self._last_added = data
        except Exception as e:
            msg = str(e)
            if "confirm you" in msg or "Sign in" in msg:
                return ("YouTube bloqueó esa canción y tampoco la encontré en SoundCloud. "
                        "Prueba escribiendo el nombre de otra forma.")
            return f"No pude obtener eso: {msg[:160]}"
        if req:
            data["req"] = str(req)[:40]
        data["who"] = who
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
            log.exception("La búsqueda falló")
            return []

    async def _play_next(self):
        if self._closing:
            return
        vc = await self._vc()
        if vc is None or not vc.is_connected():
            return
        if not self.queue:
            seed = self.current or (self.played[-1] if self.played else None)
            self.current = None
            self.paused = False
            self._current_source = None
            self.on_change()
            if self.radio and seed:
                self._maybe_radio(seed, start_after=True)
            return
        track = self.queue.popleft()
        seeking, self._seeking = self._seeking, False
        keep_paused, self._resume_paused = self._resume_paused, False
        start_at = float(track.pop("start_at", 0) or 0)  # retomar a mitad (reinicio) o adelantar
        if start_at < 3 and not seeking:
            start_at = 0
        self.current = track
        self.paused = False
        self._started_at = time.monotonic() - start_at
        self._paused_total = 0.0
        self._paused_since = None
        if not seeking:
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
            # ya bajada al disco: no hace falta volver a pedirle el enlace a YouTube
            from_cache = self._is_ready(track) or audio_cache.ready_path(track) is not None
            if not from_cache:
                data = await extract(track["webpage_url"], title_hint=track.get("title"), urgent=True)
                data.pop("uid", None)
                track.update(data)
                track["prepared"] = True
            if self.current is not track or self._closing:
                return  # mientras se preparaba, alguien puso otra
            # sonar desde el disco (ver audio_cache): si no estaba bajada se
            # espera un momento a que baje; si tarda, suena directo como antes
            local = audio_cache.ready_path(track)
            if local is None:
                try:
                    local = await asyncio.wait_for(audio_cache.fetch(track, urgent=True), LOCAL_WAIT_S)
                except asyncio.TimeoutError:
                    local = None
                if self.current is not track or self._closing:
                    return
            log.info("Reproduciendo: %s%s%s", track.get("title"), f" (desde {int(start_at)} s)" if start_at else "",
                     "" if local else " [directo]")
            options = FFMPEG_OPTIONS + (" " + FFMPEG_NORMALIZE if self.normalize else "")
            seek = f" -ss {start_at:.1f}" if start_at else ""
            if local:
                source = discord.FFmpegPCMAudio(
                    str(local), executable=ffmpeg_path(), before_options="-loglevel error" + seek,
                    options=options, stderr=_ffmpeg_stderr(),
                )
            else:
                source = discord.FFmpegPCMAudio(
                    track["stream_url"], executable=ffmpeg_path(),
                    before_options=_ffmpeg_before(track.get("http_headers")) + seek,
                    options=options, stderr=_ffmpeg_stderr(),
                )
            self._cache_ahead()
            source = discord.PCMVolumeTransformer(source, volume=self.volume)
        except Exception:
            log.exception("No se pudo preparar '%s'; paso a la siguiente", track.get("title"))
            self.played.append(self._slim(track))
            return await self._play_next()

        self._current_source = source
        started = time.monotonic()
        loop = asyncio.get_running_loop()

        def after(error):
            reason, self._stop_reason = self._stop_reason, None
            failed_fast = reason is None and (error or time.monotonic() - started < 3)
            if error:
                log.error("Error reproduciendo '%s': %s", track.get("title"), error)
            elif failed_fast:
                log.warning("'%s' terminó al instante: revisa ffmpeg.log", track.get("title"))
            listened = self._elapsed() if self.current is track else 0
            if self._closing:
                return
            asyncio.run_coroutine_threadsafe(
                self._after_track(track, reason, bool(failed_fast), from_cache, listened), loop)

        try:
            vc.play(source, after=after)
            # el reloj de la canción arranca cuando de verdad empieza a sonar,
            # no cuando se empezó a prepararla (así la app no se adelanta)
            self._started_at = time.monotonic() - start_at
            self._paused_total = 0.0
            if keep_paused:
                vc.pause()
                self.paused = True
                self._paused_since = time.monotonic()
            self.on_change()
            self._prefetch_next()
            if not seeking:
                asyncio.create_task(self._db_play_start(track))
                asyncio.create_task(self._lyrics_quiet(track))
            if self.radio:
                self._maybe_radio(track)
        except Exception:
            log.exception("No se pudo empezar a reproducir '%s'", track.get("title"))
            return await self._play_next()

    async def _after_track(self, track, reason, failed_fast, from_cache, listened):
        """Terminó (o se cortó) una canción: qué viene después."""
        if reason not in ("seek",):
            asyncio.create_task(self._db_play_end(track, listened, skipped=reason in ("skip", "jump", "prev")))
        if failed_fast:
            bad = audio_cache.ready_path(track)   # un archivo que no sirve no se vuelve a usar
            if bad:
                bad.unlink(missing_ok=True)
        if failed_fast and from_cache and self.current is track:
            # el enlace guardado ya no servía: se vuelve a pedir una vez
            retry = {k: v for k, v in track.items() if k not in ("stream_url", "http_headers", "resolved_at", "_row")}
            retry["prepared"] = True
            self.queue.appendleft(retry)
        elif reason not in ("seek", "prev", "stop"):
            self.played.append(self._slim(track))
            if reason is None and self.repeat == "one":
                again = self._slim(track)
                again["prepared"] = True
                self._enqueue_front(again)
            elif reason in (None, "skip", "jump") and self.repeat == "all":
                again = self._slim(track)
                again["prepared"] = False
                self._enqueue([again])
        if reason == "stop":
            return   # detener/sacar: no sigue con nada (ni la radio)
        if reason is None and self.sleep_eot:
            await self.action_stop_and_leave(who="Temporizador")
            return
        await self._play_next()

    # ---------- base de datos: lo que sonó ----------
    async def _db_play_start(self, track):
        try:
            track["_row"] = await self.db.run(self.db.play_start, track)
        except Exception:
            log.exception("No se pudo anotar la reproducción")

    async def _db_play_end(self, track, listened, skipped):
        row = track.get("_row")
        if not row:
            return
        try:
            await self.db.run(self.db.play_end, row, listened, skipped, self._slim(track))
        except Exception:
            log.exception("No se pudo cerrar la reproducción")

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

    def _new_uid(self, t):
        t["uid"] = self._next_uid
        self._next_uid += 1
        t.pop("loading", None)
        t.pop("_row", None)

    def _enqueue(self, tracks):
        for t in tracks:
            self._new_uid(t)
            if "prepared" not in t:
                t["prepared"] = bool(t.get("stream_url"))
            if t["prepared"]:
                # una canción ya lista (p. ej. del buscador) va al final de las listas
                self.queue.insert(self._ready_count(), t)
            else:
                self.queue.append(t)

    def _enqueue_front(self, t):
        if "uid" not in t:
            self._new_uid(t)
        t["prepared"] = True
        self.queue.appendleft(t)

    def _move_to_ready(self, item):
        """Recién preparada: pasa al final del grupo de listas."""
        try:
            self.queue.remove(item)
        except ValueError:
            return
        self.queue.insert(self._ready_count(), item)

    async def _prepare(self, item, urgent=False):
        """Deja lista UNA canción de la cola (su enlace de audio y portada)."""
        if item.get("loading") or (item.get("prepared") and self._is_ready(item)):
            return
        if self._is_ready(item):   # ya tenía su audio (p. ej. tras mezclar): solo se marca
            item["prepared"] = True
            self._move_to_ready(item)
            self.on_change()
            return
        item["loading"] = True
        self.on_change()
        try:
            data = await extract(item["webpage_url"], title_hint=item.get("title"), urgent=urgent)
            data.pop("uid", None)
            item.update(data)
            item["prepared"] = True
            item.pop("failed", None)
            self._move_to_ready(item)
            self._cache_ahead()
        except Exception as e:
            item["failed"] = True
            log.warning("No se pudo preparar '%s': %s", item.get("title"), str(e)[:120])
        finally:
            item["loading"] = False
            self.on_change()

    def _cache_ahead(self):
        """Deja bajadas al disco las próximas CACHE_AHEAD de la cola, de a una
        y en segundo plano, para que suenen sin trabones."""
        for t in list(self.queue)[:CACHE_AHEAD]:
            if self._is_ready(t) and not audio_cache.ready_path(t):
                asyncio.create_task(audio_cache.fetch(t))

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
            asyncio.create_task(self._prepare(item, urgent=True))

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
        vc = await self._vc()
        if vc and (vc.is_playing() or vc.is_paused()):
            self._cut(vc, "jump")  # dispara _play_next con esta canción al frente
        else:
            if vc is None:
                vc = await self._voice_client(connect=True)
            if vc is not None:
                await self._play_next()

    async def action_pause(self, who=None):
        vc = await self._vc()
        if vc and vc.is_playing():
            vc.pause()
            self.paused = True
            self._paused_since = time.monotonic()
            self.log_activity(who, "pause", "pausó la música")

    async def action_resume(self, who=None):
        vc = await self._vc()
        if vc and vc.is_paused():
            vc.resume()
            self.paused = False
            if self._paused_since:
                self._paused_total += time.monotonic() - self._paused_since
                self._paused_since = None
            self.log_activity(who, "resume", "reanudó la música")
        elif vc is not None and not vc.is_playing() and self.queue and self.current is None:
            await self._play_next()   # había lista pero nada sonando: arranca

    async def action_skip(self, who=None):
        vc = await self._vc()
        if vc and (vc.is_playing() or vc.is_paused()):
            cur = self.current or {}
            self.log_activity(who, "skip", "saltó", title=cur.get("title"), sub=cur.get("uploader"),
                              art=cur.get("art_url"))
            self._cut(vc, "skip")  # dispara _play_next vía "after"

    async def action_prev(self, who=None):
        """Atrás: si la canción ya lleva más de 5 s, vuelve a su inicio; si
        no, pone la anterior (y la actual queda primera en la lista)."""
        vc = await self._vc()
        playing = vc is not None and (vc.is_playing() or vc.is_paused())
        if self.current and playing and (self._elapsed() > 5 or not self.played):
            await self.action_seek(0, who=who, quiet=True)
            self.log_activity(who, "seek", "volvió al inicio de la canción")
            return
        if not self.played:
            return
        prev = self.played.pop()
        prev.pop("start_at", None)
        if self.current and playing:
            cur = self.current
            cur.pop("start_at", None)
            self._enqueue_front(cur)
        self._enqueue_front(prev)
        self.log_activity(who, "prev", "volvió a la anterior", title=prev.get("title"),
                          sub=prev.get("uploader"), art=prev.get("art_url"))
        if playing:
            self._cut(vc, "prev")
        else:
            if vc is None:
                vc = await self._voice_client(connect=True)
            if vc is not None:
                await self._play_next()

    async def action_seek(self, pos, who=None, quiet=False):
        """Adelantar/atrasar la canción: se vuelve a abrir desde ese segundo
        (con el enlace ya preparado, así que tarda muy poco)."""
        vc = await self._vc()
        if not self.current or vc is None or not (vc.is_playing() or vc.is_paused()):
            return
        try:
            pos = max(0.0, float(pos))
        except (TypeError, ValueError):
            return
        dur = self.current.get("duration") or 0
        if dur:
            pos = min(pos, max(0, dur - 2))
        cur = self.current
        cur["start_at"] = pos
        self._seeking = True
        self._resume_paused = self.paused
        self._enqueue_front(cur)
        if not quiet:
            m, s = divmod(int(pos), 60)
            self.log_activity(who, "seek", f"adelantó la canción al {m}:{s:02d}", title=cur.get("title"),
                              sub=cur.get("uploader"), art=cur.get("art_url"))
        self._cut(vc, "seek")

    async def action_set_repeat(self, mode, who=None):
        if mode not in ("off", "one", "all") or mode == self.repeat:
            return
        self.repeat = mode
        text = {"off": "quitó la repetición", "one": "puso a repetir esta canción",
                "all": "puso a repetir toda la lista"}[mode]
        self.log_activity(who, "repeat", text)

    async def action_shuffle(self, who=None):
        """Mezclar la lista (una vez). Las primeras quedan listas para sonar
        y el resto se va preparando en el nuevo orden."""
        q = list(self.queue)
        if len(q) < 2:
            return
        random.shuffle(q)
        for i, t in enumerate(q):
            if i >= PREFETCH_AHEAD:
                t["prepared"] = False   # su audio se guarda: si sigue fresco, prepararla es instantáneo
        q = [t for t in q if t.get("prepared")] + [t for t in q if not t.get("prepared")]
        self.queue = deque(q)
        self.log_activity(who, "shuffle", f"mezcló la lista ({len(q)} canciones)")
        self._prefetch_next()

    async def action_set_radio(self, on, who=None):
        on = bool(on)
        if on == self.radio:
            return
        self.radio = on
        self.log_activity(who, "radio", "prendió la radio: cuando se acabe la lista, siguen parecidas"
                          if on else "apagó la radio")
        if on:
            seed = self.current or (self.played[-1] if self.played else None)
            if seed:
                self._maybe_radio(seed, start_after=self.current is None)

    async def action_radio_now(self, who=None):
        """Botón de la lista vacía: "Generar recomendaciones de esta canción".
        Agrega una tanda de parecidas UNA vez, sin prender la radio."""
        seed = self.current or (self.played[-1] if self.played else None)
        if not seed or (self._radio_task and not self._radio_task.done()):
            return
        self.log_activity(who, "radio", "pidió recomendaciones", title=f"Parecidas a {seed.get('title')}",
                          sub=seed.get("uploader"), art=seed.get("art_url"))
        self._radio_task = asyncio.create_task(self._radio_fill(seed, start_after=self.current is None, force=True))

    def _radio_off_if_emptied(self, who):
        """Si vaciaron la lista a mano con la radio prendida, se apaga: si no,
        la radio la vuelve a llenar y se hace un bucle de borrar y que aparezcan
        más. En la lista sale el botón para pedir recomendaciones cuando quieran."""
        if self.radio and not self.queue:
            self.radio = False
            self.log_activity(who, "radio", "vació la lista: la radio se apagó")
            self.on_change()

    def _maybe_radio(self, seed, start_after=False):
        if not self.radio or (self._radio_task and not self._radio_task.done()):
            return
        if len(self.queue) >= 2:
            return
        self._radio_task = asyncio.create_task(self._radio_fill(seed, start_after))

    async def _radio_fill(self, seed, start_after=False, force=False):
        url = seed.get("webpage_url")
        if not video_id(url):
            return
        seen = list(self.played)[-40:] + list(self.queue) + ([self.current] if self.current else [])
        skip = tuple(v for v in (video_id(t.get("webpage_url")) for t in seen) if v)
        try:
            tracks = await LANES.light(radio_sync, url, 8, skip)
        except Exception as e:
            log.warning("La radio no respondió: %s", str(e)[:120])
            return
        if not tracks or not (self.radio or force):
            if force:
                self.on_change()   # que la app deje de decir "Buscando parecidas…"
            return
        for t in tracks:
            t["who"] = "Radio"
            t["radio"] = True
        self._enqueue(tracks)
        self.log_activity("Cumito", "radio", f"agregó {len(tracks)} canciones de la radio",
                          title=f"Parecidas a {seed.get('title')}", sub=seed.get("uploader"),
                          art=seed.get("art_url"))
        vc = await self._vc()
        if start_after and self.current is None and vc is not None and not vc.is_playing():
            await self._play_next()
        else:
            self._prefetch_next()

    async def action_set_normalize(self, on, who=None):
        on = bool(on)
        if on == self.normalize:
            return
        self.normalize = on
        self.log_activity(who, "normalize", "prendió el volumen parejo" if on else "apagó el volumen parejo")
        if self.current:
            await self.action_seek(self._elapsed(), who=who, quiet=True)  # se aplica ya

    def _arm_sleep(self, at):
        if self._sleep_task and not self._sleep_task.done():
            self._sleep_task.cancel()
        self.sleep_at = at

        async def wait():
            try:
                await asyncio.sleep(max(0, at - time.time()))
            except asyncio.CancelledError:
                return
            self.sleep_at = None
            self.sleep_eot = False
            await self.action_stop_and_leave(who="Temporizador")

        self._sleep_task = asyncio.create_task(wait())

    async def action_sleep(self, minutes=None, end_of_track=False, who=None):
        """Temporizador: apaga la música en X minutos o al terminar esta canción."""
        if self._sleep_task and not self._sleep_task.done():
            self._sleep_task.cancel()
        self._sleep_task = None
        self.sleep_at, self.sleep_eot = None, False
        try:
            minutes = float(minutes or 0)
        except (TypeError, ValueError):
            minutes = 0
        if end_of_track:
            self.sleep_eot = True
            self.log_activity(who, "sleep", "puso el temporizador: se apaga al terminar esta canción")
        elif minutes > 0:
            minutes = min(minutes, 12 * 60)
            self._arm_sleep(time.time() + minutes * 60)
            self.log_activity(who, "sleep", f"puso el temporizador: se apaga en {round(minutes)} min")
        else:
            self.log_activity(who, "sleep", "quitó el temporizador")

    def action_react(self, emoji, who=None):
        emoji = str(emoji or "").strip()[:8]
        if not emoji:
            return
        key = who or "?"
        now = time.time()
        if now - self._react_last.get(key, 0) < 0.6:
            return   # que nadie la llene de reacciones
        self._react_last[key] = now
        self.reaction = {"id": self._next_react, "who": who or "Alguien", "emoji": emoji, "ts": now}
        self._next_react += 1
        self._notify()   # (no hace falta guardar la sesión por esto)

    async def action_stop(self, who=None):
        """Detiene y vacía la cola, pero se queda conectado al canal."""
        if self.current or self.queue:
            self.log_activity(who, "stop", "detuvo la música y vació la lista")
        self.queue.clear()
        vc = await self._vc()
        if vc and (vc.is_playing() or vc.is_paused()):
            self._cut(vc, "stop")
        self.current = None
        self._current_source = None
        self.on_change()

    async def action_stop_and_leave(self, who=None):
        """El botón de 'detener bot': para todo, vacía la cola Y se
        desconecta del canal de voz. No mata el programa, solo la sesión
        actual de audio."""
        self.log_activity(who, "leave", "sacó a Cumito del canal de voz" if who != "Temporizador"
                          else "se apagó (temporizador)")
        self.sleep_eot = False
        self.queue.clear()
        self.current = None
        self._current_source = None
        vc = await self._vc()
        if vc:
            if vc.is_playing() or vc.is_paused():
                self._stop_reason = "stop"
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
            self._radio_off_if_emptied(who)
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
            self._radio_off_if_emptied(who)

    async def action_set_volume(self, value, who=None):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return
        self.volume = max(MIN_VOLUME, min(MAX_VOLUME, value))
        if self._current_source is not None:
            self._current_source.volume = self.volume
        self.log_activity(who, "volume", f"puso el volumen al {round(self.volume * 100)}%")

    # ---------- letras (karaoke) ----------
    @staticmethod
    def _lyrics_key(track):
        url = track.get("webpage_url") or ""
        return video_id(url) or url or (track.get("title") or "").lower()

    async def lyrics_for(self, track: dict) -> dict:
        """La letra de una canción: primero la guardada; si no, LRCLIB (una
        sola consulta aunque la pidan varios a la vez)."""
        key = self._lyrics_key(track)
        base = {"key": key, "webpage_url": track.get("webpage_url")}
        if not key or str(track.get("webpage_url", "")).startswith(SEARCH_PREFIX):
            return {**base, "found": False, "pending": True}
        try:
            cached = await self.db.run(self.db.lyrics_get, key, None)
        except Exception:
            cached = None
        if cached and (cached.get("found") or time.time() - cached.get("ts", 0) < 86400):
            return {**cached, **base}
        task = self._lyrics_inflight.get(key)
        if task is None:
            async def fetch():
                try:
                    data = await LANES.light(lyrics_mod.fetch, track.get("title") or "", track.get("uploader"),
                                             track.get("duration"))
                except Exception as e:
                    return {"found": False, "error": str(e)[:120]}
                data["ts"] = time.time()
                try:
                    await self.db.run(self.db.lyrics_put, key, data)
                except Exception:
                    pass
                return data
            task = asyncio.create_task(fetch())
            self._lyrics_inflight[key] = task
            task.add_done_callback(lambda _t: self._lyrics_inflight.pop(key, None))
        data = await task
        return {**data, **base}

    async def _lyrics_quiet(self, track):
        """Al empezar una canción se busca su letra de antemano: así, cuando
        alguien abre el karaoke, ya está."""
        await asyncio.sleep(2)
        if self.current is track:
            try:
                await self.lyrics_for(track)
            except Exception:
                pass

    # ---------- Discos ----------
    async def album_play(self, album_id, shuffle=False, who=None):
        alb = await self.db.run(self.db.album, int(album_id))
        if not alb:
            return "Ese disco ya no existe."
        if not alb["tracks"]:
            return "Ese disco todavía no tiene canciones."
        vc = await self._voice_client(connect=True)
        if vc is None:
            return "Entra a un canal de voz primero y vuelve a intentarlo."
        tracks = [{"title": t["title"], "webpage_url": t["webpage_url"], "duration": t["duration"],
                   "uploader": t["uploader"], "art_url": t["art_url"], "who": who, "album": alb["name"]}
                  for t in alb["tracks"]]
        if shuffle:
            random.shuffle(tracks)
        self._enqueue(tracks)
        self.log_activity(who, "album", f"puso el disco «{alb['name']}» ({len(tracks)} canciones)"
                          + (" en aleatorio" if shuffle else ""), title=alb["name"])
        if not vc.is_playing() and not vc.is_paused():
            await self._play_next()
        else:
            self._prefetch_next()
        return None

    def track_for_album(self, which: str = "current", uid=None) -> dict | None:
        """La canción que se quiere guardar en un disco: la que suena o una de la lista."""
        t = None
        if which == "current":
            t = self.current
        elif uid is not None:
            _, t = self._find(-1, uid)
        if not t or str(t.get("webpage_url", "")).startswith(SEARCH_PREFIX):
            return None
        return {"title": t.get("title"), "webpage_url": t.get("webpage_url"), "duration": t.get("duration"),
                "uploader": t.get("uploader"), "art_url": t.get("art_url")}

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

        @tree.command(name="back", description="Vuelve a la canción anterior")
        async def back(interaction: discord.Interaction):
            await self.action_prev(who=interaction.user.display_name)
            await interaction.response.send_message("⏮️ Atrás")

        @tree.command(name="shuffle", description="Mezcla la lista")
        async def shuffle(interaction: discord.Interaction):
            await self.action_shuffle(who=interaction.user.display_name)
            await interaction.response.send_message("🔀 Lista mezclada")

        @tree.command(name="radio", description="Prende o apaga la radio (canciones parecidas al acabarse la lista)")
        async def radio(interaction: discord.Interaction):
            await self.action_set_radio(not self.radio, who=interaction.user.display_name)
            await interaction.response.send_message("📻 Radio prendida" if self.radio else "📻 Radio apagada")

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
