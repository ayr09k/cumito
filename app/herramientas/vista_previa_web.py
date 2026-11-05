"""
Fotos de la ventana nueva (diseño del lienzo, motor web) en Windows, con
datos de ejemplo y sin servidor. Lo corre GitHub (vista_previa.yml).
"""
import json
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PySide6.QtCore import QCoreApplication, QEventLoop, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "vista_previa_web")
OUT.mkdir(parents=True, exist_ok=True)
QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)
app = QApplication(sys.argv)
from cumito import theme  # noqa: E402
theme.load_fonts(app)
from cumito import liquid_window  # noqa: E402

LOG = []


def _err(*exc):
    (OUT / "ERROR.txt").write_text("".join(traceback.format_exception(*exc)), encoding="utf-8")
    sys.__excepthook__(*exc)


sys.excepthook = _err


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


class FakeCore(QObject):
    update_requested = Signal()

    def __init__(self):
        super().__init__()
        self.cfg = {"display_name": "Juan"}
        self.recent_searches = ["bad bunny", "travis scott", "la bachata", "queen"]
        self.visual = {"streamer": False, "media_keys": True, "presence": True}
        self.ui_scale = 1.0
        self.sent = []

    def send_command(self, action, **kw):
        self.sent.append((action, kw))

    def do_search(self, q, limit, offset, kind):
        self.sent.append(("search", q, kind))
        res = [{"title": t, "uploader": a, "duration": d, "webpage_url": f"https://yt/{i}",
                "art_url": f"https://i.ytimg.com/vi/{v}/hqdefault.jpg"}
               for i, (t, a, d, v) in enumerate(SONGS)]
        QTimer.singleShot(600, lambda: win.push("search_results", {"query": q, "kind": kind, "offset": offset,
                                                                   "results": res}))

    def liquid_save(self, k, v):
        self.sent.append(("save", k, v))

    def liquid_ready(self):
        LOG.append("la página avisó que está lista")

    def switch_to_classic(self):
        self.sent.append(("switch_to_classic",))

    def on_scale_changed(self, s):
        self.sent.append(("scale", s))


SONGS = [("DtMF", "Bad Bunny", 237, "TiebZllW8As"), ("Ojitos Lindos", "Bad Bunny, Bomba Estéreo", 258, "7GDp7S1HgSk"),
         ("La Bachata", "Manuel Turizo", 163, "TiM_TFpT_DE"), ("Gasolina", "Daddy Yankee", 192, "CCF1_jI8Prk")]
core = FakeCore()
win = liquid_window.LiquidWindow(core)
win.move(60, 60)
win.show()
for _ in range(100):
    if win._ready:
        break
    wait(100)
LOG.append(f"lista: {win._ready}")


def shot(name, ms=900):
    wait(ms)
    app.processEvents()
    scr = QGuiApplication.primaryScreen()
    g = win.frameGeometry()
    scr.grabWindow(0, g.x(), g.y(), g.width(), g.height()).save(str(OUT / f"{name}.png"))
    win.grab().save(str(OUT / f"{name}_grab.png"))
    print("foto", name)


def js(code):
    win.view.page().runJavaScript(code)


FEAT = ["prev", "seek", "repeat", "shuffle", "sleep", "normalize", "radio", "lyrics", "react", "albums", "stats",
        "spotify"]
now = time.time()
recent = [{"title": t, "uploader": a, "webpage_url": f"https://yt/r{i}", "art_url": f"https://i.ytimg.com/vi/{v}/hqdefault.jpg"}
          for i, (t, a, d, v) in enumerate(SONGS)]
base = {"host_label": "Admin", "features": FEAT, "members": ["Ana", "Pedro", "Juan"], "recent": recent, "queue": [],
        "now_playing": None, "albums_rev": 1}
win.push("state", base)
win.push("albums", {"albums": [
    {"id": 1, "name": "Perreo de los viernes", "owner": "Ana", "color": "#F2D16B", "count": 24, "arts": []},
    {"id": 2, "name": "Para estudiar", "owner": "Pedro", "color": "#1F2D5C", "count": 41, "arts": []}]})
