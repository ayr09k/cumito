"""
Discos: los álbumes que arma el grupo, con su propia portada.

Cada Disco se ve como un vinilo en su funda: la portada cuadrada y, asomando
a la derecha, el disco negro con una etiqueta del color del Disco. Si no
tiene portada, la funda muestra un mosaico con las portadas de sus canciones.

Pantallas (todas dentro del mismo panel):
  - la colección (cuadrícula de fundas + "Nuevo disco")
  - la página de un Disco (portada grande, Reproducir / Aleatorio, canciones)
  - el editor (nombre, color, portada)
Y aparte, AlbumPicker: la tarjeta del corazón ("Guardar en un disco").

Las portadas viajan desde el servidor una sola vez y se guardan en la
caché de imágenes (clave "disco:<hash>").
"""
from __future__ import annotations

import base64

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor, QFont, QImage, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient,
)
from PySide6.QtWidgets import (
    QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy, QStackedWidget,
    QVBoxLayout, QWidget,
)

from . import icons, theme
from .hold import HoldButton

COLORS = ["#8E6CF2", "#E0457B", "#F2A33A", "#3DBE7A", "#4FB4D8", "#1F5FBF", "#D1517A", "#2B2838"]
COVER_UPLOAD_PX = 700


def cover_key(h):
    return f"disco:{h}" if h else None


def fmt_total(seconds):
    m = int(seconds or 0) // 60
    if m >= 60:
        return f"{m // 60} h {m % 60} min"
    return f"{m} min"


def _btn(text, primary=False, icon=None, h=36):
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedHeight(h)
    if icon:
        b.setIcon(icons.icon(icon, "#FFFFFF" if primary else theme.GLASS_TEXT, 15))
        b.setIconSize(QSize(15, 15))
    if primary:
        b.setStyleSheet(
            f"QPushButton {{ background:{theme.GLASS_ACCENT}; color:white; border:none; border-radius:{h // 2}px;"
            " font-size:12.5px; font-weight:800; padding:0 16px; }"
            "QPushButton:hover { background:#9C7EF5; } QPushButton:disabled { background: rgba(142,108,242,0.35); }")
    else:
        b.setStyleSheet(
            f"QPushButton {{ background: rgba(255,255,255,0.10); border:1px solid {theme.GLASS_BORDER};"
            f" border-radius:{h // 2}px; color:{theme.GLASS_TEXT}; font-size:12px; font-weight:700; padding:0 14px; }}"
            "QPushButton:hover { background: rgba(255,255,255,0.18); }")
    return b


def _round_icon(name, size=32, tip=""):
    b = QPushButton()
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedSize(size, size)
    b.setIcon(icons.icon(name, theme.GLASS_TEXT, int(size * 0.5)))
    b.setIconSize(QSize(int(size * 0.5), int(size * 0.5)))
    b.setToolTip(tip)
    b.setStyleSheet(
        f"QPushButton {{ background: rgba(255,255,255,0.12); border:1px solid {theme.GLASS_BORDER};"
        f" border-radius:{size // 2}px; }} QPushButton:hover {{ background: rgba(255,255,255,0.22); }}")
    return b


def _label(text, size=12, weight=700, color=None, wrap=False):
    l = QLabel(text)
    l.setWordWrap(wrap)
    l.setStyleSheet(f"color:{color or theme.GLASS_TEXT}; font-size:{size}px; font-weight:{weight};"
                    " background:transparent;")
    return l


# ---------------------------------------------------------------------------
# La funda con el vinilo
# ---------------------------------------------------------------------------
def _cover_fill(pix, w, h):
    s = pix.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x, y = (s.width() - w) // 2, (s.height() - h) // 2
    return s.copy(x, y, w, h)


