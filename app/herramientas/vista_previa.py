"""
Saca fotos de la ventana real de Cumito en distintos estados (sin servidor),
para revisar el diseño. Lo corre GitHub (.github/workflows/vista_previa.yml)
y deja las imágenes en la rama "vista-previa".
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PySide6.QtCore import QEventLoop, QTimer, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPixmap, QRadialGradient
from PySide6.QtWidgets import QApplication

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "vista_previa")
OUT.mkdir(parents=True, exist_ok=True)
app = QApplication(sys.argv)

import cumito.glass_screen as gs  # noqa: E402
from cumito.glass_screen import GlassScreen  # noqa: E402

gs.IDLE_S = 1e9   # en las fotos el modo "solo portada" se activa a mano


def _guardar_error(*exc):
    import traceback
    (OUT / "ERROR.txt").write_text("".join(traceback.format_exception(*exc)), encoding="utf-8")
    sys.__excepthook__(*exc)


sys.excepthook = _guardar_error


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def shot(w, name):
    app.processEvents()
    w.grab().save(str(OUT / f"{name}.png"))
    print("foto:", name)


def fake_art():
    pix = QPixmap(640, 360)
    p = QPainter(pix)
    g = QLinearGradient(0, 0, 640, 360)
    g.setColorAt(0, QColor("#2B1B5A"))
    g.setColorAt(0.5, QColor("#B0306A"))
    g.setColorAt(1, QColor("#F2A33A"))
    p.fillRect(pix.rect(), g)
    for cx, cy, r, c in [(150, 120, 120, "#4FB4D8"), (470, 250, 150, "#8E6CF2"), (330, 90, 70, "#FFFFFF")]:
        rg = QRadialGradient(cx, cy, r)
        col = QColor(c)
        col.setAlpha(170)
        rg.setColorAt(0, col)
        col2 = QColor(c)
        col2.setAlpha(0)
        rg.setColorAt(1, col2)
        p.fillRect(pix.rect(), rg)
    p.end()
    return pix


LONG = "Bad Bunny - DtMF (Video Oficial) | DeBÍ TiRAR MáS FOToS Remix Extendido feat. Todo el Mundo 2025"
now = time.time()
state = {
    "connected": True,
    "host_label": "Admin",
    "now_playing": {"title": LONG, "duration": 245, "elapsed": 61, "paused": False,
                    "art_url": None, "uploader": "Bad Bunny Oficial - Topic - Canal con nombre larguísimo"},
    "queue": [
        {"uid": 1, "title": "Canción normal", "duration": 200, "uploader": "Artista", "ready": True, "prepared": True},
        {"uid": 2, "title": "Un título exageradamente largo que antes empujaba la equis fuera de la lista (Letra)",
         "duration": 233, "uploader": "Un canal con un nombre también larguísimo de verdad", "ready": True,
         "prepared": True},
        {"uid": 5, "title": "La Bachata", "duration": 163, "uploader": "Manuel Turizo", "ready": True, "prepared": True},
        {"uid": 4, "title": "Preparándose", "duration": 190, "uploader": "X", "ready": False, "loading": True,
         "prepared": False},
        {"uid": 3, "title": "Otra más, todavía sin preparar, también con un nombre muy muy largo", "duration": 180,
         "uploader": "Alguien", "ready": False, "prepared": False},
    ] + [{"uid": 100 + i, "title": f"Canción {i} de la playlist", "duration": 200, "uploader": "Artista",
          "ready": False, "prepared": False} for i in range(1, 9)],
    "recent": [],
    "volume": 0.6,
}

w = GlassScreen()
w.settings_rows = lambda: [("Cambiar servidor", "server"), ("Cambiar mi nombre", "user")]
w.show()
w.set_state(state)
w._set_art_background(fake_art())
wait(500)
shot(w, "01_principal")
if len(sys.argv) > 2 and sys.argv[2] == "solo":
    sys.exit(0)

# rueda de opciones
w._open_settings()
wait(500)
shot(w, "01b_opciones")
w.option_wheel.go(2)
wait(150)
shot(w, "01c_opciones_girando")
wait(500)
shot(w, "01d_opciones_en_servidor")
w._close_settings()
wait(500)

# modo solo portada (8 s sin tocar nada)
from PySide6.QtGui import QCursor
QCursor.setPos(5000, 5000)          # el mouse lejos de la ventana
app.processEvents()
w._last_cursor = QCursor.pos()
w._set_idle(True)
wait(900)
shot(w, "01e_solo_portada")
w._set_idle(False)
wait(600)
shot(w, "01f_vuelve_todo")

# fondo paseándose: 15 s después (mitad del recorrido)
w._pan_t0 -= 15
w._on_pan()
shot(w, "02_fondo_a_la_mitad")
w._pan_t0 += 15
w._on_pan()

# aviso de actividad arriba
w.set_state({"activity_last": {"id": 1, "ts": now, "who": "Juan", "kind": "add", "text": "agregó 1 canción",
                               "title": "Ojitos Lindos", "sub": "Bad Bunny"}})
wait(400)
shot(w, "03_aviso_arriba_inicio")
wait(1800)
shot(w, "04_aviso_arriba_deslizado")
wait(2200)

# la flechita de la playlist animándose
w.swipe_hint._play()
wait(450)
shot(w, "05_flechitas_playlist")
wait(1200)

# playlist abierta con títulos largos
w._open_sheet()
wait(600)
shot(w, "06_playlist_abierta")
# --- prueba con eventos de mouse de verdad: agarrar, mover y soltar FUERA de la fila ---
from PySide6.QtCore import QPoint, QPointF, QEvent
from PySide6.QtGui import QMouseEvent, QCursor
from PySide6.QtWidgets import QApplication as _QA
ql = w.sheet_list_widget
res = []
def _send(widget, typ, gpos, buttons):
    QCursor.setPos(gpos)
    local = QPointF(widget.mapFromGlobal(gpos))
    ev = QMouseEvent(typ, local, QPointF(gpos), Qt.LeftButton, buttons, Qt.NoModifier)
    _QA.sendEvent(widget, ev)
    app.processEvents()
order = lambda: [ql._ready_lay.itemAt(i).widget().property("uid") for i in range(ql._ready_lay.count())]
row = ql._rows[5][0]
p0 = row.mapToGlobal(QPoint(60, 23))
res.append(f"antes: {order()}")
_send(row, QEvent.MouseButtonPress, p0, Qt.LeftButton)
first = ql._rows[1][0]
for k in range(1, 8):
    _send(row, QEvent.MouseMove, p0 + QPoint(0, -k * 14), Qt.LeftButton)
res.append(f"arrastrando: drag={'sí' if ql._drag else 'no'} cursor={'mano cerrada' if _QA.overrideCursor() else 'normal'}")
# soltar sobre OTRO widget (antes esto dejaba todo colgado)
_send(w, QEvent.MouseButtonRelease, p0 + QPoint(0, -98), Qt.NoButton)
wait(100)
res.append(f"después de soltar: drag={'COLGADO' if ql._drag else 'terminado'} cursor={'COLGADO' if _QA.overrideCursor() else 'normal'} orden={order()}")
# cancelar con Esc
row = ql._rows[2][0]
p1 = row.mapToGlobal(QPoint(60, 23))
_send(row, QEvent.MouseButtonPress, p1, Qt.LeftButton)
for k in range(1, 6):
    _send(row, QEvent.MouseMove, p1 + QPoint(0, k * 14), Qt.LeftButton)
from PySide6.QtGui import QKeyEvent
_QA.sendEvent(w, QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
wait(100)
res.append(f"Esc: drag={'COLGADO' if ql._drag else 'cancelado'} orden={order()}")
_send(row, QEvent.MouseButtonRelease, p1, Qt.NoButton)
wait(100)
res.append(f"la fila sigue respondiendo a clics: {'sí' if row.isVisible() and not row._dragging else 'NO'}")
(OUT / "PRUEBA_ARRASTRE.txt").write_text("\n".join(res), encoding="utf-8")
print("\n".join(res))

# arrastrar "La Bachata" al primer lugar (a mitad del arrastre)
row = ql._rows[5][0]
start = row.mapToGlobal(QPoint(60, 23))
ql._drag_start(row, start)
wait(200)
first = ql._rows[1][0]
ql._drag_move(first.mapToGlobal(QPoint(70, 6)))
wait(200)
shot(w, "06b_arrastrando")
ql._drag_end(first.mapToGlobal(QPoint(70, 6)))
wait(200)
shot(w, "06c_soltado")

# borrar lista: aviso + botón a medias
w._ask_clear_queue()
wait(450)
shot(w, "07_borrar_lista_aviso")
hb = w.hold_confirm.hold
hb._pressed = True
hb._p = 0.35
hb._shake.start()
shot(w, "08_borrar_mantener_35")
hb._p = 0.8
shot(w, "09_borrar_mantener_80")
hb.reset()
w.hold_confirm.close_confirm()
wait(400)
w._close_sheet()
wait(500)

# apagar
w._ask_stop_bot()
wait(450)
hb._pressed = True
hb._p = 0.55
shot(w, "10_apagar_mantener_55")
hb.reset()
w.hold_confirm.close_confirm()
wait(400)

# buscador con títulos largos
w._open_search()
wait(500)
w._search_query = "bad bunny"
w.set_search_results("bad bunny", [
    {"title": LONG, "uploader": "Bad Bunny", "duration": 245, "webpage_url": "u1"},
    {"title": "Corto", "uploader": "Alguien con un nombre de canal muy largo", "duration": 100, "webpage_url": "u2"},
    {"title": "Tercero con nombre larguísimo para ver si se corta bien al final", "uploader": "Z", "webpage_url": "u3"},
    {"title": "Cuarto", "uploader": "W", "webpage_url": "u4"},
])
wait(1500)
shot(w, "11_buscador_titulos_largos")
w._set_search_kind("all")
w.set_search_results("bad bunny", [{"title": "Video oficial", "uploader": "Canal", "webpage_url": "x1"},
                                   {"title": "En vivo", "uploader": "Canal", "webpage_url": "x2"}], kind="all")
wait(900)
shot(w, "11b_buscador_todo")
w._set_search_kind("music")

# vista previa de playlist con "No gracias" a medio mantener
w._preview = {"url": "https://www.youtube.com/playlist?list=PL1"}
w.show_playlist_preview({"url": "https://www.youtube.com/playlist?list=PL1", "title": "Mi playlist de prueba",
                         "entries": [{"title": f"Canción {i} " + ("con nombre larguísimo " * 3 if i == 2 else "")}
                                     for i in range(1, 9)]})
wait(1500)
pn = w.preview_no
pn._pressed = True
pn._p = 0.5
shot(w, "12_playlist_no_gracias_50")
pn.reset()
w._close_search()
wait(500)

# actividad estilo chat
w.open_activity()
w.set_activity_list([
    {"id": 1, "ts": now - 90000, "who": "Pedro", "kind": "add", "text": "agregó 1 canción", "title": "Ayer sonó esto",
     "sub": "Artista"},
    {"id": 2, "ts": now - 1200, "who": "Juan", "kind": "playlist", "text": "agregó una playlist de 24 canciones",
     "title": "Reggaetón viejo"},
    {"id": 3, "ts": now - 1100, "who": "Juan", "kind": "add", "text": "agregó 1 canción", "title": LONG,
     "sub": "Bad Bunny"},
    {"id": 4, "ts": now - 600, "who": "Ana", "kind": "skip", "text": "saltó", "title": "Canción normal", "sub": "Artista"},
    {"id": 5, "ts": now - 300, "who": "Cumito", "kind": "restored", "text": "se reinició y siguió donde iba",
     "title": "Ojitos Lindos", "sub": "Bad Bunny"},
    {"id": 6, "ts": now - 60, "who": "Ana", "kind": "volume", "text": "puso el volumen al 70%"},
    {"id": 7, "ts": now - 50, "who": "Ana", "kind": "pause", "text": "pausó la música"},
])
wait(900)
shot(w, "13_actividad")
# estado del servidor (datos de ejemplo)
w._close_activity()
wait(400)
import math as _m
w.open_status()
wait(450)
_now = time.time()
w.set_server_status({
    "cpu": 23.5, "cpu_hist": [max(2, 18 + 14 * _m.sin(i / 6) + (40 if 60 < i < 66 else 0)) for i in range(90)],
    "steal": 6, "steal_hist": [3 + 4 * abs(_m.sin(i / 9)) for i in range(90)], "cores": 2,
    "load": [0.42, 0.37, 0.30], "mem": {"total": 1_000_000_000, "used": 610_000_000},
    "swap": {"total": 2_000_000_000, "used": 180_000_000}, "disk": {"total": 47_000_000_000, "used": 9_800_000_000},
    "uptime_vm": 5 * 86400 + 3600 * 4, "uptime_bot": 3600 * 2 + 600, "bot_rss": 160_000_000,
    "helpers": {"n": 2, "rss": 120_000_000}, "discord": {"ready": True, "ping": 48, "voice": "General"},
    "listeners": 3, "queue": {"total": 14, "prepared": 5, "loading": 1, "failed": 0},
    "playing": "Ojitos Lindos", "versions": {"server": "a1b2c3d · 2026-11-04", "yt_dlp": "2026.10.22"},
    "update_pending": False, "time": _now,
    "logs": [{"t": _now - 300, "lvl": "INFO", "src": "bot", "msg": "Reproduciendo: Ojitos Lindos"},
             {"t": _now - 120, "lvl": "WARNING", "src": "bot",
              "msg": "YouTube no dejó sacar 'X' (Sign in to confirm). Probando en SoundCloud..."},
             {"t": _now - 30, "lvl": "INFO", "src": "bot", "msg": "Sesión anterior recuperada: 12 canciones"}],
})
wait(300)
shot(w, "18_estado_servidor")
w.status_scroll.verticalScrollBar().setValue(10000)
wait(200)
shot(w, "18b_estado_servidor_abajo")
w._close_status()
wait(400)

# modo streamer: opciones y las 4 formas del mini
w.visual["streamer"] = True
w._set_pills_visible(True)
shot(w, "14_streamer_boton_mini")
w._open_settings()
w._show_menu("main", keep_key="menu:apariencia")
wait(300)
shot(w, "15a_opciones_principal")
w._on_option("menu:apariencia")
wait(300)
shot(w, "15b_apariencia")
w._on_option("menu:size")
wait(300)
shot(w, "15c_tamano")
w._show_menu("apariencia", keep_key="dim_editor")
wait(300)
shot(w, "15d_apariencia_oscuridad")
w._on_option("dim_editor")
wait(400)
shot(w, "16_oscuridad_15")
w.dim_editor.slider.setValue(0.6, emit=True)
wait(200)
shot(w, "16b_oscuridad_60")
w.dim_editor.slider.setValue(0.15, emit=True)
w._options_back()
wait(200)
shot(w, "16c_volver_a_apariencia")
w._close_settings()
wait(400)
for shape in ("cuadrado", "vertical", "ancho", "circulo", "disco"):
    w.visual["mini_shape"] = shape
    w.visual["chroma"] = "#00B140" if shape == "circulo" else ""
    w.visual["mini_dim"] = 0.15
    w.enter_mini()
    wait(500)
    m = w.mini
    m._marquee_x = 60
    m.update()
    app.processEvents()
    m.grab().save(str(OUT / f"17_mini_{shape}.png"))
    if shape == "disco":
        wait(700)
        m.grab().save(str(OUT / "17_mini_disco_girando.png"))
        m._inside = True
        m.update()
        m.grab().save(str(OUT / "17_mini_disco_mouse_encima.png"))
        m._inside = False
        m._on_cover_t(0.5)
        m.grab().save(str(OUT / "17_mini_disco_portada_50.png"))
        m._on_cover_t(1.0)
        m.grab().save(str(OUT / "17_mini_disco_portada.png"))
        m._on_cover_t(0.0)
    print("foto mini", shape)
    w.exit_mini()
    wait(200)
print("listo")
