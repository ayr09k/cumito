"""
Lo que prepara las canciones (yt-dlp), separado del bot: corre en procesos
"ayudantes" aparte (ver bot._extract_pool) que no cargan Discord, así ocupan
poca memoria y el trabajo pesado no traba la música que está sonando.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import sysconfig
import time
from pathlib import Path

import yt_dlp

log = logging.getLogger("cumito.extractor")

# --- Deno / FFmpeg: carpetas donde pueden vivir, sin que haya que tocar nada ---
for _d in (
    sysconfig.get_path("scripts"),
    os.path.dirname(sys.executable),
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WinGet", "Links"),
    os.path.join(os.path.expanduser("~"), ".deno", "bin"),
):
    if _d and os.path.isdir(_d):
        os.environ["PATH"] = _d + os.pathsep + os.environ.get("PATH", "")


YTDL_OPTS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "socket_timeout": 20,
}
# Para buscar varios resultados rápido (el mosaico del buscador): extracción
# "plana", sin resolver el audio de cada video uno por uno.
SEARCH_YTDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "default_search": "ytsearch",
    "extract_flat": "in_playlist",
    "skip_download": True,
    "socket_timeout": 20,
}


def _best_thumb(info: dict):
    """Saca la mejor miniatura que yt-dlp nos haya dado, sin pedir nada extra."""
    thumb = info.get("thumbnail")
    if thumb:
        return thumb
    thumbs = info.get("thumbnails") or []
    if thumbs:
        return thumbs[-1].get("url")
    return None


# ---------------------------------------------------------------------------
# YouTube desconfía de los servidores en la nube y a veces pide "iniciar
# sesión". Dos defensas:
#   1. cookies.txt (opcional, al lado de run.py): cookies de una cuenta de
#      Google DE REPUESTO. Si existe, se usa para YouTube.
#   2. Respaldo con SoundCloud: si YouTube no deja sacar una canción, se
#      busca la misma (por su título) en SoundCloud y se pone desde ahí.
# ---------------------------------------------------------------------------
COOKIES_PATH = Path(__file__).resolve().parent.parent / "cookies.txt"


def _opts(base: dict) -> dict:
    opts = dict(base)
    if COOKIES_PATH.exists():
        opts["cookiefile"] = str(COOKIES_PATH)
    return opts


def _is_url(q: str) -> bool:
    return q.strip().lower().startswith(("http://", "https://"))


def _youtube_title(url: str) -> str | None:
    """El título de un video de YouTube sin tocar el reproductor (oEmbed
    público): sirve aunque YouTube esté bloqueando la reproducción."""
    try:
        import urllib.parse
        import urllib.request
        api = "https://www.youtube.com/oembed?format=json&url=" + urllib.parse.quote(url, safe="")
        with urllib.request.urlopen(api, timeout=6) as r:
            return json.loads(r.read().decode("utf-8")).get("title")
    except Exception:
        return None


def _extract_one(opts: dict, query: str) -> dict:
    with yt_dlp.YoutubeDL(_opts(opts)) as ydl:
        info = ydl.extract_info(query, download=False)
        if info and "entries" in info:
            entries = [e for e in (info.get("entries") or []) if e]
            if not entries:
                raise RuntimeError("sin resultados")
            info = entries[0]
        return {
            "title": info.get("title", "Sin título"),
            "webpage_url": info.get("webpage_url") or query,
            "stream_url": info["url"],
            "http_headers": info.get("http_headers") or {},
            "resolved_at": time.time(),
            "duration": info.get("duration"),
            "art_url": _best_thumb(info),
            "uploader": info.get("uploader") or info.get("channel"),
        }


def _extract_sync(query: str, title_hint: str | None = None) -> dict:
    """Preparar UNA canción (yt-dlp). Corre en un proceso aparte (ver
    _extract_pool): así el trabajo pesado no le quita fuerza a la música que
    está sonando."""
    try:
        return _extract_one(YTDL_OPTS, query)
    except Exception as yt_err:
        if "soundcloud.com" in query:
            raise
        terms = title_hint or (None if _is_url(query) else query)
        if not terms and "youtu" in query:
            terms = _youtube_title(query)
        if not terms:
            raise
        log.warning("YouTube no dejó sacar '%s' (%s). Probando en SoundCloud...", terms, str(yt_err)[:120])
        try:
            data = _extract_one(YTDL_OPTS, f"scsearch1:{terms}")
        except Exception:
            raise yt_err
        data["source"] = "soundcloud"
        return data


def _worker_init():
    # prioridad baja: si la VM está justa, primero va el audio que suena
    try:
        os.nice(10)
    except Exception:
        pass
