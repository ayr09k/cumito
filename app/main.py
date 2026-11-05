"""
Cumito -- la app que usan todos (tú y tu grupo) para controlar la música.
Se conecta al servidor donde vive el bot (Cumito-servidor, corriendo en
tu VM) por la dirección que se configura una sola vez.
"""
import os
import sys
import traceback
from pathlib import Path

BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
sys.path.insert(0, str(BASE))

from PySide6.QtCore import QObject, QTimer, Slot
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from cumito import config
from cumito.connect_screen import ConnectScreen
from cumito.glass_screen import GlassScreen
from cumito.mediakeys import MediaKeys
from cumito.presence import DiscordPresence
from cumito.runtime import CumitoRuntime
from cumito.splash import Splash, fade_in_window
from cumito.updater import Updater, run_installer_and_quit

ICON_PATH = BASE / "assets" / "cumito.ico"


class CumitoWindow(GlassScreen):
    def __init__(self, cfg):
        self.cfg = cfg
        self.runtime = None
        super().__init__("Cumito")
        self.recent_searches = list(self.cfg.get("recent_searches") or [])[:6]
        self.set_visual(self.cfg.get("visual") or {})
        self.text_overlay.submitted.connect(self._on_text_submitted)
        self.btn_close.clicked.connect(QApplication.instance().quit)
        # 2.0: "Escuchando en Cumito" en Discord y teclas multimedia
        self.presence = DiscordPresence()
        self.media_keys = MediaKeys(QApplication.instance(), self, self._on_media_key)
        QTimer.singleShot(0, self._apply_integrations)

    def my_name(self):
        return self.cfg.get("display_name") or None

    def _apply_integrations(self):
        v = self.visual
        try:
            if v.get("media_keys", True):
                self.media_keys.start()
            else:
                self.media_keys.stop()
        except Exception:
            pass
        self.presence.set_enabled(v.get("presence", True))
        self._update_presence()

    def _update_presence(self):
        np = self.state.get("now_playing") if self.state.get("connected", True) else None
        self.presence.set_track(np, self._local_elapsed)

    def _on_media_key(self, name):
        if name == "play_pause":
            self._on_play_pause()
        elif name == "next":
            self.send_command("skip")
        elif name == "prev" and "prev" in self._features():
            self.send_command("prev")

    # ---------- ajustes ----------
    def settings_rows(self):
        # (texto, ícono) -- van en la rueda de Opciones, junto a Actividad,
        # Efecto vidrio y Apagar Cumito (esas las pone la ventana)
        return [("Cambiar servidor", "server"), ("Cambiar mi nombre", "user")]

    def on_settings_row(self, label):
        if label == "Cambiar servidor":
            self.ask_text(
                "Dirección del servidor (déjalo vacío para volver al de siempre)", "set_address",
                placeholder=config.DEFAULT_SERVER, initial=self.cfg.get("host_address", ""),
            )
        elif label == "Cambiar mi nombre":
            self.ask_text("¿Cómo quieres que te vean?", "rename",
                           initial=self.cfg.get("display_name", ""))

    def _on_text_submitted(self, context, text):
        text = text.strip()
        if context == "set_address" and (":" in text or not text):
            self.cfg["host_address"] = text or config.DEFAULT_SERVER
            config.save(self.cfg)
            self._connect()
        elif context == "rename" and text:
            self.cfg["display_name"] = text
            config.save(self.cfg)
            self._connect()

    def on_scale_changed(self, scale):
        self.cfg["ui_scale"] = scale
        self.cfg["win_pos"] = [self.x(), self.y()]   # que vuelva a abrir en el mismo lugar
        config.save(self.cfg)
        QTimer.singleShot(150, _restart)

    def on_visual_changed(self, visual):
        self.cfg["visual"] = visual
        config.save(self.cfg)
        self._apply_integrations()

    # ---------- búsqueda ----------
    def on_recent_searches_changed(self, searches):
        self.cfg["recent_searches"] = searches
        config.save(self.cfg)

    def request_activity(self):
        if self.runtime:
            self.runtime.send("activity_list")

    def request_status(self):
        if self.runtime:
            self.runtime.send("status")

    def do_search(self, query, limit=8, offset=0, kind="music"):
        if self.runtime:
            self.runtime.send("search", query=query, limit=limit, offset=offset, kind=kind)

    # ---------- conexión al servidor ----------
    def _connect(self):
        if self.runtime:
            self.runtime.stop()
        self.runtime = CumitoRuntime(self.cfg["host_address"], self.cfg.get("display_name") or "Pana")
        self.send_command = lambda action, **kw: self.runtime.send(action, **kw)
        self.runtime.start()

        if hasattr(self, "_poll"):
            self._poll.stop()
        self._poll = QTimer(self)
        self._poll.timeout.connect(self._poll_events)
        self._poll.start(200)

    def _poll_events(self):
        if not self.runtime:
            return
        while not self.runtime.events.empty():
            kind, payload = self.runtime.events.get()
            if kind == "state":
                self.set_state({**payload, "connected": True})
                if payload.get("app_id"):
                    self.presence.set_client_id(payload.get("app_id"))
                self._update_presence()
            elif kind == "connected":
                if not payload:
                    # sin servidor no hay nada sonando que mostrar; al
                    # reconectar, el servidor manda el estado real solo.
                    self.set_state({"connected": False, "now_playing": None, "queue": []})
                    self._update_presence()
            elif kind == "search_results":
                self.set_search_results(payload.get("query"), payload.get("results") or [],
                                        offset=int(payload.get("offset") or 0), kind=payload.get("kind"))
            elif kind == "playlist_preview":
                self.show_playlist_preview(payload)
            elif kind == "activity_list":
                self.set_activity_list(payload.get("entries") or [])
            elif kind == "status":
                self.set_server_status(payload)
            # 2.0
            elif kind == "lyrics":
                self.set_lyrics(payload)
            elif kind == "stats":
                self.set_stats(payload)
            elif kind == "albums":
                self.set_albums(payload.get("albums") or [])
            elif kind == "album":
                self.set_album(payload.get("album"))
            elif kind == "album_cover":
                if payload.get("data"):
                    from cumito.albums import b64_to_image
                    self.set_album_cover(payload.get("cover"), b64_to_image(payload["data"]))
            elif kind == "album_added":
                self.on_album_added(payload)
            elif kind == "error":
                self.show_server_error(payload.get("message"))


