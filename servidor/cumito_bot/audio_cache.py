"""
Canciones bajadas al disco de la VM antes de sonar.

Antes FFmpeg leía la canción directo de YouTube mientras sonaba. YouTube
corta esas conexiones largas ("Connection reset by peer" en ffmpeg.log) y
cada corte se escuchaba como un trabón. Ahora la canción se baja completa
(en pedazos de 4 MB, como hace yt-dlp, que YouTube no corta) y suena desde el
disco: si internet tiembla, la música no se entera.

Las que vienen en la cola se bajan en segundo plano, de a una. Se guardan
hasta ~1.5 GB; al pasarse se borran las que llevan más tiempo sin sonar.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import urllib.request
from pathlib import Path

log = logging.getLogger("cumito.cache")

DIR = Path(__file__).resolve().parent.parent / "cache_audio"
CHUNK = 4 << 20                 # 4 MB por pedido
MAX_FILE = 200 << 20            # una sola canción de más de 200 MB no se baja (suena directo)
MAX_TOTAL = 1536 << 20          # tope de todo el caché
_tasks: dict[str, asyncio.Task] = {}
_bg = asyncio.Semaphore(1)      # en segundo plano, de a una


def _key(track) -> str | None:
    url = track.get("webpage_url") or ""
    return hashlib.sha1(url.encode()).hexdigest()[:20] if url else None


def _cacheable(track) -> bool:
    u = track.get("stream_url") or ""
    # los en vivo y los que vienen en "manifiesto" (m3u8 / dash) no son un archivo
    return u.startswith("http") and "manifest" not in u and ".m3u8" not in u and not track.get("is_live")


def ready_path(track) -> Path | None:
    k = _key(track)
    if not k:
        return None
    p = DIR / f"{k}.audio"
    if p.exists():
        try:
            p.touch()   # recién usada: la última en borrarse
        except OSError:
            pass
        return p
    return None


def _download(url: str, headers: dict, dest: Path):
    hdr = {k: v for k, v in (headers or {}).items() if v and k.lower() != "accept-encoding"}
    part = dest.with_suffix(".part")
    pos, total = 0, None
    with open(part, "wb") as f:
        while total is None or pos < total:
            req = urllib.request.Request(url, headers={**hdr, "Range": f"bytes={pos}-{pos + CHUNK - 1}"})
            for attempt in range(5):
                try:
                    with urllib.request.urlopen(req, timeout=20) as r:
                        whole = r.status == 200          # no aceptó pedazos: mandó todo
                        if total is None and not whole:
                            cr = r.headers.get("Content-Range", "")
                            if "/" in cr and not cr.endswith("*"):
                                total = int(cr.rsplit("/", 1)[1])
                        if total and total > MAX_FILE:
                            raise ValueError("muy grande")
                        data = r.read()
                    break
                except ValueError:
                    raise
                except Exception:
                    if attempt == 4:
                        raise
                    time.sleep(1 + attempt)
            if not data:
                break
            f.write(data)
            pos += len(data)
            if whole or total is None:
                total = pos
    part.replace(dest)


def _prune():
    try:
        files = sorted(DIR.glob("*.audio"), key=lambda p: p.stat().st_mtime)
        size = sum(p.stat().st_size for p in files)
        while files and size > MAX_TOTAL:
            p = files.pop(0)
            size -= p.stat().st_size
            p.unlink(missing_ok=True)
    except Exception:
        log.exception("No se pudo limpiar el caché de audio")


def startup():
    DIR.mkdir(exist_ok=True)
    for p in DIR.glob("*.part"):
        p.unlink(missing_ok=True)
    _prune()


async def fetch(track, urgent=False) -> Path | None:
    """Baja la canción (si no estaba). Devuelve la ruta, o None si no se pudo."""
    if ready_path(track):
        return ready_path(track)
    k = _key(track)
    if not k or not _cacheable(track):
        return None
    task = _tasks.get(k)
    if task is None or task.done():
        url, headers = track["stream_url"], dict(track.get("http_headers") or {})
        title = track.get("title")

        async def run():
            if not urgent:
                async with _bg:
                    return await go()
            return await go()

        async def go():
            if ready_path(track):
                return ready_path(track)
            DIR.mkdir(exist_ok=True)
            dest = DIR / f"{k}.audio"
            t0 = time.monotonic()
            try:
                await asyncio.to_thread(_download, url, headers, dest)
            except Exception as e:
                dest.with_suffix(".part").unlink(missing_ok=True)
                log.info("No se bajó '%s' (sonará directo): %s", title, str(e)[:100])
                return None
            log.info("Bajada '%s' (%.1f MB en %.1f s)", title, dest.stat().st_size / 1e6, time.monotonic() - t0)
            await asyncio.to_thread(_prune)
            return dest

        task = _tasks[k] = asyncio.create_task(run())
        task.add_done_callback(lambda _t, k=k: _tasks.pop(k, None) if _tasks.get(k) is _t else None)
    try:
        return await asyncio.shield(task)
    except Exception:
        return None
