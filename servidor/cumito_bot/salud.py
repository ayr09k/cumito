"""
Salud del servidor (se ve en Cumito -> Opciones -> Estado del servidor).

Mide cada 2 segundos, leyendo lo que Linux ya anota en /proc (no cuesta
casi nada): uso de procesador, cuánto le "roba" Oracle (steal: cuando la VM
gratis está al límite), memoria, swap, disco, carga y cuánto lleva prendida.
Además guarda los últimos mensajes del registro (avisos y errores) para
mostrarlos en la app.
"""
from __future__ import annotations

import asyncio
import logging
import os
import shutil
import time
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent   # la carpeta del servidor
SAMPLE_S = 2.0
HISTORY = 90          # 3 minutos de historia


def _read(path):
    try:
        return Path(path).read_text()
    except Exception:
        return ""


class LogBuffer(logging.Handler):
    """Los últimos mensajes del registro, para verlos desde la app."""

    def __init__(self, size=80):
        super().__init__(level=logging.INFO)
        self.items = deque(maxlen=size)

    def emit(self, record):
        try:
            msg = record.getMessage()
            if record.exc_info and record.levelno >= logging.ERROR:
                msg += " · " + str(record.exc_info[1])[:160]
            name = record.name.replace("cumito.", "")
            # el ruido de Discord/websockets no aporta
            if record.levelno < logging.WARNING and not record.name.startswith("cumito"):
                return
            self.items.append({"t": record.created, "lvl": record.levelname, "src": name, "msg": msg[:300]})
        except Exception:
            pass


class Salud:
    def __init__(self):
        self.cpu_hist = deque(maxlen=HISTORY)
        self.steal_hist = deque(maxlen=HISTORY)
        self._prev = None
        self.started = time.time()
        self.logs = LogBuffer()
        logging.getLogger().addHandler(self.logs)

    # ---- medir ----
    def _cpu_times(self):
        line = _read("/proc/stat").split("\n", 1)[0].split()
        if not line or line[0] != "cpu":
            return None
        v = [int(x) for x in line[1:]]
        idle = v[3] + (v[4] if len(v) > 4 else 0)
        steal = v[7] if len(v) > 7 else 0
        return sum(v[:8]), idle, steal

    def sample(self):
        now = self._cpu_times()
        if now and self._prev:
            dt = now[0] - self._prev[0]
            if dt > 0:
                busy = 1 - (now[1] - self._prev[1]) / dt
                steal = (now[2] - self._prev[2]) / dt
                self.cpu_hist.append(round(max(0.0, min(1.0, busy)) * 100, 1))
                self.steal_hist.append(round(max(0.0, min(1.0, steal)) * 100, 1))
        self._prev = now

    async def run(self):
        while True:
            try:
                self.sample()
            except Exception:
                pass
            await asyncio.sleep(SAMPLE_S)

    # ---- armar el resumen ----
    @staticmethod
    def _meminfo():
        out = {}
        for line in _read("/proc/meminfo").splitlines():
            k, _, rest = line.partition(":")
            try:
                out[k] = int(rest.split()[0]) * 1024
            except Exception:
                pass
        return out

    @staticmethod
    def _proc_rss(pid):
        for line in _read(f"/proc/{pid}/status").splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1]) * 1024
        return 0

    def _helpers_rss(self):
        """Memoria de los "ayudantes" que preparan canciones (procesos hijos)."""
        total, n = 0, 0
        me = str(os.getpid())
        for d in Path("/proc").iterdir() if Path("/proc").exists() else []:
            if not d.name.isdigit():
                continue
            st = _read(d / "stat").split()
            if len(st) > 3 and st[3] == me:
                total += self._proc_rss(d.name)
                n += 1
        return total, n

    def snapshot(self, bot, relay):
        mem = self._meminfo()
        mem_total = mem.get("MemTotal", 0)
        mem_avail = mem.get("MemAvailable", 0)
        swap_total = mem.get("SwapTotal", 0)
        swap_used = swap_total - mem.get("SwapFree", 0)
        try:
            du = shutil.disk_usage(str(HERE))
            disk = {"total": du.total, "used": du.used}
        except Exception:
            disk = {"total": 0, "used": 0}
        load = _read("/proc/loadavg").split()[:3]
        up = _read("/proc/uptime").split()
        helpers_rss, helpers_n = self._helpers_rss()

        guild = bot.client.get_guild(bot.guild_id) if bot.ready.is_set() else None
        vc = guild.voice_client if guild else None
        try:
            ping = bot.client.latency
            ping = None if ping is None or ping != ping or ping == float("inf") else round(ping * 1000)
        except Exception:
            ping = None
        try:
            import yt_dlp
            ytv = yt_dlp.version.__version__
        except Exception:
            ytv = "?"
        version = _read(HERE / ".version").strip() or "sin dato"
        pend = HERE / ".actualizacion_pendiente"
        queue = list(bot.queue)
        return {
            "cpu": self.cpu_hist[-1] if self.cpu_hist else None,
            "cpu_hist": list(self.cpu_hist),
            "steal": self.steal_hist[-1] if self.steal_hist else None,
            "steal_hist": list(self.steal_hist),
            "cores": os.cpu_count(),
            "load": [float(x) for x in load] if load else None,
            "mem": {"total": mem_total, "used": max(0, mem_total - mem_avail)},
            "swap": {"total": swap_total, "used": max(0, swap_used)},
            "disk": disk,
            "uptime_vm": float(up[0]) if up else None,
            "uptime_bot": time.time() - self.started,
            "bot_rss": self._proc_rss(os.getpid()),
            "helpers": {"n": helpers_n, "rss": helpers_rss},
            "discord": {"ready": bot.ready.is_set(), "ping": ping,
                        "voice": getattr(getattr(vc, "channel", None), "name", None) if vc else None},
            "listeners": relay.member_count,
            "queue": {"total": len(queue), "prepared": sum(1 for t in queue if t.get("prepared")),
                      "loading": sum(1 for t in queue if t.get("loading")),
                      "failed": sum(1 for t in queue if t.get("failed"))},
            "playing": (bot.current or {}).get("title"),
            "versions": {"server": version, "yt_dlp": ytv},
            "update_pending": pend.exists(),
            "logs": list(self.logs.items)[-40:],
            "time": time.time(),
        }
