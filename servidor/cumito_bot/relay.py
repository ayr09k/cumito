"""
RelayServer: el puente entre las apps Cumito del grupo y el bot de
Discord. Recibe sus comandos (play/pausa/skip...) y les manda el estado
actual (qué suena, la cola, quién hostea) cada vez que algo cambia. No
pasa audio, solo texto: la música sigue sonando en el canal de voz de
Discord como siempre.
"""
import asyncio
import json
import logging

import websockets

log = logging.getLogger("cumito.relay")


class RelayServer:
    def __init__(self, port, on_command):
        self.port = port
        self.on_command = on_command  # async def on_command(dict, display_name, websocket)
        self._clients = {}  # websocket -> nombre mostrado
        self._caps = {}     # websocket -> lo que entiende esa app (la del celular 3.0 manda "m3")
        self._server = None
        self._last_state = {
            "type": "state", "host_label": "", "now_playing": None,
            "queue": [], "members": [], "volume": None, "recent": [],
        }

    async def start(self):
        # max_size: las portadas de los Discos viajan como imagen (hasta ~6 MB)
        self._server = await websockets.serve(self._handle, "0.0.0.0", self.port, ping_interval=20,
                                              max_size=8 * 1024 * 1024)
        log.info("Relay escuchando en el puerto %s", self.port)

    async def stop(self):
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    @property
    def member_count(self):
        return len(self._clients)

    async def _handle(self, ws):
        name = "Invitado"
        self._clients[ws] = name
        try:
            await ws.send(json.dumps(self._last_state))
            async for raw in ws:
                try:
                    data = json.loads(raw)
                except Exception:
                    continue
                if data.get("type") == "hello":
                    name = str(data.get("name") or "Invitado")[:32]
                    self._clients[ws] = name
                    caps = data.get("caps")
                    self._caps[ws] = {str(c)[:16] for c in caps[:10]} if isinstance(caps, list) else set()
                elif data.get("type") == "command":
                    try:
                        await self.on_command(data, self._clients.get(ws, "Invitado"), ws)
                    except Exception:
                        log.exception("Error manejando comando del cliente")
        except websockets.ConnectionClosed:
            pass
        finally:
            self._clients.pop(ws, None)
            self._caps.pop(ws, None)

    async def send_cap(self, cap, raw, names=None):
        """Un mensaje solo para las apps que lo entienden (cap), y si se dan
        nombres, solo para esas personas (en todos sus celulares)."""
        n = 0
        for ws, name in list(self._clients.items()):
            if cap not in self._caps.get(ws, ()):
                continue
            if names is not None and name not in names:
                continue
            try:
                await ws.send(raw)
                n += 1
            except Exception:
                pass
        return n

    async def broadcast_state(self, host_label, now_playing, queue, members=None, volume=None, recent=None,
                              **extra):
        members = members if members is not None else list(self._clients.values())
        self._last_state = {
            "type": "state",
            "host_label": host_label,
            "now_playing": now_playing,
            "queue": queue,
            "members": members,
            "volume": volume,
            "recent": recent or [],
            **extra,
        }
        raw = json.dumps(self._last_state)
        dead = []
        for ws in list(self._clients.keys()):
            try:
                await ws.send(raw)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._clients.pop(ws, None)
