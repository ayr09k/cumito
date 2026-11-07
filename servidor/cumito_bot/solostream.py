"""
Modo solo como UNA transmisión continua (como una radio por internet).

Antes el celular cambiaba de archivo en cada canción. Con la pantalla apagada
el teléfono (sobre todo el iPhone) congela la app y no deja empezar la
siguiente: la música se quedaba parada al terminar cada canción.

Ahora el celular abre una sola transmisión de audio (/solo/stream?...) y el
servidor le va pegando las canciones una tras otra, sin cortes. Para el
teléfono es una sola "canción" infinita, así que sigue sonando aunque la app
esté dormida. Por el WebSocket se le avisa en qué segundo de la transmisión
empieza cada canción (solo_seg), para que la pantalla muestre la correcta.

Cada canción se convierte UNA vez a AAC "ADTS" (cuadros sueltos que se
pueden pegar uno detrás de otro): si ya viene en m4a solo se reempaca, sin
recodificar, así que casi no gasta procesador.

Se manda hasta AHEAD_S segundos adelantado y después al ritmo de la música,
así los cambios en la lista (quitar, reordenar) alcanzan a aplicarse.
"""
from __future__ import annotations

import asyncio
import itertools
import logging
import secrets
import time
import urllib.parse
from pathlib import Path

from . import audio_cache
from .extractor import radio_sync, video_id
from .lanes import LANES

log = logging.getLogger("cumito.solo")

PORT = 8766
AHEAD_S = 20
CHUNK_S = 1.0
SESSION_IDLE_S = 8 * 3600
RADIO_UID0 = 1_000_000
SR_TABLE = [96000, 88200, 64000, 48000, 44100, 32000, 24000, 22050, 16000, 12000, 11025, 8000, 7350]


def adts_frames(data: bytes) -> list[tuple[int, int, float]]:
    """(posición, largo, segundos) de cada cuadro ADTS."""
    out, i, n = [], 0, len(data)
    while i + 7 <= n:
        if data[i] != 0xFF or (data[i + 1] & 0xF6) != 0xF0:
            i += 1
            continue
        sr_idx = (data[i + 2] >> 2) & 0xF
        flen = ((data[i + 3] & 3) << 11) | (data[i + 4] << 3) | (data[i + 5] >> 5)
        if flen < 7 or i + flen > n or sr_idx >= len(SR_TABLE):
            break
        nfr = (data[i + 6] & 3) + 1
        out.append((i, flen, 1024 * nfr / SR_TABLE[sr_idx]))
        i += flen
    return out


async def to_adts(src: Path) -> Path | None:
    from .bot import ffmpeg_path
    dst = src.with_suffix(".adts")
    if dst.exists() and dst.stat().st_size > 1000:
        return dst
    tmp = src.with_name(src.stem + ".adts.part")
    copy = src.suffix in (".m4a", ".mp4", ".aac")
    remux = ["-c:a", "copy"]
    encode = ["-c:a", "aac", "-b:a", "128k", "-ac", "2", "-ar", "44100"]
    for codec in ((remux, encode) if copy else (encode,)):
        proc = await asyncio.create_subprocess_exec(
            ffmpeg_path(), "-loglevel", "error", "-y", "-i", str(src), "-vn", *codec, "-f", "adts", str(tmp),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE)
        _, err = await proc.communicate()
        if proc.returncode == 0 and tmp.exists() and tmp.stat().st_size > 1000:
            tmp.chmod(0o644)
            tmp.replace(dst)
            return dst
        log.info("No se pudo pasar a ADTS (%s): %s", codec[1], (err or b"").decode(errors="replace")[:160])
    tmp.unlink(missing_ok=True)
    return None


class Stream:
    def __init__(self, sess, uid, pos):
        self.id = secrets.token_hex(6)
        self.sess = sess
        self.start_uid = uid
        self.start_pos = pos
        self.closed = False
        self.paused = False
        self.connected = False
        self.cur_uid = None
        self.segs: list[dict] = []


