"""
Cumito - servidor (bot de Discord + relay)
============================================
Esto es lo que corre 24/7 en tu VM (por ejemplo, una de Oracle Cloud).
No tiene ventana ni interfaz gráfica -- es un programa de consola que se
queda corriendo. Las apps "Cumito" de tu grupo se conectan a este
servidor por el puerto 8765.

La PRIMERA vez que lo corres, te pregunta por consola el token del bot,
el ID del servidor de Discord, el ID del canal de voz y un nombre para
mostrar -- y los guarda en config.json (al lado de este archivo). Las
siguientes veces arranca directo, sin preguntar nada.

Para cambiar algo después: edita config.json a mano, o bórralo para que
vuelva a preguntar.
"""
import asyncio
import logging
import signal
import sys

from cumito_bot import config, protocol
from cumito_bot.bot import BotCore
from cumito_bot.relay import RelayServer

RELAY_PORT = 8765

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _ask(prompt, numeric=False):
    while True:
        value = input(prompt).strip().strip('"').strip("'")
        if not value:
            print("  (no puede quedar vacío)")
        elif numeric and not value.isdigit():
            print("  (eso no parece un ID: tiene que ser solo números, ej. 123456789012345678)")
        else:
            return value


def _first_time_setup():
    print("=" * 60)
    print(" Cumito - configuración (esto solo se pregunta una vez)")
    print("=" * 60)
    cfg = config.load()
    cfg["token"] = _ask("Token del bot de Discord: ")
    cfg["guild_id"] = _ask("ID del servidor de Discord: ", numeric=True)
    print("\nEl bot entra solo al canal de voz donde esté la gente. Si quieres,")
    print("puedes darle un canal de respaldo para cuando no haya nadie conectado.")
    while True:
        ch = input("ID del canal de voz de respaldo (opcional, Enter para saltar): ").strip()
        if not ch or ch.isdigit():
            cfg["channel_id"] = ch
            break
        print("  (tiene que ser solo números, o déjalo vacío)")
    cfg["host_display_name"] = input("Tu nombre (como te verán en Cumito): ").strip() or "Admin"
    config.save(cfg)
    print("\nGuardado en config.json.\n")
    return cfg


class CumitoServer:
    """Igual que el bot + relay de siempre, solo que sin la parte de Qt:
    todo corre en un único loop de asyncio, en el hilo principal -- no
    hace falta un hilo aparte porque no hay ninguna interfaz que proteger."""

    def __init__(self, cfg):
        self.relay = RelayServer(RELAY_PORT, on_command=self._on_relay_command)
        self.bot = BotCore(
            cfg["token"], int(cfg["guild_id"]),
            int(cfg["channel_id"]) if str(cfg.get("channel_id") or "").isdigit() else None,
            cfg.get("host_display_name") or "Admin",
            on_change=self._on_change,
        )

    def _on_change(self):
        snap = self.bot.snapshot()
        asyncio.create_task(self.relay.broadcast_state(
            snap["host_label"], snap["now_playing"], snap["queue"],
            volume=snap.get("volume"), recent=snap.get("recent"),
            activity_last=snap.get("activity_last"),
        ))

    async def _on_relay_command(self, data, sender_name, ws=None):
        bot = self.bot
        who = sender_name
        action = data.get("action")
        if action == "play":
            await bot.action_play(data.get("query", ""), as_playlist=bool(data.get("as_playlist")),
                                  req=data.get("req"), who=who)
        elif action == "playlist_preview":
            # responde solo a quien preguntó, como la búsqueda
            preview = await bot.action_playlist_preview(data.get("url", ""))
            if ws is not None:
                try:
                    await ws.send(protocol.dumps("playlist_preview", **preview))
                except Exception:
                    pass
        elif action == "pause":
            await bot.action_pause(who=who)
        elif action == "resume":
            await bot.action_resume(who=who)
        elif action == "skip":
            await bot.action_skip(who=who)
        elif action == "stop":
            await bot.action_stop(who=who)
        elif action == "stop_and_leave":
            await bot.action_stop_and_leave(who=who)
        elif action == "queue_remove":
            await bot.action_queue_remove(int(data.get("index", -1)), who=who)
        elif action == "queue_clear":
            await bot.action_queue_clear(who=who)
        elif action == "set_volume":
            await bot.action_set_volume(data.get("value", 0.6), who=who)
        elif action == "play_index":
            await bot.action_play_index(int(data.get("index", -1)), uid=data.get("uid"), who=who)
        elif action == "activity_list":
            # el historial completo, solo para quien lo pidió (Ajustes > Actividad)
            if ws is not None:
                try:
                    await ws.send(protocol.dumps("activity_list", entries=bot.activity_list()))
                except Exception:
                    pass
        elif action == "prepare":
            await bot.action_prepare(int(data.get("index", -1)), uid=data.get("uid"))
        elif action == "search":
            # Esta sí responde directo a quien preguntó, no se difunde.
            offset = int(data.get("offset", 0) or 0)
            results = await bot.action_search(data.get("query", ""), limit=int(data.get("limit", 8)), offset=offset)
            if ws is not None:
                try:
                    await ws.send(protocol.search_results(data.get("query", ""), results, offset=offset))
                except Exception:
                    pass

    async def run(self):
        await self.relay.start()
        print(f"Relay escuchando en el puerto {RELAY_PORT}. Conectando el bot a Discord...")
        try:
            await self.bot.start()
        finally:
            await self.relay.stop()
            await self.bot.close()


async def main():
    cfg = config.load()
    if not config.is_complete(cfg):
        cfg = _first_time_setup()
    server = CumitoServer(cfg)
    # systemd apaga con SIGTERM (al actualizar o reiniciar): se atrapa para
    # cerrar ordenado y dejar anotado en qué segundo iba la canción.
    task = asyncio.current_task()
    try:
        asyncio.get_running_loop().add_signal_handler(signal.SIGTERM, task.cancel)
    except (NotImplementedError, RuntimeError):
        pass
    try:
        await server.run()
    except asyncio.CancelledError:
        print("Cumito servidor detenido (se guardó dónde iba).")


if __name__ == "__main__":
    # "python3 run.py --configurar": solo pregunta los datos y sale (lo usa
    # instalar.sh antes de dejar el servicio corriendo solo).
    if "--configurar" in sys.argv:
        _first_time_setup()
        sys.exit(0)
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nCumito servidor detenido.")
        sys.exit(0)