win.push("activity_list", {"entries": [
    {"id": 1, "ts": now - 300, "who": "Ana", "text": "agregó 1 canción", "title": "La Bachata"},
    {"id": 2, "ts": now - 100, "who": "Pedro", "text": "creó el disco «Para estudiar»"}]})
shot("w01_inicio", 1800)
js("openSearch()")
shot("w02_buscar_estirandose", 260)
shot("w03_buscar", 900)
js("document.getElementById('q').value='bad bunny'; submitSearch()")
shot("w04_resultados", 2200)
js("closeSearch()")
wait(700)
st = dict(base, now_playing={"title": "Ojitos Lindos", "uploader": "Bad Bunny, Bomba Estéreo", "duration": 258,
                             "elapsed": 61, "paused": False, "who": "Ana", "webpage_url": "https://yt/x",
                             "art_url": "https://i.ytimg.com/vi/7GDp7S1HgSk/hqdefault.jpg"},
          queue=[{"uid": 2, "title": "La Bachata", "uploader": "Manuel Turizo", "duration": 163, "prepared": True,
                  "art_url": "https://i.ytimg.com/vi/TiM_TFpT_DE/hqdefault.jpg"},
                 {"uid": 3, "title": "Gasolina", "uploader": "Daddy Yankee", "duration": 192, "prepared": False}],
          can_prev=True, repeat="all")
win.push("state", st)
shot("w05_ahora_sonando", 2200)
js("openSheet()")
shot("w06_lista", 1000)
js("closeSheet(); openOptions()")
shot("w07_opciones", 2000)
js("optGo(2)")
shot("w07b_opciones_girando", 900)
js("closePanel(); openLyrics()")
win.push("lyrics", {"found": True, "webpage_url": "https://yt/x", "synced": "\n".join(
    f"[01:{s:05.2f}] {t}" for s, t in [(0, "Hace mucho tiempo le hago caso al corazón"), (2, "Y pasan los días"),
                                        (8, "Ha llegado el tiempo para usar la razón"), (14, "Pero aquí sigo yo")])})
shot("w08_karaoke", 1500)
js("closePanel(); openAlbums()")
win.push("albums", {"albums": [
    {"id": 1, "name": "Perreo de los viernes", "owner": "Ana", "color": "#F2D16B", "count": 24,
     "arts": [r["art_url"] for r in recent]},
    {"id": 2, "name": "Para estudiar", "owner": "Pedro", "color": "#1F2D5C", "count": 41, "arts": []}]})
shot("w09_discos", 1800)
shot("w09b_discos_despues", 3500)
js("closePanel(); openPanel('status')")
win.push("status", {"cpu": 23, "cpu_hist": [20 + (i % 9) * 3 for i in range(90)], "steal": 2,
                    "steal_hist": [2] * 90, "cores": 2, "mem": {"total": 1e9, "used": 6.1e8},
                    "disk": {"total": 4.7e10, "used": 9.8e9}, "uptime_vm": 450000, "uptime_bot": 7800,
                    "bot_rss": 1.6e8, "helpers": {"n": 2, "rss": 1.2e8},
                    "discord": {"ready": True, "ping": 48, "voice": "General"}, "listeners": 3,
                    "queue": {"total": 14, "prepared": 5}, "playing": "Ojitos Lindos",
                    "versions": {"server": "2.1 (2026-11-04)", "yt_dlp": "2026.10.22"}, "time": now, "logs": []})
shot("w10_estado", 2000)
shot("w10b_estado_despues", 3500)
js("closePanel()")
wait(600)
win.window_command("drag")   # no debe romper nada aunque no haya mouse
(OUT / "PRUEBA_WEB.txt").write_text("\n".join(LOG + [f"mandó: {x}" for x in core.sent]), encoding="utf-8")
log = Path.home() / "Cumito_pagina.txt"
if log.exists():
    (OUT / "ERRORES_PAGINA.txt").write_text(log.read_text(encoding="utf-8"), encoding="utf-8")
print("\n".join(LOG))
print("listo")