class Session:
    def __init__(self, who):
        self.sid = secrets.token_hex(8)
        self.key = secrets.token_hex(12)
        self.who = who
        self.ws = None
        self.plan: list[dict] = []
        self.repeat = "off"
        self.radio = False
        self.follow = None          # a quién está siguiendo ("sala"), o None
        self.stream: Stream | None = None
        self.touched = time.time()
        self.prep: dict[str, asyncio.Task] = {}
        self.radio_task: asyncio.Task | None = None
        self.next_uid = itertools.count(RADIO_UID0)


class SoloStreams:
    def __init__(self, solo, reply):
        self.solo = solo            # Solo: bajar canciones, presencia, recomendaciones
        self.reply = reply          # async (ws, tipo, **datos)
        self.sessions: dict[str, Session] = {}

    # ---------- servidor HTTP mínimo (Caddy le pasa /solo/...) ----------
    async def start(self):
        try:
            self.server = await asyncio.start_server(self._http, "127.0.0.1", PORT)
            log.info("Transmisión del modo solo lista en el puerto %s", PORT)
        except OSError as e:
            log.warning("No pude abrir el puerto %s para el modo solo: %s", PORT, e)
        asyncio.create_task(self._sweep())

    async def _sweep(self):
        while True:
            await asyncio.sleep(600)
            now = time.time()
            for sid, s in list(self.sessions.items()):
                if now - s.touched > SESSION_IDLE_S and not (s.stream and s.stream.connected):
                    self.sessions.pop(sid, None)

    async def _http(self, reader, writer):
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 10)
            line = head.split(b"\r\n", 1)[0].decode("latin-1")
            method, target = line.split(" ")[:2]
            u = urllib.parse.urlsplit(target)
            q = dict(urllib.parse.parse_qsl(u.query))
            sess = self.sessions.get(q.get("s", ""))
            st = sess.stream if sess else None
            if method not in ("GET", "HEAD") or not u.path.startswith("/solo/stream") or not sess \
                    or not secrets.compare_digest(q.get("k", ""), sess.key) or not st or st.id != q.get("st"):
                writer.write(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                await writer.drain()
                return
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: audio/aac\r\nCache-Control: no-store\r\n"
                         b"Connection: close\r\nX-Accel-Buffering: no\r\n\r\n")
            await writer.drain()
            if method == "HEAD":
                return
            if st.connected:   # el navegador abrió otra conexión a la misma: la vieja se suelta
                st.closed = True
                st = self._new_stream(sess, st.start_uid, st.start_pos, reuse=st)
            await self._pump(sess, st, writer)
        except (asyncio.IncompleteReadError, asyncio.TimeoutError, ConnectionError, ValueError):
            pass
        except Exception:
            log.exception("Transmisión del modo solo")
        finally:
            try:
                writer.close()
            except Exception:
                pass

    # ---------- órdenes del celular ----------
    def _session(self, sid, who, ws):
        s = self.sessions.get(sid or "")
        if s is None or s.who != who:
            s = Session(who)
            self.sessions[s.sid] = s
        s.ws = ws
        s.touched = time.time()
        return s

    def _set_plan(self, s, d):
        items = []
        for it in d.get("items") or []:
            if isinstance(it, dict) and it.get("webpage_url") and it.get("uid") is not None:
                items.append({k: it.get(k) for k in ("uid", "webpage_url", "title", "uploader", "duration", "art_url")})
        s.plan = items[:500]
        s.repeat = d.get("repeat") if d.get("repeat") in ("off", "all", "one") else "off"
        s.radio = bool(d.get("radio"))
        if "with" in d:
            s.follow = str(d.get("with"))[:40] if d.get("with") else None
        # lo que viene se va preparando ya
        if s.stream and s.stream.cur_uid is not None:
            self._prep_after(s, s.stream.cur_uid, 2)

    def _new_stream(self, s, uid, pos, reuse=None):
        if s.stream and s.stream is not reuse:
            s.stream.closed = True
        st = Stream(s, uid, pos)
        if reuse is not None:
            st.id = reuse.id
        s.stream = st
        return st

    async def play(self, who, ws, d):
        s = self._session(d.get("sid"), who, ws)
        self._set_plan(s, d)
        uid = d.get("uid")
        if not any(it["uid"] == uid for it in s.plan):
            uid = s.plan[0]["uid"] if s.plan else None
        if uid is None:
            return
        st = self._new_stream(s, uid, max(0.0, float(d.get("pos") or 0)))
        self._prep_uid(s, uid)
        self._prep_after(s, uid, 1)
        await self.reply(ws, "solo_stream", req=d.get("req"), sid=s.sid, stream=st.id,
                         url=f"/solo/stream?s={s.sid}&k={s.key}&st={st.id}")

    def plan(self, who, ws, d):
        s = self.sessions.get(d.get("sid") or "")
        if s and s.who == who:
            s.ws = ws
            s.touched = time.time()
            self._set_plan(s, d)

    def pause(self, who, d, paused):
        s = self.sessions.get(d.get("sid") or "")
        if not s or s.who != who or not s.stream:
            return
        s.stream.paused = paused
        cur = self._item(s, s.stream.cur_uid)
        if cur:
            asyncio.create_task(self.solo.status(who, {"track": cur, "elapsed": float(d.get("elapsed") or 0), "paused": paused, "with": s.follow}))

    def stop(self, who, d):
        s = self.sessions.get(d.get("sid") or "")
        if s and s.who == who and s.stream:
            s.stream.closed = True

    # ---------- preparar canciones ----------
    def _item(self, s, uid):
        return next((it for it in s.plan if it["uid"] == uid), None)

    def _next_item(self, s, uid):
        if s.repeat == "one":
            it = self._item(s, uid)
            if it:
                return it
        idx = next((i for i, it in enumerate(s.plan) if it["uid"] == uid), None)
        if idx is not None and idx + 1 < len(s.plan):
            return s.plan[idx + 1]
        if idx is None and s.plan:
            return s.plan[0]
        if s.repeat == "all" and s.plan:
            return s.plan[0]
        return None

    def _prep_uid(self, s, uid):
        it = self._item(s, uid)
        if not it:
            return None
        url = it["webpage_url"]
        t = s.prep.get(url)
        if t is None or (t.done() and t.result() is None):
            t = s.prep[url] = asyncio.create_task(self._prepare(it))
            if len(s.prep) > 40:
                for k in list(s.prep)[:-30]:
                    if s.prep[k].done():
                        s.prep.pop(k, None)
        return t

    def _prep_after(self, s, uid, n):
        cur = uid
        for _ in range(n):
            nx = self._next_item(s, cur)
            if not nx or nx["uid"] == cur:
                break
            self._prep_uid(s, nx["uid"])
            cur = nx["uid"]

    async def _prepare(self, it):
        try:
            path, info = await self.solo.ensure_file(it["webpage_url"], it.get("title"), pre=True)
            if path is None:
                log.info("Modo solo: no se pudo preparar %s: %s", it.get("title"), info)
                return None
            for k in ("title", "uploader", "duration", "art_url"):
                if info and info.get(k) and not it.get(k):
                    it[k] = info[k]
            return await to_adts(path)
        except Exception:
            log.exception("Modo solo: preparando %s", it.get("title"))
            return None

    async def _radio_more(self, s, last):
        """Se acabó la lista con la radio prendida: más parecidas a la última."""
        seen = {video_id(it["webpage_url"]) for it in s.plan}
        try:
            got = await LANES.light(radio_sync, last["webpage_url"], 10, tuple(v for v in seen if v))
        except Exception as e:
            log.info("Modo solo: radio sin resultados: %s", str(e)[:100])
            return []
        add = []
        for t in got:
            if video_id(t.get("webpage_url")) in seen:
                continue
            add.append({"uid": next(s.next_uid), "webpage_url": t["webpage_url"], "title": t.get("title"),
                        "uploader": t.get("uploader"), "duration": t.get("duration"), "art_url": t.get("art_url"), "radio": True})
            if len(add) >= 8:
                break
        if add:
            s.plan.extend(add)
            await self.reply(s.ws, "solo_plan_add", sid=s.sid, items=add)
        return add

    # ---------- mandar el audio ----------
    async def _pump(self, s, st, writer):
        st.connected = True
        try:
            await self._pump2(s, st, writer)
        finally:
            st.connected = False

    async def _pump2(self, s, st, writer):
        loop = asyncio.get_running_loop()
        sent = 0.0                  # segundos de audio mandados
        clock0 = loop.time()        # reloj de la reproducción (sin contar pausas)
        paused_at = None
        uid, pos = st.start_uid, st.start_pos
        while not st.closed and uid is not None:
            it = self._item(s, uid)
            task = self._prep_uid(s, uid) if it else None
            path = await task if task else None
            if st.closed:
                break
            if path is None:
                # no se pudo esta: se salta a la que sigue
                nx = self._next_item(s, uid) if it else None
                uid, pos = (nx["uid"] if nx and nx["uid"] != uid else None), 0
                continue
            data = await asyncio.to_thread(path.read_bytes)
            frames = await asyncio.to_thread(adts_frames, data)
            skip, acc = 0, 0.0
            while skip < len(frames) and acc + frames[skip][2] <= pos:
                acc += frames[skip][2]
                skip += 1
            st.cur_uid = uid
            seg = {"uid": uid, "t0": round(sent, 3), "base": round(acc, 3)}
            st.segs.append(seg)
            await self.reply(s.ws, "solo_seg", sid=s.sid, stream=st.id, item=it, **seg)
            asyncio.create_task(self.solo.status(s.who, {"track": it, "elapsed": acc, "started": True, "paused": st.paused, "with": s.follow}))
            self._prep_after(s, uid, 2)
            nx_preview = self._next_item(s, uid)
            if s.radio and (nx_preview is None) and s.repeat == "off" and not (s.radio_task and not s.radio_task.done()):
                s.radio_task = asyncio.create_task(self._radio_more(s, it))
            i = skip
            while i < len(frames) and not st.closed:
                # ritmo: hasta AHEAD_S por delante de lo que va sonando
                while not st.closed:
                    now = loop.time()
                    if st.paused:
                        if paused_at is None:
                            paused_at = now
                    elif paused_at is not None:
                        clock0 += now - paused_at
                        paused_at = None
                    if not st.paused and sent < (now - clock0) + AHEAD_S:
                        break
                    await asyncio.sleep(0.25)
                j, dur = i, 0.0
                while j < len(frames) and dur < CHUNK_S:
                    dur += frames[j][2]
                    j += 1
                a, b = frames[i][0], frames[j - 1][0] + frames[j - 1][1]
                t_w = loop.time()
                writer.write(data[a:b])
                await writer.drain()
                waited = loop.time() - t_w
                if waited > 1.0:
                    clock0 += waited   # el celular dejó de leer (pausado por el sistema): no adelantarse
                sent += dur
                i = j
            if st.closed:
                break
            nx = self._next_item(s, uid)
            if nx is None and s.radio and s.repeat == "off":
                if s.radio_task:
                    await s.radio_task
                nx = self._next_item(s, uid)
            uid, pos = (nx["uid"] if nx else None), 0
        if not st.closed:
            await self.reply(s.ws, "solo_end", sid=s.sid, stream=st.id)
            asyncio.create_task(self.solo.status(s.who, {"track": None}))
