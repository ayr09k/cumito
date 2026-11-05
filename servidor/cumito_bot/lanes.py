"""
Los tres "carriles" de trabajo del servidor, para que una cosa no trabe a
la otra (la VM tiene muy poco procesador):

  1. Audio: lo que suena por Discord. No pasa por aquí: corre aparte (FFmpeg
     + el hilo de voz de discord.py) y nunca espera a nadie.
  2. Pesado (yt-dlp): dos "ayudantes" en procesos aparte, con prioridad baja.
       - urgente: lo que alguien está esperando (poner una canción, saltar a
         una no preparada, buscar, abrir una playlist);
       - fondo: dejar listas las que siguen, la radio, los Discos.
     Así lo urgente nunca hace fila detrás de una playlist de 200.
  3. Liviano (internet): letras, Spotify, sugerencias de radio. Son esperas
     de red: van varias a la vez en hilos, sin gastar procesador.
"""
from __future__ import annotations

import asyncio
import logging
import multiprocessing
import time
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool

log = logging.getLogger("cumito.lanes")

LIGHT_MAX = 4          # cuántas consultas de internet a la vez
LIGHT_TIMEOUT_S = 25   # una consulta liviana que tarda más que esto se abandona


class Lanes:
    def __init__(self):
        self._pools: dict[str, ProcessPoolExecutor | None] = {"urgent": None, "background": None}
        self._busy = {"urgent": 0, "background": 0}
        self._light_sem: asyncio.Semaphore | None = None
        self.light_busy = 0
        self.done = {"urgent": 0, "background": 0, "light": 0}
        self.last_ms = {"urgent": None, "background": None, "light": None}

    # ---------- pesado (procesos ayudantes) ----------
    def _pool(self, name):
        if self._pools[name] is None:
            from .extractor import _worker_init
            self._pools[name] = ProcessPoolExecutor(
                max_workers=1, mp_context=multiprocessing.get_context("spawn"), initializer=_worker_init)
        return self._pools[name]

    def _pick(self, urgent):
        if not urgent:
            return "background"
        # lo urgente usa su ayudante; si ese está ocupado y el de fondo está
        # libre, toma el de fondo (nunca al revés: el urgente se guarda libre)
        if self._busy["urgent"] and not self._busy["background"]:
            return "background"
        return "urgent"

    async def heavy(self, fn, *args, urgent=False):
        name = self._pick(urgent)
        loop = asyncio.get_running_loop()
        self._busy[name] += 1
        t0 = time.monotonic()
        try:
            for attempt in (1, 2):
                try:
                    return await loop.run_in_executor(self._pool(name), fn, *args)
                except BrokenProcessPool:
                    log.warning("El ayudante '%s' se cayó; lo reinicio", name)
                    self._pools[name] = None
                    if attempt == 2:
                        # último recurso: en un hilo de este mismo proceso
                        return await loop.run_in_executor(None, fn, *args)
        finally:
            self._busy[name] -= 1
            self.done[name] += 1
            self.last_ms[name] = round((time.monotonic() - t0) * 1000)

    # ---------- liviano (hilos, esperas de red) ----------
    async def light(self, fn, *args, timeout=LIGHT_TIMEOUT_S):
        if self._light_sem is None:
            self._light_sem = asyncio.Semaphore(LIGHT_MAX)
        loop = asyncio.get_running_loop()
        async with self._light_sem:
            self.light_busy += 1
            t0 = time.monotonic()
            try:
                return await asyncio.wait_for(loop.run_in_executor(None, fn, *args), timeout)
            finally:
                self.light_busy -= 1
                self.done["light"] += 1
                self.last_ms["light"] = round((time.monotonic() - t0) * 1000)

    def snapshot(self):
        return {
            "urgent": {"busy": self._busy["urgent"], "done": self.done["urgent"], "ms": self.last_ms["urgent"]},
            "background": {"busy": self._busy["background"], "done": self.done["background"],
                           "ms": self.last_ms["background"]},
            "light": {"busy": self.light_busy, "done": self.done["light"], "ms": self.last_ms["light"]},
        }

    def shutdown(self):
        for name, p in self._pools.items():
            if p is not None:
                p.shutdown(wait=False, cancel_futures=True)
                self._pools[name] = None


LANES = Lanes()
