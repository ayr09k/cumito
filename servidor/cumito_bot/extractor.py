"""
Lo que prepara las canciones (yt-dlp), separado del bot: corre en procesos
"ayudantes" aparte (ver lanes.py) que no cargan Discord, así ocupan
poca memoria y el trabajo pesado no traba la música que está sonando.
"""
from __future__ import annotations

import json
import logging
import os
import re
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


SEARCH_PREFIX = "busca:"   # canción conocida solo por "artista - título" (p. ej. de Spotify)


def _resolve_search(terms: str) -> str:
    """'artista - título' -> el enlace de YouTube de su versión de audio
    (sección Canciones de YouTube Music). Si no, la primera de YouTube."""
    try:
        rows = _music_search(terms, 1)
        if rows:
            return rows[0]["webpage_url"]
    except Exception:
        pass
    return f"ytsearch1:{terms}"


def _extract_sync(query: str, title_hint: str | None = None) -> dict:
    """Preparar UNA canción (yt-dlp). Corre en un proceso aparte (ver
    lanes.py): así el trabajo pesado no le quita fuerza a la música que
    está sonando."""
    if query.startswith(SEARCH_PREFIX):
        terms = query[len(SEARCH_PREFIX):].strip()
        title_hint = title_hint or terms
        query = _resolve_search(terms)
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


# ---------------------------------------------------------------------------
# Búsquedas y playlists (también corren en los ayudantes)
# ---------------------------------------------------------------------------
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


def ytmusic():
    global _ytmusic
    if _ytmusic is None:
        from ytmusicapi import YTMusic
        _ytmusic = YTMusic()
    return _ytmusic


def _artists(r) -> str | None:
    return ", ".join(a.get("name") for a in (r.get("artists") or []) if a.get("name")) or None


def _ym_art(thumbs, vid=None):
    art = thumbs[-1]["url"] if thumbs else (f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg" if vid else None)
    # las portadas de YouTube Music se pueden pedir más grandes
    return re.sub(r"=w\d+-h\d+", "=w400-h400", art) if art else None


def _parse_len(v):
    """'3:45' -> 225"""
    if isinstance(v, (int, float)):
        return int(v)
    try:
        n = 0
        for part in str(v).split(":"):
            n = n * 60 + int(part)
        return n
    except Exception:
        return None


def _music_search(query: str, limit: int) -> list[dict]:
    """Buscar como YouTube Music, en su sección "Canciones": ahí salen las
    versiones de audio oficiales (no el videoclip, ni covers, ni en vivo).
    Usa ytmusicapi (trae artista, duración y portada cuadrada); si no está o
    falla, usa yt-dlp, que solo trae el nombre."""
    try:
        rows = ytmusic().search(query, filter="songs", limit=max(1, min(limit, 60)))
        out = []
        for r in rows:
            vid = r.get("videoId")
            if not vid:
                continue
            out.append({
                "title": r.get("title") or "Sin título",
                "webpage_url": f"https://www.youtube.com/watch?v={vid}",
                "duration": r.get("duration_seconds"),
                "uploader": _artists(r),
                "art_url": _ym_art(r.get("thumbnails") or [], vid),
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


def search_sync(query: str, limit: int, offset: int, kind: str) -> list[dict]:
    """Varios resultados livianos para el mosaico del buscador. Si YouTube
    no responde, busca en SoundCloud. offset: para "Buscar más"."""
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


def playlist_sync(url: str, limit: int):
    """Las canciones de una playlist (solo lo liviano) y su nombre."""
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


def video_id(url: str | None) -> str | None:
    m = re.search(r"(?:v=|youtu\.be/|/shorts/)([A-Za-z0-9_-]{11})", url or "")
    return m.group(1) if m else None


def radio_sync(seed_url: str, limit: int = 10, skip: tuple = ()) -> list[dict]:
    """La "radio" de YouTube Music a partir de una canción: canciones
    parecidas, para que la música no se acabe cuando se vacía la lista."""
    vid = video_id(seed_url)
    if not vid:
        return []
    data = ytmusic().get_watch_playlist(videoId=vid, limit=limit + 5, radio=True)
    skip = set(skip) | {vid}
    out = []
    for r in data.get("tracks") or []:
        v = r.get("videoId")
        if not v or v in skip:
            continue
        skip.add(v)
        out.append({
            "title": r.get("title") or "Sin título",
            "webpage_url": f"https://www.youtube.com/watch?v={v}",
            "duration": _parse_len(r.get("length")),
            "uploader": _artists(r),
            "art_url": _ym_art(r.get("thumbnail") or r.get("thumbnails") or [], v),
        })
        if len(out) >= limit:
            break
    return out
