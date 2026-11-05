"""
Fotos de lo nuevo de la 2.0 (karaoke, Discos, Wrapped, reacciones, botones
nuevos, opciones de Música). Sin servidor: los datos son de ejemplo.
Lo corre GitHub junto con vista_previa.py.
"""
import sys
import time
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtGui import QColor, QImage, QLinearGradient, QPainter, QRadialGradient
from PySide6.QtWidgets import QApplication

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "vista_previa_2")
OUT.mkdir(parents=True, exist_ok=True)
app = QApplication(sys.argv)
from cumito import theme as _theme  # noqa: E402
_theme.load_fonts(app)

import cumito.glass_screen as gs  # noqa: E402

gs.IDLE_S = 1e9
SENT = []
log = []


def _err(*exc):
    (OUT / "ERROR.txt").write_text("".join(traceback.format_exception(*exc)), encoding="utf-8")
    sys.__excepthook__(*exc)


sys.excepthook = _err


def wait(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def shot(w, name):
    app.processEvents()
    w.grab().save(str(OUT / f"{name}.png"))
    print("foto:", name)


def art(c1, c2, c3="#FFFFFF", w=400, h=400):
    img = QImage(w, h, QImage.Format_RGB32)
    p = QPainter(img)
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, QColor(c1))
    g.setColorAt(1, QColor(c2))
    p.fillRect(img.rect(), g)
    rg = QRadialGradient(w * 0.7, h * 0.3, w * 0.4)
    col = QColor(c3)
    col.setAlpha(150)
    rg.setColorAt(0, col)
    col.setAlpha(0)
    rg.setColorAt(1, col)
    p.fillRect(img.rect(), rg)
    p.end()
    return img


w = gs.GlassScreen()
w.send_command = lambda a, **kw: SENT.append((a, kw))
w.my_name = lambda: "Juan"
for key, (a, b) in {"https://img/1": ("#E0457B", "#6C4CF5"), "https://img/2": ("#F7A35C", "#6C4CF5"),
                    "https://img/3": ("#B8323A", "#3A2D6B"), "https://img/4": ("#22A699", "#1F5FBF"),
                    "https://img/5": ("#F2D16B", "#D1517A"), "https://img/6": ("#3DBE7A", "#1F5FBF")}.items():
    w.art_cache.put(key, art(a, b))
w.art_cache.put("disco:abc", art("#101018", "#8E6CF2", "#F2D16B"))
FEAT = ["prev", "seek", "repeat", "shuffle", "sleep", "normalize", "radio", "lyrics", "react", "albums", "stats",
        "spotify"]
now = time.time()
state = {
    "connected": True, "host_label": "Admin", "server_v": 2, "features": FEAT,
    "now_playing": {"title": "Ojitos Lindos", "duration": 258, "elapsed": 41, "paused": False,
                    "art_url": "https://img/1", "uploader": "Bad Bunny, Bomba Estéreo", "who": "Ana",
                    "webpage_url": "https://www.youtube.com/watch?v=7GDp7S1HgSk"},
    "queue": [{"uid": i, "title": f"Canción {i}", "duration": 200, "uploader": "Artista", "ready": True,
               "prepared": True, "art_url": f"https://img/{i}", "who": "Pedro"} for i in range(2, 6)],
    "recent": [], "volume": 0.6, "repeat": "all", "radio": True, "normalize": False,
    "sleep": {"at": now + 29 * 60, "eot": False}, "can_prev": True, "albums_rev": 3,
}
w.show()
# ---- inicio (no suena nada) ----
home = {**state, "now_playing": None, "queue": [], "members": ["Ana", "Pedro", "Juan"],
        "recent": [{"title": t, "uploader": a, "webpage_url": f"https://yt/r{i}", "art_url": f"https://img/{i + 2}"}
                   for i, (t, a) in enumerate([("Bohemian Rhapsody", "Queen"), ("Highest in the Room", "Travis Scott"),
                                               ("La Bachata", "Manuel Turizo"), ("Gasolina", "Daddy Yankee")])]}
w.set_state(home)
w.set_albums([{"id": 1, "name": "Perreo de los viernes", "owner": "Ana", "color": "#F2D16B", "cover": None,
               "count": 24, "arts": []},
              {"id": 2, "name": "Para estudiar", "owner": "Pedro", "color": "#1F2D5C", "cover": None, "count": 41,
               "arts": []},
              {"id": 3, "name": "Para el carro", "owner": "Juan", "color": "#E0457B", "cover": "abc", "count": 18,
               "arts": []}])