def sleeve_pixmap(size: int, cover: QPixmap | None = None, color: str | None = None, arts=(),
                  name: str = "", spin: float = 0.0) -> QPixmap:
    """Funda cuadrada de `size` px con el vinilo asomando a la derecha.
    El dibujo mide size*1.33 de ancho y size de alto."""
    color = QColor(color or theme.GLASS_ACCENT)
    W, H = int(size * 1.33) + 1, size
    dpr = 2.0
    pix = QPixmap(int(W * dpr), int(H * dpr))
    pix.setDevicePixelRatio(dpr)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)

    # --- el vinilo (detrás) ---
    d = size * 0.94
    cx, cy = size * 0.84, H / 2
    rec = QRectF(cx - d / 2, cy - d / 2, d, d)
    g = QRadialGradient(QPointF(cx, cy), d / 2)
    g.setColorAt(0.0, QColor(30, 28, 36))
    g.setColorAt(0.6, QColor(14, 13, 18))
    g.setColorAt(1.0, QColor(6, 6, 9))
    p.setPen(Qt.NoPen)
    p.setBrush(g)
    p.drawEllipse(rec)
    p.setBrush(Qt.NoBrush)
    for k in range(7):   # surcos
        r = d / 2 * (0.42 + k * 0.08)
        p.setPen(QPen(QColor(255, 255, 255, 14 if k % 2 else 9), 1))
        p.drawEllipse(QPointF(cx, cy), r, r)
    # brillo en diagonal
    p.save()
    p.translate(cx, cy)
    p.rotate(spin - 35)
    shine = QLinearGradient(-d / 2, 0, d / 2, 0)
    shine.setColorAt(0.35, QColor(255, 255, 255, 0))
    shine.setColorAt(0.5, QColor(255, 255, 255, 30))
    shine.setColorAt(0.65, QColor(255, 255, 255, 0))
    p.setPen(Qt.NoPen)
    p.setBrush(shine)
    p.drawEllipse(QRectF(-d / 2, -d / 2, d, d))
    p.restore()
    # etiqueta del color del Disco
    lr = d * 0.17
    p.setBrush(color)
    p.drawEllipse(QPointF(cx, cy), lr, lr)
    p.setBrush(QColor(10, 10, 12))
    p.drawEllipse(QPointF(cx, cy), d * 0.025, d * 0.025)

    # --- la funda (encima) ---
    r = max(4.0, size * 0.045)
    sleeve = QRectF(0, 0, size, size)
    path = QPainterPath()
    path.addRoundedRect(sleeve, r, r)
    # sombra suave hacia el vinilo
    for k in range(6):
        p.setPen(QPen(QColor(0, 0, 0, 22 - k * 3), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(sleeve.adjusted(-k, -k * 0.3, k + 1, k * 0.6), r + k, r + k)
    p.setClipPath(path)
    if cover is not None and not cover.isNull():
        p.drawPixmap(sleeve, _cover_fill(cover, int(size * dpr), int(size * dpr)),
                     QRectF(0, 0, size * dpr, size * dpr))
    else:
        bg = QLinearGradient(0, 0, size, size)
        bg.setColorAt(0, color.lighter(125))
        bg.setColorAt(1, color.darker(170))
        p.fillRect(sleeve, bg)
        arts = [a for a in arts if a is not None and not a.isNull()][:4]
        if len(arts) >= 4:
            half = size / 2
            for i, a in enumerate(arts):
                tgt = QRectF((i % 2) * half, (i // 2) * half, half, half)
                p.drawPixmap(tgt, _cover_fill(a, int(half * dpr), int(half * dpr)),
                             QRectF(0, 0, half * dpr, half * dpr))
            p.fillRect(sleeve, QColor(0, 0, 0, 40))
        elif arts:
            p.drawPixmap(sleeve, _cover_fill(arts[0], int(size * dpr), int(size * dpr)),
                         QRectF(0, 0, size * dpr, size * dpr))
        else:
            ic = icons.pixmap("disc", "#FFFFFF", int(size * 0.34))
            p.setOpacity(0.55)
            p.drawPixmap(QPointF((size - size * 0.34) / 2, (size - size * 0.34) / 2 - (size * 0.06 if name else 0)), ic)
            p.setOpacity(1.0)
            if name:
                f = QFont(theme.GLASS_FONT_FAMILY)
                f.setPixelSize(max(9, int(size * 0.1)))
                f.setBold(True)
                p.setFont(f)
                p.setPen(QColor(255, 255, 255, 215))
                p.drawText(QRectF(8, size * 0.66, size - 16, size * 0.3), Qt.AlignHCenter | Qt.AlignTop | Qt.TextWordWrap,
                           name)
    # brillo del cartón
    gl = QLinearGradient(0, 0, 0, size)
    gl.setColorAt(0, QColor(255, 255, 255, 34))
    gl.setColorAt(0.25, QColor(255, 255, 255, 0))
    p.fillRect(sleeve, gl)
    p.setClipping(False)
    p.setPen(QPen(QColor(255, 255, 255, 40), 1))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    p.end()
    return pix


def image_to_b64(path: str) -> str | None:
    """La imagen elegida -> JPEG de máx. 700 px en base64 (para mandarla)."""
    img = QImage(path)
    if img.isNull():
        return None
    if max(img.width(), img.height()) > COVER_UPLOAD_PX:
        img = img.scaled(COVER_UPLOAD_PX, COVER_UPLOAD_PX, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    if img.hasAlphaChannel():
        bg = QImage(img.size(), QImage.Format_RGB32)
        bg.fill(QColor(16, 14, 22))
        p = QPainter(bg)
        p.drawImage(0, 0, img)
        p.end()
        img = bg
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "JPEG", 88)
    buf.close()
    return base64.b64encode(bytes(data)).decode("ascii")


def b64_to_image(b64: str) -> QImage:
    img = QImage()
    try:
        img.loadFromData(QByteArray(base64.b64decode(b64)))
    except Exception:
        pass
    return img


# ---------------------------------------------------------------------------
# piezas
# ---------------------------------------------------------------------------
class _Clickable(QWidget):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self._down = False

    def mousePressEvent(self, ev):
        self._down = ev.button() == Qt.LeftButton
        ev.accept()

    def mouseReleaseEvent(self, ev):
        if self._down and self.rect().contains(ev.position().toPoint()):
            self.clicked.emit()
        self._down = False
        ev.accept()


class AlbumTile(_Clickable):
    """Una funda en la colección."""

    def __init__(self, album, size, pix, parent=None):
        super().__init__(parent)
        self.album = album
        self._size = size
        self._hover = False
        self.setAttribute(Qt.WA_Hover, True)
        self.setFixedSize(int(size * 1.33) + 1, size + 40)
        self._pix = pix
        self.name = album.get("name") or "Disco"
        n = album.get("count", 0)
        self.sub = f"{n} canción" if n == 1 else f"{n} canciones"
        if album.get("owner"):
            self.sub += f" · de {album['owner']}"

    def set_pix(self, pix):
        self._pix = pix
        self.update()

    def enterEvent(self, ev):
        self._hover = True
        self.update()

    def leaveEvent(self, ev):
        self._hover = False
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        if self._pix is not None:
            # al pasar el mouse el vinilo asoma un poquito más
            p.drawPixmap(QPointF(-4 if self._hover else 0, 0), self._pix)
        f = QFont(theme.GLASS_FONT_FAMILY)
        f.setPixelSize(12)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(theme.GLASS_TEXT))
        fm = p.fontMetrics()
        p.drawText(QRectF(2, self._size + 6, self.width() - 4, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(self.name, Qt.ElideRight, self.width() - 6))
        f.setPixelSize(10)
        f.setBold(False)
        p.setFont(f)
        p.setPen(QColor(242, 240, 247, 120))
        fm = p.fontMetrics()
        p.drawText(QRectF(2, self._size + 23, self.width() - 4, 15), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(self.sub, Qt.ElideRight, self.width() - 6))
        p.end()


class _NewTile(_Clickable):
    def __init__(self, size, parent=None):
        super().__init__(parent)
        self._size = size
        self.setFixedSize(int(size * 1.33) + 1, size + 40)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(1, 1, self._size - 2, self._size - 2)
        p.setPen(QPen(QColor(255, 255, 255, 70), 1.4, Qt.DashLine))
        p.setBrush(QColor(255, 255, 255, 14))
        p.drawRoundedRect(r, 8, 8)
        ic = icons.pixmap("plus", "#FFFFFF", 26)
        p.drawPixmap(QPointF(r.center().x() - 13, r.center().y() - 20), ic)
        f = QFont(theme.GLASS_FONT_FAMILY)
        f.setPixelSize(11)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 200))
        p.drawText(QRectF(0, r.center().y() + 10, self._size, 18), Qt.AlignHCenter, "Nuevo disco")
        p.end()


class _AlbumTrackRow(_Clickable):
    remove = Signal()

    def __init__(self, t, pix, parent=None):
        super().__init__(parent)
        self.t = t
        self.setFixedHeight(48)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(6, 4, 4, 4)
        lay.setSpacing(10)
        self.thumb = QLabel()
        self.thumb.setFixedSize(38, 38)
        self.set_pix(pix)
        lay.addWidget(self.thumb)
        col = QVBoxLayout()
        col.setSpacing(0)
        self.title = _label("", 12, 700)
        self.artist = _label("", 10.5, 500, theme.GLASS_TEXT_MUTE)
        self._full = (t.get("title") or "Sin título", t.get("uploader") or "")
        col.addWidget(self.title)
        col.addWidget(self.artist)
        lay.addLayout(col, 1)
        m, s = divmod(int(t.get("duration") or 0), 60)
        lay.addWidget(_label(f"{m}:{s:02d}" if t.get("duration") else "", 10, 600, theme.GLASS_TEXT_MUTE2))
        self.btn_x = QPushButton()
        self.btn_x.setCursor(Qt.PointingHandCursor)
        self.btn_x.setFixedSize(26, 26)
        self.btn_x.setToolTip("Quitar del disco")
        self.btn_x.setIcon(icons.icon("remove", "#C9C5D3", 12))
        self.btn_x.setStyleSheet("QPushButton { background: transparent; border:none; border-radius:13px; }"
                                 "QPushButton:hover { background: rgba(228,91,91,0.30); }")
        self.btn_x.clicked.connect(self.remove.emit)
        lay.addWidget(self.btn_x)
        self.setStyleSheet("_AlbumTrackRow:hover { background: rgba(255,255,255,0.07); border-radius: 10px; }")
        self.setAttribute(Qt.WA_StyledBackground, True)

    def resizeEvent(self, ev):
        w = max(40, self.title.width())
        self.title.setText(self.title.fontMetrics().elidedText(self._full[0], Qt.ElideRight, w))
        self.artist.setText(self.artist.fontMetrics().elidedText(self._full[1], Qt.ElideRight, w))
        super().resizeEvent(ev)

    def set_pix(self, pix):
        out = QPixmap(76, 76)
        out.setDevicePixelRatio(2.0)
        out.fill(Qt.transparent)
        p = QPainter(out)
        p.setRenderHint(QPainter.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, 38, 38), 8, 8)
        p.setClipPath(path)
        if pix is not None and not pix.isNull():
            p.drawPixmap(QRectF(0, 0, 38, 38), _cover_fill(pix, 76, 76), QRectF(0, 0, 76, 76))
        else:
            g = QLinearGradient(0, 0, 38, 38)
            g.setColorAt(0, QColor(theme.GLASS_GRAD_1))
            g.setColorAt(1, QColor(theme.GLASS_GRAD_2))
            p.fillRect(QRectF(0, 0, 38, 38), g)
        p.end()
        self.thumb.setPixmap(out)


# ---------------------------------------------------------------------------
# el panel de Discos
# ---------------------------------------------------------------------------
class AlbumsView(QWidget):
    """Colección / página de un Disco / editor. `send(action, **kw)` habla
    con el servidor; `scroll_factory(widget)` arma un scroll como el resto."""

    closed = Signal()
    toast = Signal(str)

    TILE = 112

    def __init__(self, send, art_cache, scroll_factory, parent=None):
        super().__init__(parent)
        self.send = send
        self.art = art_cache
        self.albums: list[dict] = []
        self.current: dict | None = None     # el Disco abierto
        self._editing: dict | None = None    # None = nuevo
        self._edit_cover_b64 = None
        self._edit_remove_cover = False
        self._edit_color = COLORS[0]
        self._add_after_create = False       # vino del corazón: al crearlo, guardar la canción
        self._tiles: list[AlbumTile] = []
        self._rows: list[_AlbumTrackRow] = []
        self.art.loaded.connect(self._on_art)

        self.stack = QStackedWidget(self)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(self.stack)

        # ---- colección ----
        grid_page = QWidget()
        gl = QVBoxLayout(grid_page)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(8)
        head = QHBoxLayout()
        self.btn_close = _round_icon("back", 30, "Volver")
        self.btn_close.clicked.connect(self.closed.emit)
        head.addWidget(self.btn_close)
        tcol = QVBoxLayout()
        tcol.setSpacing(0)
        tcol.addWidget(_label("Discos", 19, 800, "#FFFFFF"))
        self.grid_sub = _label("Los álbumes del grupo", 10.5, 600, theme.GLASS_TEXT_MUTE2)
        tcol.addWidget(self.grid_sub)
        head.addLayout(tcol, 1)
        gl.addLayout(head)
        self.grid_w = QWidget()
        self.grid = QGridLayout(self.grid_w)
        self.grid.setContentsMargins(4, 8, 4, 20)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(14)
        self.grid.setAlignment(Qt.AlignTop | Qt.AlignHCenter)
        self.grid_scroll = scroll_factory(self.grid_w)
        gl.addWidget(self.grid_scroll, 1)
        self.stack.addWidget(grid_page)

        # ---- página de un Disco ----
        page = QWidget()
        pl = QVBoxLayout(page)
        pl.setContentsMargins(0, 0, 0, 0)
        pl.setSpacing(6)
        phead = QHBoxLayout()
        b = _round_icon("back", 30, "Volver a los discos")
        b.clicked.connect(self.show_grid)
        phead.addWidget(b)
        phead.addStretch()
        self.btn_edit = _round_icon("edit", 30, "Editar el disco")
        self.btn_edit.clicked.connect(lambda: self.open_editor(self.current))
        phead.addWidget(self.btn_edit)
        pl.addLayout(phead)
        body = QWidget()
        bl = QVBoxLayout(body)
        bl.setContentsMargins(4, 0, 4, 20)
        bl.setSpacing(6)
        self.big = QLabel()
        self.big.setAlignment(Qt.AlignCenter)
        self.big.setFixedHeight(176)
        bl.addWidget(self.big)
        self.p_name = _label("", 21, 800, "#FFFFFF", wrap=True)
        self.p_name.setAlignment(Qt.AlignCenter)
        bl.addWidget(self.p_name)
        self.p_sub = _label("", 11, 600, theme.GLASS_TEXT_MUTE)
        self.p_sub.setAlignment(Qt.AlignCenter)
        bl.addWidget(self.p_sub)
        brow = QHBoxLayout()
        brow.setSpacing(8)
        self.btn_play = _btn("Reproducir", primary=True, icon="play")
        self.btn_play.clicked.connect(lambda: self._play(False))
        self.btn_shuffle = _btn("Aleatorio", icon="shuffle")
        self.btn_shuffle.clicked.connect(lambda: self._play(True))
        brow.addWidget(self.btn_play, 1)
        brow.addWidget(self.btn_shuffle, 1)
        bl.addSpacing(4)
        bl.addLayout(brow)
        bl.addSpacing(6)
        self.tracks_box = QVBoxLayout()
        self.tracks_box.setSpacing(2)
        bl.addLayout(self.tracks_box)
        self.empty_tracks = _label("Todavía no tiene canciones.\nToca el corazón ♡ en lo que suena para guardarla aquí.",
                                   11.5, 600, theme.GLASS_TEXT_MUTE2, wrap=True)
        self.empty_tracks.setAlignment(Qt.AlignCenter)
        bl.addWidget(self.empty_tracks)
        bl.addSpacing(14)
        self.btn_delete = HoldButton("Borrar el disco", height=36, font_size=12)
        self.btn_delete.confirmed.connect(self._delete)
        bl.addWidget(self.btn_delete)
        bl.addStretch()
        self.page_scroll = scroll_factory(body)
        pl.addWidget(self.page_scroll, 1)
        self.stack.addWidget(page)

        # ---- editor ----
        ed = QWidget()
        el = QVBoxLayout(ed)
        el.setContentsMargins(0, 0, 0, 0)
        el.setSpacing(8)
        ehead = QHBoxLayout()
        b = _round_icon("back", 30, "Cancelar")
        b.clicked.connect(self._cancel_editor)
        ehead.addWidget(b)
        self.e_title = _label("Nuevo disco", 19, 800, "#FFFFFF")
        ehead.addWidget(self.e_title, 1)
        el.addLayout(ehead)
        ebody = QWidget()
        ebl = QVBoxLayout(ebody)
        ebl.setContentsMargins(6, 4, 6, 16)
        ebl.setSpacing(10)
        self.e_preview = QLabel()
        self.e_preview.setAlignment(Qt.AlignCenter)
        self.e_preview.setFixedHeight(150)
        ebl.addWidget(self.e_preview)
        crow = QHBoxLayout()
        crow.setSpacing(8)
        self.btn_cover = _btn("Elegir portada", icon="image", h=32)
        self.btn_cover.clicked.connect(self._pick_cover)
        self.btn_nocover = _btn("Quitar", h=32)
        self.btn_nocover.clicked.connect(self._remove_cover)
        crow.addStretch()
        crow.addWidget(self.btn_cover)
        crow.addWidget(self.btn_nocover)
        crow.addStretch()
        ebl.addLayout(crow)
        ebl.addWidget(_label("NOMBRE", 10, 800, theme.GLASS_TEXT_MUTE))
        self.e_name = QLineEdit()
        self.e_name.setMaxLength(40)
        self.e_name.setPlaceholderText("Ej. Para el carro, Viernes, Los clásicos…")
        self.e_name.setFixedHeight(38)
        self.e_name.setStyleSheet(
            "QLineEdit { background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.28);"
            f" border-radius: 12px; padding: 0 12px; color: {theme.GLASS_TEXT}; font-size: 13px; font-weight:700; }}"
            "QLineEdit:focus { border: 1px solid rgba(142,108,242,0.95); }")
        self.e_name.textChanged.connect(lambda _t: self._refresh_preview())
        self.e_name.returnPressed.connect(self._save)
        ebl.addWidget(self.e_name)
        ebl.addWidget(_label("COLOR", 10, 800, theme.GLASS_TEXT_MUTE))
        sw = QHBoxLayout()
        sw.setSpacing(8)
        self._swatches = []
        for c in COLORS:
            s = QPushButton()
            s.setCursor(Qt.PointingHandCursor)
            s.setFixedSize(28, 28)
            s.clicked.connect(lambda _=False, c=c: self._set_color(c))
            self._swatches.append((c, s))
            sw.addWidget(s)
        sw.addStretch()
        ebl.addLayout(sw)
        ebl.addSpacing(6)
        self.btn_save = _btn("Crear disco", primary=True, h=40)
        self.btn_save.clicked.connect(self._save)
        ebl.addWidget(self.btn_save)
        ebl.addStretch()
        self.edit_scroll = scroll_factory(ebody)
        el.addWidget(self.edit_scroll, 1)
        self.stack.addWidget(ed)

    # ---------- datos que llegan ----------
    def set_albums(self, albums):
        self.albums = list(albums or [])
        self._fill_grid()
        if self.current:
            mine = next((a for a in self.albums if a["id"] == self.current["id"]), None)
            if mine is None and self.stack.currentIndex() == 1:
                self.show_grid()

    def set_album(self, album):
        """La respuesta a album_get / crear / editar."""
        if not album:
            if self.stack.currentIndex() == 1:
                self.show_grid()
            return
        if self._add_after_create and self._editing is None and self.stack.currentIndex() == 2:
            self._add_after_create = False
            self.send("album_add", id=album["id"], current=True)
        if self.stack.currentIndex() == 2 or (self.current and self.current.get("id") == album["id"]):
            self.open_album(album, fetch=False)

    def refresh(self):
        self.send("album_list")
        if self.current and self.stack.currentIndex() == 1:
            self.send("album_get", id=self.current["id"])

    # ---------- portadas ----------
    def _cover(self, album):
        k = cover_key(album.get("cover"))
        if not k:
            return None
        pix = self.art.get(k)
        if pix is None and not getattr(self, f"_asked_{album['cover']}", False):
            setattr(self, f"_asked_{album['cover']}", True)
            self.send("album_cover", cover=album["cover"])
        return pix

    def _arts(self, album):
        out = []
        for url in album.get("arts") or []:
            pix = self.art.get(url)
            if pix is None:
                self.art.request(url)
            out.append(pix)
        return out

    def _sleeve(self, album, size):
        return sleeve_pixmap(size, self._cover(album), album.get("color"), self._arts(album), album.get("name") or "")

    def _on_art(self, key, _pix):
        if self.stack.currentIndex() == 0:
            for t in self._tiles:
                a = t.album
                if key == cover_key(a.get("cover")) or key in (a.get("arts") or []):
                    t.set_pix(self._sleeve(a, self.TILE))
        elif self.stack.currentIndex() == 1 and self.current:
            a = self.current
            if key == cover_key(a.get("cover")) or key in (a.get("arts") or []):
                self.big.setPixmap(self._sleeve(a, 168))
            for r in self._rows:
                if r.t.get("art_url") == key:
                    r.set_pix(_pix)
        elif self.stack.currentIndex() == 2:
            self._refresh_preview()

    # ---------- colección ----------
    def _fill_grid(self):
        while self.grid.count():
            it = self.grid.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._tiles = []
        new = _NewTile(self.TILE)
        new.clicked.connect(lambda: self.open_editor(None))
        self.grid.addWidget(new, 0, 0)
        for i, a in enumerate(self.albums, start=1):
            t = AlbumTile(a, self.TILE, self._sleeve(a, self.TILE))
            t.clicked.connect(lambda a=a: self.open_album(a))
            self._tiles.append(t)
            self.grid.addWidget(t, i // 2, i % 2)
        n = len(self.albums)
        self.grid_sub.setText("Los álbumes del grupo" if not n else
                              f"{n} disco" + ("" if n == 1 else "s") + " del grupo")

    def show_grid(self):
        self.current = None
        self.stack.setCurrentIndex(0)

    # ---------- página ----------
    def open_album(self, album, fetch=True):
        self.current = album
        self.stack.setCurrentIndex(1)
        self.big.setPixmap(self._sleeve(album, 168))
        self.p_name.setText(album.get("name") or "Disco")
        n = album.get("count", 0)
        bits = [f"de {album['owner']}"] if album.get("owner") else []
        bits.append(f"{n} canción" if n == 1 else f"{n} canciones")
        if album.get("duration"):
            bits.append(fmt_total(album["duration"]))
        self.p_sub.setText(" · ".join(bits))
        self.btn_delete.reset()
        tracks = album.get("tracks")
        self.btn_play.setEnabled(bool(n))
        self.btn_shuffle.setEnabled(n > 1)
        if tracks is not None:
            self._fill_tracks(tracks)
        if fetch:
            self.send("album_get", id=album["id"])

    def _fill_tracks(self, tracks):
        while self.tracks_box.count():
            it = self.tracks_box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self._rows = []
        for t in tracks:
            pix = self.art.get(t.get("art_url"))
            if pix is None:
                self.art.request(t.get("art_url"))
            row = _AlbumTrackRow(t, pix)
            row.setToolTip("Tócala para agregarla a la lista")
            row.clicked.connect(lambda t=t: self._play_track(t))
            row.remove.connect(lambda t=t: self._remove_track(t))
            self._rows.append(row)
            self.tracks_box.addWidget(row)
        self.empty_tracks.setVisible(not tracks)

    def _play(self, shuffle):
        if self.current:
            self.send("album_play", id=self.current["id"], shuffle=shuffle)
            self.toast.emit(f"Poniendo «{self.current.get('name')}»" + (" en aleatorio" if shuffle else ""))

    def _play_track(self, t):
        if t.get("webpage_url"):
            self.send("play", query=t["webpage_url"])
            self.toast.emit(f"Agregando «{t.get('title')}»")

    def _remove_track(self, t):
        if self.current:
            self.send("album_remove", id=self.current["id"], track_id=t["id"])

    def _delete(self):
        if self.current:
            self.send("album_delete", id=self.current["id"])
            self.toast.emit(f"Borraste «{self.current.get('name')}»")
            self.show_grid()

    # ---------- editor ----------
    def open_editor(self, album=None, add_current=False):
        self._editing = album
        self._add_after_create = add_current
        self._edit_cover_b64 = None
        self._edit_remove_cover = False
        self._edit_color = (album or {}).get("color") or COLORS[len(self.albums) % len(COLORS)]
        self.e_title.setText("Editar disco" if album else "Nuevo disco")
        self.btn_save.setText("Guardar" if album else ("Crear y guardar la canción" if add_current else "Crear disco"))
        self.e_name.setText((album or {}).get("name") or "")
        self._set_color(self._edit_color)
        self.stack.setCurrentIndex(2)
        self.e_name.setFocus()

    def _set_color(self, c):
        self._edit_color = c
        for col, s in self._swatches:
            ring = "3px solid #FFFFFF" if col == c else "1px solid rgba(255,255,255,0.3)"
            s.setStyleSheet(f"QPushButton {{ background:{col}; border:{ring}; border-radius:14px; }}")
        self._refresh_preview()

    def _edit_cover_pix(self):
        if self._edit_cover_b64:
            return QPixmap.fromImage(b64_to_image(self._edit_cover_b64))
        if self._editing and not self._edit_remove_cover:
            return self._cover(self._editing)
        return None

    def _refresh_preview(self):
        a = self._editing or {}
        pix = sleeve_pixmap(140, self._edit_cover_pix(), self._edit_color, self._arts(a) if a else (),
                            self.e_name.text().strip() or "Nuevo disco")
        self.e_preview.setPixmap(pix)
        self.btn_nocover.setVisible(bool(self._edit_cover_b64 or (a.get("cover") and not self._edit_remove_cover)))

    def _pick_cover(self):
        path, _ = QFileDialog.getOpenFileName(self, "Elegir portada", "",
                                              "Imágenes (*.png *.jpg *.jpeg *.webp *.bmp *.gif)")
        if not path:
            return
        b64 = image_to_b64(path)
        if not b64:
            self.toast.emit("No pude abrir esa imagen")
            return
        self._edit_cover_b64 = b64
        self._edit_remove_cover = False
        self._refresh_preview()

    def _remove_cover(self):
        self._edit_cover_b64 = None
        self._edit_remove_cover = True
        self._refresh_preview()

    def _save(self):
        name = self.e_name.text().strip()
        if not name:
            self.e_name.setFocus()
            self.toast.emit("Ponle un nombre al disco")
            return
        if self._editing:
            kw = {"id": self._editing["id"], "name": name, "color": self._edit_color}
            if self._edit_cover_b64:
                kw["cover_b64"] = self._edit_cover_b64
            elif self._edit_remove_cover:
                kw["remove_cover"] = True
            self.send("album_update", **kw)
        else:
            kw = {"name": name, "color": self._edit_color}
            if self._edit_cover_b64:
                kw["cover_b64"] = self._edit_cover_b64
            self.send("album_create", **kw)
        self.btn_save.setEnabled(False)
        QTimer.singleShot(4000, lambda: self.btn_save.setEnabled(True))

    def _cancel_editor(self):
        if self._editing:
            self.open_album(self._editing, fetch=False)
        else:
            self.show_grid()

    def editor_done(self):
        self.btn_save.setEnabled(True)


# ---------------------------------------------------------------------------
# El corazón: "Guardar en un disco"
# ---------------------------------------------------------------------------
class AlbumPicker(QWidget):
    """Tarjeta flotante encima de la ventana: elegir en qué Disco guardar lo
    que suena (o crear uno nuevo)."""

    chosen = Signal(int)
    new_album = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.hide()
        self.card = QWidget(self)
        self.card.setObjectName("card")
        self.card.setStyleSheet("#card { background: rgba(22,20,30,0.97); border:1px solid rgba(255,255,255,0.18);"
                                " border-radius: 20px; }")
        cl = QVBoxLayout(self.card)
        cl.setContentsMargins(16, 14, 16, 14)
        cl.setSpacing(8)
        cl.addWidget(_label("Guardar en un disco", 15, 800, "#FFFFFF"))
        self.song = _label("", 11, 600, theme.GLASS_TEXT_MUTE)
        cl.addWidget(self.song)
        self.list_w = QWidget()
        self.list_l = QVBoxLayout(self.list_w)
        self.list_l.setContentsMargins(0, 4, 0, 4)
        self.list_l.setSpacing(2)
        cl.addWidget(self.list_w)
        nb = _btn("Nuevo disco", icon="plus", h=34)
        nb.clicked.connect(lambda: (self.close_picker(), self.new_album.emit()))
        cl.addWidget(nb)

    def open(self, albums, title, art_cache, sleeve_fn):
        self.song.setText(title or "")
        while self.list_l.count():
            it = self.list_l.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for a in albums[:7]:
            row = _Clickable()
            row.setFixedHeight(46)
            row.setAttribute(Qt.WA_StyledBackground, True)
            row.setStyleSheet("_Clickable:hover { background: rgba(255,255,255,0.08); border-radius: 10px; }")
            rl = QHBoxLayout(row)
            rl.setContentsMargins(4, 2, 4, 2)
            rl.setSpacing(10)
            th = QLabel()
            th.setPixmap(sleeve_fn(a, 38))
            th.setFixedSize(52, 38)
            rl.addWidget(th)
            col = QVBoxLayout()
            col.setSpacing(0)
            col.addWidget(_label(a.get("name") or "Disco", 12, 700))
            n = a.get("count", 0)
            col.addWidget(_label(f"{n} canción" if n == 1 else f"{n} canciones", 10, 600, theme.GLASS_TEXT_MUTE2))
            rl.addLayout(col, 1)
            row.clicked.connect(lambda a=a: (self.close_picker(), self.chosen.emit(a["id"])))
            self.list_l.addWidget(row)
        if not albums:
            self.list_l.addWidget(_label("Todavía no hay discos. ¡Crea el primero!", 11, 600, theme.GLASS_TEXT_MUTE2))
        pw = self.parentWidget()
        self.setGeometry(pw.rect())
        self.card.setFixedWidth(pw.width() - 40)
        self.card.adjustSize()
        self.card.move(20, max(60, (pw.height() - self.card.height()) // 2))
        self.show()
        self.raise_()

    def close_picker(self):
        self.hide()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(5, 5, 8, 150))
        p.end()

    def mousePressEvent(self, ev):
        if not self.card.geometry().contains(ev.position().toPoint()):
            self.close_picker()
        ev.accept()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self.close_picker()
        else:
            super().keyPressEvent(ev)


class Toast(QLabel):
    """Avisito que aparece abajo unos segundos."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet("background: rgba(20,18,28,0.94); color:#fff; border:1px solid rgba(255,255,255,0.2);"
                           " border-radius: 16px; padding: 8px 14px; font-size: 12px; font-weight: 700;")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()
        self._t = QTimer(self)
        self._t.setSingleShot(True)
        self._t.timeout.connect(self.hide)

    def show_text(self, text, ms=2600):
        pw = self.parentWidget()
        self.setText(text)
        self.setFixedWidth(min(pw.width() - 40, max(160, self.fontMetrics().horizontalAdvance(text) + 40)))
        self.adjustSize()
        self.move((pw.width() - self.width()) // 2, pw.height() - self.height() - 236)
        self.show()
        self.raise_()
        self._t.start(ms)
