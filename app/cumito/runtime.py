"""
CumitoRuntime: conecta la ventana (GlassScreen) con el servidor, corriendo
el cliente de WebSocket en un hilo aparte con su propio loop de asyncio,
para no bloquear la interfaz."""
import asyncio
import queue
import threading

from .relay_client import RelayClient


class CumitoRuntime:
    def __init__(self, host_address, display_name):
        self.events = queue.Queue()   # ("state"|"search_results", dict) | ("connected", bool)
        self._loop = None
        self._thread = None
        self.client = RelayClient(
            f"ws://{host_address}",
            display_name,
            on_state=self._on_message,
            on_connection_change=lambda ok: self.events.put(("connected", ok)),
        )

    def _on_message(self, data):
        # El servidor manda dos tipos de mensaje por este mismo canal: el
        # estado (se difunde solo) y los resultados de una búsqueda propia
        # (respuesta directa). Los separamos por su "type" antes de meterlos
        # en la cola que lee la ventana.
        kind = data.get("type") if data.get("type") in ("search_results", "playlist_preview", "activity_list", "status") else "state"
        self.events.put((kind, data))

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self.client.stop()

    def _run(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self.client.run())

    def send(self, action, **kw):
        if self._loop is None:
            return
        asyncio.run_coroutine_threadsafe(self.client.send_command(action, **kw), self._loop)