w.set_activity_list([{"id": 1, "ts": now - 300, "who": "Ana", "kind": "add", "text": "agregó 1 canción",
                      "title": "La Bachata"},
                     {"id": 2, "ts": now - 100, "who": "Pedro", "kind": "album_new", "text": "creó el disco «Para estudiar»"}])
wait(700)
shot(w, "19_inicio")
w.home_scroll.verticalScrollBar().setValue(10000)
wait(200)
shot(w, "19b_inicio_abajo")
w.home_scroll.verticalScrollBar().setValue(0)
w._open_search()
wait(260)
shot(w, "19c_buscar_estirandose")
wait(700)
shot(w, "19d_buscar_desde_inicio")
w.recent_searches = ["bad bunny", "travis scott", "la bachata", "queen"]
w._refresh_search_home()
wait(300)
shot(w, "19e_buscar_recientes")
w._set_search_kind("all")
w.search_tabs.set_current("all")
wait(200)
shot(w, "19f_pestana_moviendose")
wait(600)
w._set_search_kind("music")
w.search_tabs.set_current("music")
w._close_search()
wait(800)
shot(w, "19g_buscar_cerrado")

w.set_state(state)
w._set_art_background(w.art_cache.get("https://img/1"))
wait(500)
shot(w, "20_principal_2_0")
w._open_search()
wait(900)
shot(w, "20c_buscar_desde_arriba")
w._close_search()
wait(800)
log.append(f"botones: shuffle={w.btn_shuffle.isVisible()} repeat={w.btn_repeat.isVisible()} "
           f"heart={w.btn_heart.isVisible()} lyrics={w.btn_lyrics.isVisible()} react={w.btn_react.isVisible()} "
           f"discos_pill={w.discos_pill.isVisible()} prev_on={w.btn_prev.isEnabled()} seek={w.progress.seekable}")

# servidor viejo: nada nuevo a la vista
w.set_state({**state, "features": None})
wait(200)
shot(w, "20b_servidor_viejo")
log.append(f"servidor viejo: shuffle={w.btn_shuffle.isVisible()} heart={w.btn_heart.isVisible()} "
           f"discos_pill={w.discos_pill.isVisible()} prev_on={w.btn_prev.isEnabled()}")
w.set_state(state)
wait(200)

# barra: arrastrando a la mitad
w.progress._hover = True
w.progress._drag = 0.5
w._on_scrub(0.5)
shot(w, "21_barra_arrastrando")
f = w.progress._drag
w.progress._drag = None
w._on_seek_bar(f)
log.append(f"adelantar: {SENT[-1]}")
w.progress._hover = False

# reacciones
w._toggle_reactions()
wait(300)
shot(w, "22_reacciones_barra")
w.reaction_bar.hide()
w.set_state({"reaction": {"id": 5, "who": "Pedro", "emoji": "🔥", "ts": time.time()}})
w.set_state({"reaction": {"id": 6, "who": "Ana", "emoji": "💜", "ts": time.time()}})
wait(700)
shot(w, "23_reacciones_flotando")
wait(1800)

# karaoke
LRC = "\n".join(f"[00:{t:05.2f}] {line}" for t, line in [
    (11.22, "Hace mucho tiempo le hago caso al corazón"),
    (17.32, "Y pasan los días, los meses pensando en tu olor"),
    (23.21, "Ha llegado el tiempo para usar la razón"),
    (29.40, "Pero aquí sigo yo"),
    (35.10, "Mirándote a los ojitos lindos"),
    (41.00, "Esos ojitos que me tienen en el limbo, lindo"),
    (47.50, "Una noche más contigo"),
    (52.30, "Y otra más, y otra más"),
    (57.80, "Que no se acabe nunca"),
])
w.open_lyrics()
wait(500)
log.append(f"pidió la letra: {SENT[-1]}")
w.set_lyrics({"found": True, "synced": LRC, "plain": None, "webpage_url": state["now_playing"]["webpage_url"]})
w._local_elapsed = 43.5
w._lyrics_follow()
wait(700)
shot(w, "24_karaoke")
w._local_elapsed = 53.0
w._lyrics_follow()
wait(600)
shot(w, "24b_karaoke_avanza")
w.set_lyrics({"found": False, "webpage_url": state["now_playing"]["webpage_url"]})
wait(200)
shot(w, "24c_karaoke_sin_letra")
w._close_lyrics()
wait(450)