def _log_uncaught(exc_type, exc_value, exc_tb):
    """Red de seguridad: con pythonw no hay consola, así que un error
    dentro de un clic/acción sería invisible sin esto."""
    text = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
    log_path = Path.home() / "Cumito_error.txt"
    try:
        log_path.write_text(text, encoding="utf-8")
    except Exception:
        pass
    # La app no tiene consola, así que sin esto un error sería invisible:
    # se muestra un aviso normal de Windows con dónde quedó el detalle.
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(
            None,
            f"Cumito tuvo un problema y se cerró.\n\n"
            f"El detalle quedó guardado en:\n{log_path}\n\n"
            f"Mándale ese archivo a quien te pasó Cumito.",
            "Cumito",
            0x10,
        )
    except Exception:
        pass



class _UpdateController(QObject):
    """Une el Updater (que trabaja en un hilo de fondo) con la ventana.
    Al ser un QObject, sus métodos siempre corren en el hilo de la ventana,
    aunque la señal venga del hilo de descarga."""

    def __init__(self, win, app):
        super().__init__(win)
        self.win, self.app, self.url = win, app, None
        self._downloading = False
        self.updater = Updater(self)
        # además de al abrir, se vuelve a mirar cada 30 min (por si Cumito
        # se queda abierto todo el día)
        self._every = QTimer(self)
        self._every.setInterval(30 * 60 * 1000)
        self._every.timeout.connect(self._periodic_check)
        self._every.start()
        self.updater.available.connect(self._on_available)
        self.updater.progress.connect(self._on_progress)
        self.updater.failed.connect(self._on_failed)
        self.updater.ready.connect(self._on_ready)
        win.update_requested.connect(self._on_requested)

    @Slot()
    def _periodic_check(self):
        if not self._downloading:
            self.updater.check()

    @Slot(str, str)
    def _on_available(self, version, url):
        if self._downloading:
            return
        self.url = url
        QTimer.singleShot(1500, lambda: self.win.show_update(version))  # que la ventana ya esté a la vista

    @Slot()
    def _on_requested(self):
        if self.url and not self._downloading:
            self._downloading = True
            self.win.set_update_progress(0.0)
            self.updater.download(self.url)

    @Slot(float)
    def _on_progress(self, f):
        self.win.set_update_progress(f)

    @Slot(str)
    def _on_failed(self, message):
        self._downloading = False
        self.win.set_update_failed(message)

    @Slot(str)
    def _on_ready(self, path):
        self.win.set_update_installing()
        try:
            run_installer_and_quit(path)
        except Exception as e:
            self.win.set_update_failed(str(e))
            return
        QTimer.singleShot(700, self.app.quit)

