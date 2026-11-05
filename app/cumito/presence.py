"""
"Escuchando en Cumito" en tu perfil de Discord (Rich Presence).

Habla con la app de Discord de la computadora por su canal local (un "named
pipe" de Windows), sin librerías extra. Si Discord no está abierto, lo
vuelve a intentar cada tanto sin molestar. El nombre que sale ("Escuchando
a ...") es el del bot de Cumito: el servidor manda su ID en el estado.

Discord deja cambiar la actividad pocas veces por minuto, así que solo se
manda cuando cambia la canción o la pausa, y nunca más de una vez cada 4 s.
"""
from __future__ import annotations

import json
import os
import struct
import sys
import threading
import time
import uuid

RETRY_S = 20
MIN_GAP_S = 4.0


class DiscordPresence:
    def __init__(self):
        self.enabled = True
        self._client_id = None
        self._want = None          # la actividad que debería verse (o None = nada)
        self._sent_key = "-"       # lo último que se mandó ("-" = nada todavía)
        self._pipe = None
        self._cv = threading.Condition()
        self._last_send = 0.0
        self._stop = False
        if sys.platform == "win32":
            threading.Thread(target=self._run, daemon=True, name="cumito-presence").start()

    # ---------- lo que usa la ventana ----------
    def set_client_id(self, cid):
        cid = str(cid or "").strip()
        if not cid.isdigit() or cid == self._client_id:
            return
        with self._cv:
            self._client_id = cid
            self._close()
            self._cv.notify()

    def set_track(self, np: dict | None, elapsed: float = 0.0):
        """np = now_playing del estado (o None)."""
        act = None
        if np and self.enabled:
            title = (np.get("title") or "Sin título")[:120]
            artist = (np.get("uploader") or "").strip()
            act = {"type": 2, "details": title, "status_display_type": 2,
                   "assets": {"large_text": "Cumito"}, "instance": False}
            if np.get("art_url", "").startswith("https://"):
                act["assets"]["large_image"] = np["art_url"][:300]
            if np.get("paused"):
                act["state"] = "En pausa"
            else:
                act["state"] = (f"de {artist}" if artist else "en Cumito")[:120]
                dur = np.get("duration") or 0
                start = time.time() - float(elapsed or 0)
                act["timestamps"] = {"start": int(start * 1000)}
                if dur:
                    act["timestamps"]["end"] = int((start + dur) * 1000)
        key = json.dumps(act, sort_keys=True, default=str) if act else None
        # el reloj se corre un poquito en cada estado: no cuenta como cambio
        if act and act.get("timestamps") and self._want:
            old = self._want.get("timestamps") or {}
            if abs(old.get("start", 0) - act["timestamps"]["start"]) < 4000 and \
                    {k: v for k, v in self._want.items() if k != "timestamps"} == \
                    {k: v for k, v in act.items() if k != "timestamps"}:
                return
        with self._cv:
            if key != self._key(self._want):
                self._want = act
                self._cv.notify()

    def set_enabled(self, on):
        self.enabled = bool(on)
        if not on:
            with self._cv:
                self._want = None
                self._cv.notify()

    def stop(self):
        with self._cv:
            self._stop = True
            self._want = None
            self._cv.notify()

    # ---------- el hilo que habla con Discord ----------
    def _frame(self, op, payload):
        data = json.dumps(payload).encode("utf-8")
        self._pipe.write(struct.pack("<II", op, len(data)) + data)
        self._pipe.flush()
        head = self._pipe.read(8)
        if len(head) < 8:
            raise OSError("Discord cerró")
        _op, n = struct.unpack("<II", head)
        return json.loads(self._pipe.read(n) or b"{}")

    def _connect(self):
        for i in range(10):
            try:
                self._pipe = open(rf"\\.\pipe\discord-ipc-{i}", "r+b", buffering=0)
                break
            except OSError:
                self._pipe = None
        if self._pipe is None:
            return False
        try:
            self._frame(0, {"v": 1, "client_id": self._client_id})
            self._sent_key = "-"
            return True
        except Exception:
            self._close()
            return False

    def _close(self):
        try:
            if self._pipe:
                self._pipe.close()
        except Exception:
            pass
        self._pipe = None

    @staticmethod
    def _key(act):
        return json.dumps(act, sort_keys=True, default=str) if act else None

    def _run(self):
        while True:
            with self._cv:
                while not self._stop and (self._client_id is None or self._key(self._want) == self._sent_key):
                    self._cv.wait(RETRY_S)
                if self._stop:
                    self._close()
                    return
            gap = MIN_GAP_S - (time.monotonic() - self._last_send)
            if gap > 0:
                time.sleep(gap)
            with self._cv:
                want = self._want
            if self._pipe is None:
                if want is None:
                    self._sent_key = None   # nada que borrar: Discord no está
                    continue
                if not self._connect():
                    time.sleep(RETRY_S)
                    continue
            try:
                self._frame(1, {"cmd": "SET_ACTIVITY", "nonce": str(uuid.uuid4()),
                                "args": {"pid": os.getpid(), "activity": want}})
                self._sent_key = self._key(want)
                self._last_send = time.monotonic()
            except Exception:
                self._close()
                time.sleep(3)