# Discos
ALBUMS = [
    {"id": 1, "name": "Para el carro", "owner": "Juan", "color": "#E0457B", "cover": "abc", "count": 18,
     "duration": 3900, "arts": []},
    {"id": 2, "name": "Viernes", "owner": "Ana", "color": "#4FB4D8", "cover": None, "count": 7, "duration": 1500,
     "arts": ["https://img/2", "https://img/3", "https://img/4", "https://img/5"]},
    {"id": 3, "name": "Los clásicos de siempre", "owner": "Pedro", "color": "#F2A33A", "cover": None, "count": 1,
     "duration": 200, "arts": ["https://img/6"]},
    {"id": 4, "name": "Vacío", "owner": "Juan", "color": "#3DBE7A", "cover": None, "count": 0, "duration": 0,
     "arts": []},
]
w.open_albums()
w.set_albums(ALBUMS)
wait(600)
shot(w, "25_discos")
alb = dict(ALBUMS[0], tracks=[{"id": 10 + i, "title": t, "webpage_url": f"https://yt/{i}", "duration": 180 + i * 7,
                               "uploader": a, "art_url": f"https://img/{i % 6 + 1}", "added_by": "Juan"}
                              for i, (t, a) in enumerate([("Ojitos Lindos", "Bad Bunny"), ("La Bachata", "Manuel Turizo"),
                                                          ("Gasolina", "Daddy Yankee"), ("Tití Me Preguntó", "Bad Bunny"),
                                                          ("Provenza", "KAROL G")])])
w.albums_view.open_album(alb, fetch=False)
w.set_album(alb)
wait(400)
shot(w, "26_disco_pagina")
w.albums_view.page_scroll.verticalScrollBar().setValue(10000)
wait(200)
shot(w, "26b_disco_pagina_abajo")
w.albums_view.open_editor(None)
w.albums_view.e_name.setText("Para la playa")
w.albums_view._set_color("#4FB4D8")
wait(300)
shot(w, "27_disco_nuevo")
w.albums_view.open_editor(ALBUMS[0])
wait(300)
shot(w, "27b_disco_editar")
w.albums_view._save()
log.append(f"guardar disco: {SENT[-1][0]} {sorted(SENT[-1][1])}")
w._close_albums()
wait(450)

# corazón
w._open_picker()
wait(300)
shot(w, "28_guardar_en_disco")
w.album_picker.close_picker()
w.on_album_added({"id": 1, "added": 1})
wait(200)
shot(w, "28b_guardada")
wait(2200)

# Wrapped
w.open_wrapped()
wait(450)
w.set_stats({"period": "month", "plays": 214, "minutes": 683, "days": 19, "skipped": 31,
             "top_songs": [{"title": t, "uploader": a, "plays": n, "art_url": f"https://img/{i + 1}"}
                           for i, (t, a, n) in enumerate([("Ojitos Lindos", "Bad Bunny", 14), ("La Bachata", "Manuel Turizo", 11),
                                                          ("Gasolina", "Daddy Yankee", 9), ("Provenza", "KAROL G", 8),
                                                          ("DtMF", "Bad Bunny", 7)])],
             "top_artists": [{"name": n, "plays": p} for n, p in [("Bad Bunny", 40), ("KAROL G", 22), ("Feid", 15),
                                                                   ("Manuel Turizo", 12), ("Daddy Yankee", 9)]],
             "top_people": [{"name": n, "plays": p} for n, p in [("Juan", 90), ("Ana", 64), ("Pedro", 41), ("Radio", 19)]],
             "hours": [0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 2, 4, 6, 5, 4, 6, 8, 10, 14, 20, 26, 31, 22, 9]})
wait(500)
shot(w, "29_wrapped")
w.wrapped_view.scroll.verticalScrollBar().setValue(10000)
wait(200)
shot(w, "29b_wrapped_abajo")
w._close_wrapped()
wait(450)

# opciones nuevas
w._open_settings()
w._show_menu("main", keep_key="albums")
wait(400)
shot(w, "30_opciones_principal")
w._on_option("menu:musica")
wait(400)
shot(w, "30b_musica")
w._on_option("menu:sleep")
wait(400)
shot(w, "30c_temporizador")
w._options_back()
w._options_back()
w._on_option("menu:conexiones")
wait(400)
shot(w, "30d_teclado_discord")
w._close_settings()
wait(400)

# repetir una
w.set_state({"repeat": "one"})
wait(100)
shot(w, "31_repetir_una")

(OUT / "PRUEBA_2_0.txt").write_text("\n".join(log + [f"mandó: {a} {kw}" for a, kw in SENT]), encoding="utf-8")
print("\n".join(log))
print("listo")
