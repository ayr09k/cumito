"""
RelayClient: con esto Cumito habla con el servidor. Se reconecta solo si
el servidor se reinicia o la red falla.
"""
import asyncio
import json
import logging

import websockets

from . import protocol

log = logging.getLogger("cumito.relay_client")


class RelayClient:
    def __init__(self, uri, name, on_state, on_connection_change):
        self.uri = uri
        self.name = name
        self.on_state = on_state                      # callback(dict) hilo asyncio
        self.on_connection_change = on_connection_change  # callback(bool conectado)
        self._ws = None
        self._stop = False

    async def run(self):
        while not self._stop:
            try:
                async with websockets.connect(self.uri, open_timeout=6, ping_interval=20) as ws:
                    self._ws = ws
                    await ws.send(protocol.hello(self.name))
                    self.on_connection_change(True)
                    async for raw in ws:
                        try:
                            data = json.loads(raw)
                        except Exception:
                            continue
                        self.on_state(data)
            except Exception:
                pass
            self._ws = None
            self.on_connection_change(False)
            if self._stop:
                break
            await asyncio.sleep(3)

    async def send_command(self, action, **kw):
        if self._ws is None:
            return False
        try:
            await self._ws.send(protocol.command(action, **kw))
            return True
        except Exception:
            return False

    def stop(self):
        self._stop = True