def _restart():
    """Vuelve a abrir Cumito (para aplicar el tamaño nuevo de la ventana)."""
    from PySide6.QtCore import QProcess
    if getattr(sys, "frozen", False):
        QProcess.startDetached(sys.executable, ["--sin-bienvenida"])
    else:
        QProcess.startDetached(sys.executable, [str(Path(__file__).resolve()), "--sin-bienvenida"])
    QApplication.instance().quit()


def main():
    sys.excepthook = _log_uncaught
    cfg = config.load()
    # Tamaño de toda la ventana (Opciones -> Apariencia -> Tamaño). Qt lo
    # aplica a todo por igual (textos, íconos, márgenes) si se pide ANTES de
    # crear la app.
    try:
        scale = max(0.6, min(1.0, float(cfg.get("ui_scale") or 1.0)))
    except (TypeError, ValueError):
        scale = 1.0
    if scale < 0.999:
        os.environ["QT_SCALE_FACTOR"] = f"{scale:.2f}"
    app = QApplication(sys.argv)
    icon = QIcon(str(ICON_PATH))
    app.setWindowIcon(icon)

    win = CumitoWindow(cfg)
    win.ui_scale = scale
    win.setWindowIcon(icon)

    # La primera vez (sin nombre guardado) se muestra la bienvenida; las
    # demás, la conexión arranca mientras se ve el splash, y cuando aparece
    # la ventana ya trae lo que está sonando.
    first_time = not cfg.get("display_name") or not cfg.get("host_address")
    if not first_time:
        win._connect()

    def after_splash():
        if not first_time:
            fade_in_window(win)
            return
        connect = ConnectScreen(default_address=cfg.get("host_address", ""),
                                default_name=cfg.get("display_name", ""))
        connect.setWindowIcon(icon)

        def _start(address, name):
            win.cfg["host_address"] = address
            win.cfg["display_name"] = name
            config.save(win.cfg)
            fade_in_window(win)   # primero se muestra la nueva...
            connect.close()       # ...y recién después se cierra esta
            win._connect()

        connect.connected.connect(_start)
        win._connect_screen = connect  # que no se pierda la referencia
        fade_in_window(connect)

    # ---- actualizaciones automáticas (ver cumito/updater.py) ----
    win._update_ctl = _UpdateController(win, app)

    if "--sin-bienvenida" in sys.argv and not first_time:
        # se reinició solo (p. ej. al cambiar el tamaño): directo, sin el saludo
        pos = cfg.get("win_pos")
        if isinstance(pos, list) and len(pos) == 2:
            win.move(int(pos[0]), int(pos[1]))
        after_splash()
        QTimer.singleShot(1500, win._update_ctl.updater.check)
    else:
        splash = Splash()
        splash.setWindowIcon(icon)
        splash.finished.connect(after_splash)
        splash.finished.connect(win._update_ctl.updater.check)
        splash.start()

    def _bye():
        try:
            win.presence.stop()
            win.media_keys.stop()
        except Exception:
            pass
    app.aboutToQuit.connect(_bye)

    try:
        sys.exit(app.exec())
    except SystemExit:
        raise
    except Exception:
        _log_uncaught(*sys.exc_info())
        raise


if __name__ == "__main__":
    main()
