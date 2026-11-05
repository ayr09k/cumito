"""
La ventana del modo normal: el diseño del lienzo tal cual (assets/web/),
dibujado por el mismo motor que el lienzo (Chromium, vía QtWebEngine).
Gasta más memoria que la ventana "clásica" (glass_screen.py), por eso el
modo streamer sigue usando esa, que no gasta casi nada.

La página y Python hablan por QWebChannel:
  página -> Python: cumito.send(acción, json), cumito.search(...),
                    cumito.win_cmd(...), cumito.save(clave, json), ...
  Python -> página: cumito.event(tipo, json)  (estado, resultados, etc.)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from PySide6.QtCore import QObject, QPoint, QUrl, Qt, Signal, Slot
from PySide6.QtWidgets import QFileDialog, QWidget

from . import theme

try:
    from PySide6.QtWebChannel import QWebChannel
    from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineSettings
    from PySide6.QtWebEngineWidgets import QWebEngineView
    AVAILABLE = True
except Exception:   # sin el motor web: Cumito usa la ventana clásica
    AVAILABLE = False

ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "assets"
WEB_INDEX = ASSETS / "web" / "index.html"


class Bridge(QObject):
    """Lo que la página puede pedirle a Python (y el canal de vuelta)."""

    event = Signal(str, str)

    def __init__(self, win):
        super().__init__(win)
        self.win = win

    @Slot(str, str)
    def send(self, action, kw_json):
        try:
            kw = json.loads(kw_json or "{}")
        except Exception:
            kw = {}
        self.win.core_send(action, kw if isinstance(kw, dict) else {})

    @Slot(str, int, int, str)
    def search(self, query, limit, offset, kind):
        self.win.core.do_search(query, limit, offset, kind)

    @Slot(str)
    def win_cmd(self, cmd):
        self.win.window_command(cmd)

    @Slot(str, str)
    def save(self, key, value_json):
        try:
            value = json.loads(value_json)
        except Exception:
            return
        self.win.core.liquid_save(key, value)

    @Slot()
    def pick_cover(self):
        self.win.pick_cover()

    @Slot()
    def ready(self):
        self.win.on_ready()


if AVAILABLE:
    class _Page(QWebEnginePage):
        def javaScriptConsoleMessage(self, level, message, line, source):
            # los errores de la página quedan en el registro (para poder arreglarlos)
            if level == QWebEnginePage.JavaScriptConsoleMessageLevel.ErrorMessageLevel:
                try:
                    (Path.home() / "Cumito_pagina.txt").open("a", encoding="utf-8").write(
                        f"{source}:{line}: {message}\n")
                except Exception:
                    pass


class LiquidWindow(QWidget):
    def __init__(self, core):
        super().__init__()
        self.core = core          # la ventana clásica (CumitoWindow): tiene la conexión y todo lo demás
        self._ready = False
        self._pending = []
        self.setWindowTitle("Cumito")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window | Qt.WindowMinimizeButtonHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(theme.GLASS_WINDOW_W, theme.GLASS_WINDOW_H)

        self.view = QWebEngineView(self)
        self.view.setGeometry(0, 0, theme.GLASS_WINDOW_W, theme.GLASS_WINDOW_H)
        self.view.setContextMenuPolicy(Qt.NoContextMenu)
        page = _Page(self.view)
        self.view.setPage(page)
        page.setBackgroundColor(Qt.transparent)
        st = page.settings()
        st.setAttribute(QWebEngineSettings.LocalContentCanAccessRemoteUrls, True)
        st.setAttribute(QWebEngineSettings.LocalContentCanAccessFileUrls, True)
        st.setAttribute(QWebEngineSettings.PlaybackRequiresUserGesture, False)   # el "tic" de la rueda
        st.setAttribute(QWebEngineSettings.ShowScrollBars, True)
        self.bridge = Bridge(self)
        self.channel = QWebChannel(page)
        self.channel.registerObject("cumito", self.bridge)
        page.setWebChannel(self.channel)
        self.view.load(QUrl.fromLocalFile(str(WEB_INDEX)))

    # ---------- Python -> página ----------
    def push(self, type_, payload):
        try:
            raw = json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:
            return
        if not self._ready:
            self._pending.append((type_, raw))
            return
        self.bridge.event.emit(type_, raw)

    def on_ready(self):
        self._ready = True
        self.push_config()
        for type_, raw in self._pending:
            self.bridge.event.emit(type_, raw)
        self._pending.clear()
        self.core.liquid_ready()

    def push_config(self):
        c = self.core
        try:
            from .build_info import VERSION
        except Exception:
            VERSION = ""
        self.push("config", {
            "name": c.cfg.get("display_name") or None,
            "recent_searches": list(c.recent_searches or []),
            "visual": dict(c.visual),
            "scale": c.ui_scale,
            "version": VERSION,
        })

    # ---------- página -> Python ----------
    def core_send(self, action, kw):
        try:
            self.core.send_command(action, **kw)
        except Exception:
            pass

    def window_command(self, cmd):
        if cmd == "minimize":
            self.showMinimized()
        elif cmd == "close":
            from PySide6.QtWidgets import QApplication
            QApplication.instance().quit()
        elif cmd == "drag":
            h = self.windowHandle()
            if h is not None:
                h.startSystemMove()
        elif cmd == "streamer":
            self.core.switch_to_classic()
        elif cmd.startswith("scale:"):
            try:
                self.core.on_scale_changed(float(cmd[6:]))
            except ValueError:
                pass
        elif cmd == "update":
            self.core.update_requested.emit()

    def pick_cover(self):
        path, _ = QFileDialog.getOpenFileName(self, "Elegir portada", "",
                                              "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
        if not path:
            return
        from .albums import image_to_b64
        b64 = image_to_b64(path)
        self.push("cover_picked", {"b64": b64} if b64 else {"error": "No pude abrir esa imagen"})
