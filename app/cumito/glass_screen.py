"""
GlassScreen: la ventana del reproductor con el diseño "glass" aprobado --
portada a pantalla completa, paneles translúcidos encima, barra de título
con píldora de búsqueda, bandeja de playlist que sube con el scroll,
buscador en mosaico a pantalla completa.

Nota de rendimiento (por qué esto no mata un equipo modesto): un "glass"
de verdad -- desenfocar lo que hay DETRÁS de una ventana transparente, el
escritorio -- es caro, y necesita APIs nativas de Windows (Acrylic/Mica).
Acá no hace falta nada de eso: la ventana ya no es transparente al
escritorio, se llena con la portada de la canción, que la propia app
dibuja. El efecto "glass" de los paneles de encima (título, bandeja,
buscador) se logra con transparencia simple (alpha), SIN desenfoque en
ningún lado, ni en vivo ni precalculado -- así que el costo real es
mínimo: lo único que se hace por canción es bajar la miniatura una vez
(art_cache.py) y guardarla. El switch de "glass" solo cambia esos paneles
entre translúcidos y opacos.

La usa la única ventana de Cumito (main.py la hereda como CumitoWindow),
que le agrega sus propios renglones de ajustes sobreescribiendo
settings_rows()/on_settings_row() -- ver connect_screen.py para la
pantalla chiquita que aparece antes de esta, solo la primera vez que no
se conoce todavía la dirección del servidor.
"""
from __future__ import annotations

import math
import time
import uuid

from PySide6.QtCore import (
    QAbstractAnimation, QEasingCurve, QEvent, QParallelAnimationGroup, QPoint, QPropertyAnimation,
    QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal,
)
from PySide6.QtGui import QColor, QCursor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QFrame, QGraphicsOpacityEffect, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QScrollArea, QSizePolicy, QVBoxLayout, QWidget,
)

from . import icons, theme
from .anim_widgets import HopLoader, Spinner, stagger_fade_in
from .art_cache import ArtCache
from .activity import ActivityFeed, Ticker
from .hold import HoldButton, HoldConfirm
from .wheel import OptionWheel
from .mini import CHROMAS, SHAPE_NAMES, MiniWindow
from .dim_editor import DimEditor

W, H = theme.GLASS_WINDOW_W, theme.GLASS_WINDOW_H
SHEET_H = int(H * 0.74)
PAN_MAX_W = int(W * 1.4)   # el fondo es un poco más ancho que la ventana y se pasea
PAN_EDGE_S = 30.0          # segundos de una esquina a la otra
PAN_TICK_MS = 80
IDLE_S = 8.0               # sin tocar nada este tiempo: solo queda la portada y el nombre
PANEL_TOP = 50       # donde arrancan las hojas de buscador/ajustes (debajo de cerrar/minimizar)
CARD_W, CARD_H = 124, 158   # las cards de la vista previa de playlist
TICK_MS = 250  # a cuánto se refresca el progreso / ecualizador -- bajo a propósito


def fmt_time(seconds):
    seconds = int(seconds or 0)
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


def _cover_pixmap(pix: QPixmap, w: int, h: int) -> QPixmap:
    """Como 'background-size: cover' de CSS: escala y recorta al centro."""
    if pix is None or pix.isNull():
        return pix
    scaled = pix.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    x = max(0, (scaled.width() - w) // 2)
    y = max(0, (scaled.height() - h) // 2)
    return scaled.copy(x, y, w, h)


def _rounded(pix: QPixmap, radius: int) -> QPixmap:
    if pix is None or pix.isNull():
        return pix
    out = QPixmap(pix.size())
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, pix.width(), pix.height()), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pix)
    p.end()
    return out


def _placeholder_art(w, h) -> QPixmap:
    """Degradado morado/celeste/rosado, antes de que haya portada real."""
    pix = QPixmap(w, h)
    p = QPainter(pix)
    g = QLinearGradient(0, 0, 0, h)
    g.setColorAt(0.0, QColor("#211f29"))
    g.setColorAt(0.55, QColor("#141319"))
    g.setColorAt(1.0, QColor("#09090c"))
    p.fillRect(pix.rect(), g)
    r1 = QRadialGradient(w * 0.5, h * 0.28, w * 0.75)
    r1.setColorAt(0, QColor(142, 108, 242, 120))
    r1.setColorAt(1, QColor(142, 108, 242, 0))
    p.fillRect(pix.rect(), r1)
    r2 = QRadialGradient(w * 0.78, h * 0.82, w * 0.6)
    r2.setColorAt(0, QColor(79, 180, 216, 80))
    r2.setColorAt(1, QColor(79, 180, 216, 0))
    p.fillRect(pix.rect(), r2)
    r3 = QRadialGradient(w * 0.18, h * 0.9, w * 0.55)
    r3.setColorAt(0, QColor(209, 81, 122, 70))
    r3.setColorAt(1, QColor(209, 81, 122, 0))
    p.fillRect(pix.rect(), r3)
    p.end()
    return pix


def _pending_thumb(w, h, radius) -> QPixmap:
    """Miniatura de una canción que AÚN NO está lista: gris, con borde
    punteado -- para que se note claramente que falta prepararla."""
    pix = QPixmap(w, h)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(1, 1, w - 2, h - 2), radius, radius)
    p.fillPath(path, QColor(255, 255, 255, 18))
    pen = QPen(QColor(255, 255, 255, 70), 1.2, Qt.DashLine)
    p.setPen(pen)
    p.drawPath(path)
    p.end()
    return pix


def _with_ready_border(pix: QPixmap, radius) -> QPixmap:
    """La portada con un borde verde: "¡ya está lista!" (dura 2 segundos)."""
    return _with_border(pix, radius, "#3DDC84")


def _with_border(pix: QPixmap, radius, color, width=2.6) -> QPixmap:
    out = QPixmap(pix)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setPen(QPen(QColor(color), width))
    p.setBrush(Qt.NoBrush)
    d = width / 2
    p.drawRoundedRect(QRectF(d, d, out.width() - 2 * d, out.height() - 2 * d), radius, radius)
    p.end()
    return out


def _gradient_label(w, h, radius, c1="#8E6CF2", c2="#4FB4D8") -> QPixmap:
    """Miniatura de relleno (mientras no hay portada real todavía)."""
    pix = QPixmap(w, h)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)
    g = QLinearGradient(0, 0, w, h)
    g.setColorAt(0, QColor(c1))
    g.setColorAt(1, QColor(c2))
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, w, h), radius, radius)
    p.fillPath(path, g)
    p.end()
    return pix


# ======================================================================
# Widgets chicos reutilizables
# ======================================================================

class _IconButton(QPushButton):
    """Botón redondo con un ícono SVG (ver icons.py / assets/icons)."""

    def __init__(self, icon_name, danger=False, size=26, icon_size=None, icon_color=None, parent=None):
        super().__init__("", parent)
        self.danger = danger
        self.setFixedSize(size, size)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self._radius = size // 2
        self._icon_size = icon_size or max(12, int(size * 0.55))
        self._icon_color = icon_color or (theme.GLASS_DANGER if danger else theme.GLASS_TEXT)
        self.set_icon(icon_name)

    def set_icon(self, icon_name):
        self._icon_name = icon_name
        self.setIcon(icons.icon(icon_name, self._icon_color, self._icon_size))
        self.setIconSize(QSize(self._icon_size, self._icon_size))

    def apply_glass(self, glass: bool):
        bg = theme.GLASS_CHROME_BG if glass else theme.FLAT_CHROME_BG
        hover = theme.GLASS_CHROME_BG_HOVER if glass else "rgba(255,255,255,0.2)"
        color = theme.GLASS_DANGER if self.danger else theme.GLASS_TEXT
        border = theme.GLASS_BORDER if glass else "rgba(255,255,255,0.14)"
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg}; color: {color}; border: 1px solid {border};
                border-radius: {self._radius}px; font-size: 12px; font-weight: 600;
            }}
            QPushButton:hover {{ background: {hover}; }}
        """)


class _Pill(QPushButton):
    def __init__(self, text, icon_name=None, parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFlat(True)
        self.setFixedHeight(32)
        self.setFont(QFont(theme.GLASS_FONT_FAMILY, 10, QFont.DemiBold))
        self.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        if icon_name:
            self.setIcon(icons.icon(icon_name, theme.GLASS_TEXT, 15))
            self.setIconSize(QSize(15, 15))

    def apply_glass(self, glass: bool):
        bg = theme.GLASS_CHROME_BG if glass else theme.FLAT_CHROME_BG
        hover = theme.GLASS_CHROME_BG_HOVER if glass else "rgba(255,255,255,0.2)"
        border = theme.GLASS_BORDER if glass else "rgba(255,255,255,0.14)"
        self.setStyleSheet(f"""
            QPushButton {{
                background: {bg}; color: {theme.GLASS_TEXT}; border: 1px solid {border};
                border-radius: 16px; padding: 4px 16px;
            }}
            QPushButton:hover {{ background: {hover}; }}
        """)


class _GlassSwitch(QWidget):
    toggled = Signal(bool)

    def __init__(self, on=True, parent=None):
        super().__init__(parent)
        self.setFixedSize(34, 18)
        self.setCursor(Qt.PointingHandCursor)
        self._on = on

    def isOn(self):
        return self._on

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._on = not self._on
            self.update()
            self.toggled.emit(self._on)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(142, 108, 242, 130) if self._on else QColor(255, 255, 255, 40))
        p.drawRoundedRect(self.rect(), 9, 9)
        knob_x = self.width() - 16 if self._on else 2
        p.setBrush(QColor(theme.GLASS_ACCENT) if self._on else QColor("#ffffff"))
        p.drawEllipse(knob_x, 2, 14, 14)


class _ProgressBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(4)
        self._frac = 0.0

    def setFraction(self, f):
        self._frac = max(0.0, min(1.0, f))
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 55))
        p.drawRoundedRect(self.rect(), 2, 2)
        if self._frac > 0:
            w = max(4, int(self.width() * self._frac))
            p.setBrush(QColor("#ffffff"))
            p.drawRoundedRect(0, 0, w, self.height(), 2, 2)


class _Equalizer(QWidget):
    """Barritas animadas, a pocos fps (ver TICK_MS) y quietas si no suena
    nada -- lo que de verdad importa para no gastar batería de más."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(20, 14)
        self._phase = 0
        self._active = False

    def setActive(self, active: bool):
        self._active = active
        self.setVisible(active)

    def tick(self):
        if self._active:
            self._phase += 1
            self.update()

    def paintEvent(self, ev):
        if not self._active:
            return
        p = QPainter(self)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(theme.GLASS_ACCENT))
        heights = [4, 11, 7]
        for i, base in enumerate(heights):
            h = base + (3 if (self._phase + i) % 3 == 0 else 0)
            p.drawRect(i * 7, self.height() - h, 4, h)


class _ElidedLabel(QLabel):
    """Un texto de una sola línea que NUNCA se sale de su espacio: si no
    cabe, se corta con "…" (y el nombre completo sale al dejar el mouse
    encima). Así un título larguísimo no empuja la X ni nada más."""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._full = text or ""
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(1)
        self._apply()

    def setText(self, text):
        self._full = text or ""
        self._apply()

    def text(self):
        return self._full

    def resizeEvent(self, ev):
        super().resizeEvent(ev)
        self._apply()

    def changeEvent(self, ev):
        super().changeEvent(ev)
        if ev.type() in (QEvent.FontChange, QEvent.StyleChange):
            self._apply()

    def _apply(self):
        fm = self.fontMetrics()
        shown = fm.elidedText(self._full, Qt.ElideRight, max(1, self.width()))
        QLabel.setText(self, shown)
        self.setToolTip(self._full if shown != self._full else "")


class _SwipeHint(QWidget):
    """El "PLAYLIST" de abajo: cada 3 segundos unas flechitas suben y se
    desvanecen (como el gesto de deslizar hacia arriba). Se puede tocar
    para abrir la playlist."""
    clicked = Signal()
    EVERY_MS = 3000
    RUN_MS = 1300

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(96, 34)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self._t = -1.0
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(self.RUN_MS)
        self._anim.valueChanged.connect(self._on_value)
        self._anim.finished.connect(self._on_done)
        self._every = QTimer(self)
        self._every.setInterval(self.EVERY_MS)
        self._every.timeout.connect(self._play)
        self._every.start()
        self._font = QFont(theme.GLASS_FONT_FAMILY)
        self._font.setPixelSize(9)
        self._font.setBold(True)
        self._font.setLetterSpacing(QFont.AbsoluteSpacing, 1.2)

    def _play(self):
        if self.isVisible() and self.window().isVisible() and not self.window().isMinimized():
            self._anim.start()

    def _on_value(self, v):
        self._t = float(v)
        self.update()

    def _on_done(self):
        self._t = -1.0
        self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.LeftButton and self.rect().contains(ev.position().toPoint()):
            self.clicked.emit()

    def _chevron(self, p, cx, cy, alpha, width=7.0):
        if alpha <= 0:
            return
        pen = QPen(QColor(255, 255, 255, int(alpha)), 1.8)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        path = QPainterPath()
        path.moveTo(cx - width, cy + width * 0.55)
        path.lineTo(cx, cy - width * 0.45)
        path.lineTo(cx + width, cy + width * 0.55)
        p.drawPath(path)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        cx = self.width() / 2
        hover = self.underMouse()
        if hover:
            bg = QPainterPath()
            bg.addRoundedRect(QRectF(4, 0, self.width() - 8, self.height()), 12, 12)
            p.fillPath(bg, QColor(255, 255, 255, 22))
        if self._t < 0:
            # en reposo: una flechita tenue
            self._chevron(p, cx, 9, 120 if hover else 85)
        else:
            # dos flechitas que suben una detrás de otra y se desvanecen
            for k, delay in enumerate((0.0, 0.22)):
                u = (self._t - delay) / 0.78
                if 0 <= u <= 1:
                    y = 15 - 13 * u
                    alpha = 255 * math.sin(math.pi * u) * (0.95 if k == 0 else 0.7)
                    self._chevron(p, cx, y, alpha)
            # la de reposo se apaga mientras pasa la animación
            self._chevron(p, cx, 9, 85 * max(0.0, 1 - self._t * 4) if self._t < 0.25 else 85 * max(0.0, (self._t - 0.8) / 0.2))
        p.setFont(self._font)
        p.setPen(QColor(255, 255, 255, 170 if hover else 128))
        p.drawText(QRectF(0, 17, self.width(), 16), Qt.AlignHCenter | Qt.AlignVCenter, "PLAYLIST")
        p.end()


class _TrackRow(QWidget):
    clicked = Signal()
    remove_clicked = Signal()

    def __init__(self, title, artist, duration, pixmap=None, active=False, removable=True,
                 status="ready", flash=False, parent=None):
        """status: "ready" (lista), "pending" (aún no lista) o "loading"
        (preparándose: circulito girando). flash: borde verde de "¡lista!"."""
        super().__init__(parent)
        self.status = status
        self.setFixedHeight(46)
        self.setCursor(Qt.PointingHandCursor)
        self.active = active
        # Un QWidget "hecho a mano" no pinta su fondo de estilo si no se le
        # pide explícitamente -- sin esto el resaltado nunca se veía.
        self.setObjectName("trackrow")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_Hover, True)
        if active:
            style = f"QWidget#trackrow {{ background: {theme.GLASS_ACCENT_SOFT}; border-radius: 10px; }}"
        else:
            style = (
                "QWidget#trackrow { background: transparent; border-radius: 10px; }"
                "QWidget#trackrow:hover { background: rgba(255,255,255,0.07); }"
            )
        self.setStyleSheet(style)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 5, 8, 5)
        lay.setSpacing(10)

        self.thumb = QLabel()
        self.thumb.setFixedSize(34, 34)
        self.thumb.setAlignment(Qt.AlignCenter)
        self.thumb.setStyleSheet("background:transparent;")
        if status == "ready":
            self._set_thumb(pixmap, flash=flash)
        else:
            self.thumb.setPixmap(_pending_thumb(34, 34, 8))
        lay.addWidget(self.thumb)
        if status == "loading":
            # el circulito va encima de la miniatura punteada
            self.spinner = Spinner(20, parent=self.thumb)
            self.spinner.move(7, 7)
        else:
            self.spinner = None

        info = QVBoxLayout()
        info.setSpacing(1)
        title_lbl = _ElidedLabel(title)
        title_lbl.setStyleSheet(
            f"color:{theme.GLASS_ACCENT if active else theme.GLASS_TEXT}; "
            "font-size:12px; font-weight:600; background:transparent;"
        )
        if status == "pending":
            artist = "Aún no lista · tócala para prepararla"
        elif status == "loading":
            artist = "Preparando…"
        artist_lbl = _ElidedLabel(artist or "")
        artist_lbl.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE2}; font-size:10.5px; background:transparent;")
        if status != "ready":
            title_lbl.setStyleSheet(
                f"color:{theme.GLASS_TEXT_MUTE}; font-size:12px; font-weight:600; background:transparent;"
            )
        info.addWidget(title_lbl)
        info.addWidget(artist_lbl)
        lay.addLayout(info, 1)

        if active:
            self.eq = _Equalizer()
            self.eq.setActive(True)
            lay.addWidget(self.eq)
        else:
            self.eq = None
            dur_lbl = QLabel(fmt_time(duration) if duration else "")
            dur_lbl.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE2}; font-size:10px; background:transparent;")
            lay.addWidget(dur_lbl)

        if removable and not active:
            remove_btn = QPushButton("")
            remove_btn.setFixedSize(22, 22)
            remove_btn.setCursor(Qt.PointingHandCursor)
            remove_btn.setToolTip("Quitar de la cola")
            remove_btn.setIcon(icons.icon("remove", "#9E9BA8", 14))
            remove_btn.setIconSize(QSize(14, 14))
            remove_btn.setStyleSheet(
                "QPushButton { background:transparent; border:none; border-radius:11px; }"
                "QPushButton:hover { background: rgba(228,91,91,0.35); }"
            )
            remove_btn.clicked.connect(lambda: self.remove_clicked.emit())
            lay.addWidget(remove_btn)

    def _set_thumb(self, pixmap, flash=False):
        if pixmap and not pixmap.isNull():
            pm = _rounded(_cover_pixmap(pixmap, 34, 34), 8)
        else:
            pm = _gradient_label(34, 34, 8)
        self.thumb.setPixmap(_with_ready_border(pm, 8) if flash else pm)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(ev)


class _Tile(QWidget):
    """Un resultado del buscador. Al tocarlo: morado con circulito
    "Añadiendo…"; cuando el servidor confirma, se ilumina en verde y queda
    marcado "Añadido · #3 en la lista" (o "Sonando ahora")."""
    clicked = Signal()

    def __init__(self, title, artist, pixmap=None, size=150, parent=None):
        super().__init__(parent)
        self.setFixedWidth(size)
        self.setCursor(Qt.PointingHandCursor)
        self.state = "idle"   # idle | adding | added | failed
        self._size = size
        self._pixmap = pixmap

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(5)

        self.art = QLabel()
        self.art.setFixedSize(size, size)
        self.art.setStyleSheet("background:transparent;")
        lay.addWidget(self.art)

        t = _ElidedLabel(title)
        t.setStyleSheet(f"color:{theme.GLASS_TEXT}; font-size:11.5px; font-weight:700; background:transparent;")
        a = _ElidedLabel(artist or "")
        a.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE2}; font-size:10px; background:transparent;")
        lay.addWidget(t)
        lay.addWidget(a)

        # capa encima de la portada: "Añadiendo…" / "No se pudo añadir"
        self.overlay = QWidget(self.art)
        self.overlay.setGeometry(0, 0, size, size)
        self.overlay.setObjectName("tileov")
        self.overlay.setAttribute(Qt.WA_StyledBackground, True)
        self.overlay.setAttribute(Qt.WA_TransparentForMouseEvents)
        ol = QVBoxLayout(self.overlay)
        ol.setAlignment(Qt.AlignCenter)
        ol.setSpacing(8)
        self.ov_spinner = Spinner(26, color="#ffffff")
        srow = QHBoxLayout()
        srow.addStretch()
        srow.addWidget(self.ov_spinner)
        srow.addStretch()
        ol.addLayout(srow)
        self.ov_label = QLabel("")
        self.ov_label.setAlignment(Qt.AlignCenter)
        self.ov_label.setWordWrap(True)
        self.ov_label.setStyleSheet("color:white; font-size:12px; font-weight:800; background:transparent;")
        ol.addWidget(self.ov_label)
        self.overlay.hide()

        # destello verde de "¡añadido!" (se desvanece solo)
        self.glow = QWidget(self.art)
        self.glow.setGeometry(0, 0, size, size)
        self.glow.setObjectName("tileglow")
        self.glow.setAttribute(Qt.WA_StyledBackground, True)
        self.glow.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.glow.setStyleSheet("QWidget#tileglow { background: rgba(61,220,132,0.50); border-radius: 12px; }")
        self.glow.hide()

        # etiqueta verde fija: "Añadido · #3 en la lista"
        self.badge = QWidget(self.art)
        self.badge.setObjectName("tilebadge")
        self.badge.setAttribute(Qt.WA_StyledBackground, True)
        self.badge.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.badge.setStyleSheet("QWidget#tilebadge { background: rgba(31,170,95,0.95); border-radius: 11px; }")
        bl = QHBoxLayout(self.badge)
        bl.setContentsMargins(8, 0, 9, 0)
        bl.setSpacing(5)
        chk = QLabel()
        chk.setPixmap(icons.pixmap("check", "#ffffff", 12))
        chk.setStyleSheet("background:transparent;")
        bl.addWidget(chk)
        self.badge_label = QLabel("")
        self.badge_label.setStyleSheet("color:white; font-size:10px; font-weight:800; background:transparent;")
        bl.addWidget(self.badge_label)
        self.badge.hide()

        self._render_art()

    def _render_art(self):
        size = self._size
        if self._pixmap and not self._pixmap.isNull():
            pm = _rounded(_cover_pixmap(self._pixmap, size, size), 12)
        else:
            pm = _gradient_label(size, size, 12)
        if self.state == "adding":
            pm = _with_border(pm, 12, theme.GLASS_ACCENT)
        elif self.state == "added":
            pm = _with_border(pm, 12, "#3DDC84")
        self.art.setPixmap(pm)

    def _set_art(self, pixmap, size):
        self._pixmap = pixmap
        self._render_art()

    def set_adding(self):
        self.state = "adding"
        self.badge.hide()
        self.overlay.setStyleSheet("QWidget#tileov { background: rgba(142,108,242,0.62); border-radius: 12px; }")
        self.ov_label.setText("Añadiendo…")
        self.ov_spinner.show()
        self.overlay.show()
        self._render_art()

    def set_added(self, text):
        first_time = self.state != "added"
        self.state = "added"
        self.overlay.hide()
        self.badge_label.setText(text)
        self.badge.adjustSize()
        bw = min(self.badge.sizeHint().width(), self._size - 12)
        self.badge.setGeometry(6, self._size - 28, bw, 22)
        self.badge.show()
        self._render_art()
        if first_time:
            # se ilumina en verde y se va apagando hasta quedar solo el borde
            self.glow.show()
            eff = QGraphicsOpacityEffect(self.glow)
            self.glow.setGraphicsEffect(eff)
            anim = QPropertyAnimation(eff, b"opacity", self)
            anim.setDuration(1100)
            anim.setStartValue(1.0)
            anim.setEndValue(0.0)
            anim.setEasingCurve(QEasingCurve.InCubic)
            anim.finished.connect(self.glow.hide)
            self._glow_anim = anim
            anim.start()

    def set_failed(self):
        self.state = "failed"
        self.overlay.setStyleSheet("QWidget#tileov { background: rgba(228,91,91,0.70); border-radius: 12px; }")
        self.ov_spinner.hide()
        self.ov_label.setText("No se pudo añadir")
        self.overlay.show()
        self._render_art()
        QTimer.singleShot(2600, self._reset)

    def _reset(self):
        if self.state == "failed":
            self.state = "idle"
            self.overlay.hide()
            self._render_art()

    def mousePressEvent(self, ev):
        # mientras se añade (o si ya está añadido) no se vuelve a mandar
        if ev.button() == Qt.LeftButton and self.state == "idle":
            self.clicked.emit()
        super().mousePressEvent(ev)


class _GlassTextOverlay(QWidget):
    """Cuadro flotante para cuando hace falta escribir algo (un link, un
    nombre, pegar un código) o mostrar algo para copiar (el código de
    conexión) -- con la paleta "glass", para no romper el aspecto del
    reproductor nuevo. Mismo patrón que el TextOverlay original, solo que
    éste vive adentro de la propia GlassScreen (que ahora es la ventana de
    verdad, no una pantalla embebida), así que no hace falta una ventana
    aparte que lo contenga."""
    submitted = Signal(str, str)   # (contexto, texto)
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._context = ""
        self.setStyleSheet(f"""
            QWidget#backdrop {{ background: rgba(0,0,0,0.55); }}
            QWidget#card {{
                background: {theme.GLASS_PANEL_BG};
                border: 1px solid {theme.GLASS_BORDER};
                border-radius: 14px;
            }}
            QLabel {{ color: {theme.GLASS_TEXT}; font-size: 11px; background: transparent; }}
            QLineEdit {{
                background: rgba(255,255,255,0.08); border: 1px solid {theme.GLASS_BORDER};
                border-radius: 8px; padding: 7px 9px; font-size: 12px; color: {theme.GLASS_TEXT};
            }}
            QPushButton {{
                background: {theme.GLASS_ACCENT}; color: white; border: none;
                border-radius: 8px; padding: 7px 14px; font-weight: 600;
            }}
            QPushButton#cancel {{ background: transparent; color: {theme.GLASS_TEXT_MUTE}; }}
        """)
        self._backdrop = QWidget(self)
        self._backdrop.setObjectName("backdrop")
        self._backdrop.setGeometry(0, 0, W, H)

        card = QWidget(self)
        card.setObjectName("card")
        card.setFixedWidth(min(280, W - 32))
        self._card = card

        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 16, 18, 14)
        lay.setSpacing(10)
        self.label = QLabel("")
        self.label.setWordWrap(True)
        lay.addWidget(self.label)
        self.edit = QLineEdit()
        self.edit.returnPressed.connect(self._submit)
        lay.addWidget(self.edit)
        btns = QHBoxLayout()
        cancel = QPushButton("Cancelar")
        cancel.setObjectName("cancel")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self._cancel)
        ok = QPushButton("Listo")
        ok.setCursor(Qt.PointingHandCursor)
        ok.clicked.connect(self._submit)
        btns.addWidget(cancel)
        btns.addStretch()
        btns.addWidget(ok)
        lay.addLayout(btns)

        self.setGeometry(0, 0, W, H)
        self._center_card()
        self.hide()

    def _center_card(self):
        self._card.adjustSize()
        self._card.move((W - self._card.width()) // 2, (H - self._card.height()) // 2)

    def open(self, prompt, context, placeholder="", initial=""):
        self._context = context
        self.label.setText(prompt)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setText(initial)
        self._center_card()
        self.show()
        self.raise_()
        self.edit.setFocus()
        self.edit.selectAll()

    def _submit(self):
        text = self.edit.text()
        self.hide()
        self.submitted.emit(self._context, text)

    def _cancel(self):
        self.hide()
        self.cancelled.emit()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            self._cancel()
        else:
            super().keyPressEvent(ev)


# Barra de scroll fina y redondeada (solo el "palito"), sin las flechas ni
# el fondo gris de Windows.
SCROLL_STYLE = """
    QScrollArea { background: transparent; border: none; }
    QScrollBar:vertical { background: transparent; width: 8px; margin: 4px 1px 4px 1px; }
    QScrollBar::handle:vertical { background: rgba(255,255,255,0.26); border-radius: 3px; min-height: 30px; margin: 0 1px; }
    QScrollBar::handle:vertical:hover { background: rgba(255,255,255,0.45); }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; width: 0; border: none; background: none; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""


class _CardStack(QWidget):
    """Las portadas de una playlist como una baraja: la 1ª al frente, recta y
    con el nombre encima; la 2ª y 3ª detrás, inclinadas a cada lado y más
    oscuras. Al aparecer se abren en abanico con un rebotito."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(CARD_H + 26)
        self._pix = [None, None, None]
        self._title = ""
        self._subtitle = ""
        self._t = 1.0
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(620)
        self._anim.setEasingCurve(QEasingCurve.OutBack)
        self._anim.valueChanged.connect(self._on_anim)

    def _on_anim(self, v):
        self._t = float(v)
        self.update()

    def set_cards(self, pixmaps, title, subtitle):
        self._pix = list(pixmaps)[:3] + [None] * (3 - len(pixmaps[:3]))
        self._title = title or ""
        self._subtitle = subtitle or ""
        self.update()

    def set_card(self, i, pixmap):
        if 0 <= i < 3:
            self._pix[i] = pixmap
            self.update()

    def play_intro(self):
        self._anim.stop()
        self._t = 0.0
        self._anim.start()

    def _card_path(self):
        path = QPainterPath()
        path.addRoundedRect(QRectF(-CARD_W / 2, -CARD_H / 2, CARD_W, CARD_H), 16, 16)
        return path

    def _draw_card(self, p, pix, angle, dx, scale, darken, front=False):
        p.save()
        p.translate(self.width() / 2 + dx, self.height() / 2)
        p.rotate(angle)
        p.scale(scale, scale)
        path = self._card_path()
        # sombra suave debajo
        for k, a in ((6, 26), (3, 34)):
            sh = QPainterPath()
            sh.addRoundedRect(QRectF(-CARD_W / 2 - k / 2, -CARD_H / 2 + k, CARD_W + k, CARD_H + k / 2), 18, 18)
            p.fillPath(sh, QColor(0, 0, 0, a))
        p.setClipPath(path)
        p.fillPath(path, QColor("#1b1a22"))  # base sólida: nada se transparenta
        if pix is not None and not pix.isNull():
            art = _cover_pixmap(pix, CARD_W * 2, CARD_H * 2)  # el doble: se ve nítido
            p.drawPixmap(QRectF(-CARD_W / 2, -CARD_H / 2, CARD_W, CARD_H), art, QRectF(0, 0, art.width(), art.height()))
        else:
            g = QLinearGradient(-CARD_W / 2, -CARD_H / 2, CARD_W / 2, CARD_H / 2)
            g.setColorAt(0, QColor(theme.GLASS_GRAD_1))
            g.setColorAt(1, QColor(theme.GLASS_GRAD_2))
            p.fillPath(path, g)
        if darken:
            p.fillPath(path, QColor(10, 9, 14, darken))
        if front and (self._title or self._subtitle):
            shade = QLinearGradient(0, 0, 0, CARD_H / 2)
            shade.setColorAt(0, QColor(0, 0, 0, 0))
            shade.setColorAt(1, QColor(0, 0, 0, 190))
            p.fillRect(QRectF(-CARD_W / 2, 0, CARD_W, CARD_H / 2), shade)
            f = QFont(theme.GLASS_FONT_FAMILY)
            f.setPixelSize(12)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#ffffff"))
            fm = p.fontMetrics()
            title = fm.elidedText(self._title, Qt.ElideRight, CARD_W - 20)
            p.drawText(QRectF(-CARD_W / 2 + 10, CARD_H / 2 - 40, CARD_W - 20, 18), Qt.AlignLeft | Qt.AlignVCenter, title)
            f.setBold(False)
            f.setPixelSize(10)
            p.setFont(f)
            p.setPen(QColor(255, 255, 255, 185))
            p.drawText(QRectF(-CARD_W / 2 + 10, CARD_H / 2 - 23, CARD_W - 20, 14), Qt.AlignLeft | Qt.AlignVCenter, self._subtitle)
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 60 if front else 35), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.restore()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        t = self._t
        # detrás: la 3ª a la derecha y la 2ª a la izquierda, abriéndose en abanico
        self._draw_card(p, self._pix[2], 9 * t, 34 * t, 0.86, 120)
        self._draw_card(p, self._pix[1], -9 * t, -34 * t, 0.86, 120)
        front_scale = 0.9 + 0.1 * min(1.0, max(0.0, t))
        self._draw_card(p, self._pix[0], 0, 0, front_scale, 0, front=True)
        p.end()


def _bare_scroll(widget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidget(widget)
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.NoFrame)
    sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    sa.viewport().setAutoFillBackground(False)
    sa.viewport().setStyleSheet("background: transparent;")
    sa.setStyleSheet(SCROLL_STYLE)
    return sa


def _blur_pixmap(pix: QPixmap, w: int, h: int) -> QPixmap:
    """Desenfoque "gaussiano" barato: se encoge mucho la imagen y se vuelve
    a agrandar suavizando, en dos pasos. Se hace UNA vez por canción (no en
    cada cuadro), así que no le cuesta nada al equipo."""
    if pix is None or pix.isNull():
        return QPixmap()
    base = _cover_pixmap(pix, w, h)
    tiny = base.scaled(max(1, w // 18), max(1, h // 18), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    mid = tiny.scaled(max(1, w // 4), max(1, h // 4), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    out = mid.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    out.setDevicePixelRatio(1.0)
    return out


class _GlassPanel(QWidget):
    """Panel de vidrio esmerilado: dibuja detrás la portada DESENFOCADA (en
    la misma posición que ocupa en la ventana, como un vidrio de verdad) y
    encima un velo oscuro para que todo se lea. Con el switch de glass
    apagado, es un fondo sólido."""

    def __init__(self, screen, top_radius=0, tint_alpha=150, parent=None):
        super().__init__(parent or screen)
        self._screen = screen
        self._radius = top_radius
        self._tint_alpha = tint_alpha
        self.setAttribute(Qt.WA_StyledBackground, False)

    def moveEvent(self, ev):
        self.update()  # al deslizarse, el "vidrio" se redibuja alineado
        super().moveEvent(ev)

    def _shape(self):
        r = self._radius
        w, h = self.width(), self.height()
        path = QPainterPath()
        if r <= 0:
            path.addRect(QRectF(0, 0, w, h))
            return path
        path.moveTo(0, h)
        path.lineTo(0, r)
        path.quadTo(0, 0, r, 0)
        path.lineTo(w - r, 0)
        path.quadTo(w, 0, w, r)
        path.lineTo(w, h)
        path.closeSubpath()
        return path

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        path = self._shape()
        p.setClipPath(path)
        blur = getattr(self._screen, "_blur_pix", None)
        if getattr(self._screen, "_glass_on", True) and blur is not None and not blur.isNull():
            p.drawPixmap(QRectF(0, 0, self.width(), self.height()), blur,
                         QRectF(self.x(), self.y(), self.width(), self.height()))
            p.fillPath(path, QColor(14, 13, 20, self._tint_alpha))
            # un filo de luz arriba, como el borde de un vidrio
            p.setClipping(False)
            p.setPen(QPen(QColor(255, 255, 255, 46), 1))
            p.drawPath(path)
        else:
            p.fillPath(path, QColor(theme.FLAT_PANEL_BG))
        p.end()


# ======================================================================
# GlassScreen
# ======================================================================

class GlassScreen(QWidget):
    update_requested = Signal()   # tocaron "Actualizar" en el aviso

    def __init__(self, title="Cumito", parent=None):
        super().__init__(parent)
        # Todo el estado interno va PRIMERO, antes de tocar nada de Qt:
        # Qt puede disparar eventos (changeEvent, eventFilter, ...) en
        # cualquier momento mientras se arma la ventana, y esos métodos
        # leen estas variables. Si todavía no existen, la app se cae.
        self.state = {
            "now_playing": None, "queue": [], "host_label": "",
            "connected": True, "members": [], "volume": 0.6,
        }
        self._glass_on = True
        self._sheet_open = False
        self._searching = False
        self._panel_mode = None  # None | "search" | "settings"
        self._local_elapsed = 0.0
        self._drag_pos = None
        self._chrome_widgets = []  # todo lo que cambia con el switch de glass
        self._filters_ready = False
        self._empty_mode = None          # True = "¿Qué escucharemos hoy?"
        self._anims = {}                 # animaciones de aparecer/desaparecer en curso
        self._recent_sig = None          # para no rehacer la lista si no cambió
        self._showing_placeholder = None
        self._blur_pix = None            # portada desenfocada para el vidrio
        self._req_tiles = {}             # código de "añadir" -> resultado del buscador
        self._seen_unready = set()       # canciones de la cola que vimos sin preparar
        self._flash_until = {}           # uid -> hasta cuándo va el borde verde
        self._sheet_sig = None           # para no rehacer la lista si no cambió
        self._last_act = None            # (id, texto) de la última actividad vista
        self._activity_loaded = False
        self._pan_range = 0              # cuánto se puede pasear el fondo (px)
        self._pan_t0 = time.monotonic()
        self._idle = False               # modo "solo portada"
        self._last_poke = time.monotonic()
        self._last_cursor = None
        self._last_option = "activity"   # la rueda de opciones abre donde quedó
        # opciones visuales (main.py las guarda): modo streamer, forma del mini, fondo para OBS
        self.visual = {"streamer": False, "mini_shape": "cuadrado", "chroma": "", "mini_dim": 0.15,
                       "mini_dim_set": False, "glass": True}
        self.ui_scale = 1.0              # tamaño de toda la ventana (main.py lo aplica al abrir)
        self.mini = None                 # la ventanita del modo mini (si se abrió)
        self._now_art = None
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._on_tick)
        self._pan_timer = QTimer(self)
        self._pan_timer.timeout.connect(self._on_pan)

        self.setWindowTitle(title)
        # WindowMinimizeButtonHint: aunque la ventana no tiene marco, así
        # Windows deja minimizarla y restaurarla desde la barra de tareas.
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window | Qt.WindowMinimizeButtonHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(W, H)

        self.art_cache = ArtCache(self)
        self.art_cache.loaded.connect(self._on_art_loaded)

        self._build_ui()
        self._apply_window_mask()
        self._apply_glass(True)
        self._refresh_now()
        self._refresh_sheet_list()
        self._refresh_recent(force=True)
        self._update_mode(animate=False)

        # Recién ahora que existe TODA la ventana se conectan los
        # "vigilantes" de eventos (arrastrar desde zonas vacías, abrir/
        # cerrar la bandeja con la manija o con la rueda del mouse).
        self.titlebar.installEventFilter(self)
        self.now_overlay.installEventFilter(self)
        self.empty_view.installEventFilter(self)
        self.sheet_handle.installEventFilter(self)
        self.sheet_scroll.viewport().installEventFilter(self)
        self._filters_ready = True

        self._timer.start(TICK_MS)
        self._pan_timer.start(PAN_TICK_MS)

    # ---------- lo que CumitoWindow (main.py) sobreescribe ----------
    def on_visual_changed(self, visual):
        """main.py lo sobreescribe para guardar las opciones visuales."""
        pass

    def on_scale_changed(self, scale):
        """main.py lo sobreescribe: guarda el tamaño y reinicia Cumito."""
        pass

    def set_visual(self, visual):
        self.visual.update({k: v for k, v in (visual or {}).items() if k in self.visual})
        if not self.visual.get("mini_dim_set"):
            self.visual["mini_dim"] = 0.15   # el valor de fábrica nuevo (antes era 30%)
        if bool(self.visual.get("glass", True)) != self._glass_on:
            self._apply_glass(bool(self.visual.get("glass", True)))
        self._set_pills_visible(not self._empty_mode and not self._panel_mode)
        if self.mini is not None:
            self.mini.set_shape(self.visual["mini_shape"])
            self.mini.set_chroma(self.visual["chroma"])
            self.mini.set_dim(self.visual["mini_dim"])

    def request_activity(self):
        """main.py lo sobreescribe: pide al servidor el registro completo."""
        pass

    def settings_rows(self):
        return []

    def on_settings_row(self, label):
        pass

    def send_command(self, action, **kw):
        pass

    def do_search(self, query, limit=8, offset=0, kind="music"):
        pass

    def on_recent_searches_changed(self, searches):
        """main.py lo sobreescribe para guardar las búsquedas recientes."""
        pass

    # ---------- cuadro de texto flotante ----------
    def ask_text(self, prompt, context, placeholder="", initial=""):
        """on_settings_row(...) la llama cuando hace falta que la persona
        escriba algo (o vea algo para copiar). El resultado llega por
        self.text_overlay.submitted (contexto, texto) -- main.py es quien
        se conecta a esa señal, porque es quien sabe qué hacer con cada
        contexto (guardar config, reconectar, etc.)."""
        self.text_overlay.open(prompt, context, placeholder=placeholder, initial=initial)

    # ================= construcción =================
    def _apply_window_mask(self):
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, W, H), theme.GLASS_WINDOW_RADIUS, theme.GLASS_WINDOW_RADIUS)
        region = path.toFillPolygon().toPolygon()
        from PySide6.QtGui import QRegion
        self.setMask(QRegion(region))

    def _build_ui(self):
        # ---- capa 0: portada ----
        self.art_bg = QLabel(self)
        self.art_bg.setGeometry(0, 0, W, H)
        self.art_bg.setPixmap(_placeholder_art(W, H))
        self.art_bg.setScaledContents(False)
        # deja pasar el clic hacia la ventana (así se puede arrastrar
        # agarrando de la portada, que ocupa toda la ventana)
        self.art_bg.setAttribute(Qt.WA_TransparentForMouseEvents)

        # ---- scrims ----
        self.scrim_top = QLabel(self)
        self.scrim_top.setGeometry(0, 0, W, 130)
        self.scrim_top.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._paint_scrim(self.scrim_top, top=True)

        self.scrim_bottom = QLabel(self)
        bh = int(H * 0.62)
        self.scrim_bottom.setGeometry(0, H - bh, W, bh)
        self.scrim_bottom.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._paint_scrim(self.scrim_bottom, top=False)

        # ---- barra de título ----
        self.titlebar = QWidget(self)
        self.titlebar.setGeometry(0, 0, W, 92)
        tlay = QVBoxLayout(self.titlebar)
        tlay.setContentsMargins(14, 14, 14, 0)
        tlay.setSpacing(10)

        row = QHBoxLayout()
        row.setSpacing(6)
        left = QHBoxLayout()
        left.setSpacing(8)
        dot = QLabel()
        dot.setFixedSize(9, 9)
        dot.setStyleSheet(f"background:{theme.GLASS_ACCENT}; border-radius:4px;")
        name = QLabel(self.windowTitle())
        name.setStyleSheet(f"color:#fff; font-size:13px; font-weight:700; background:transparent;")
        left.addWidget(dot)
        # "Cumito" y, encima, el aviso de la última actividad (ocupan el mismo lugar)
        title_area = QWidget()
        title_area.setStyleSheet("background:transparent;")
        title_area.setFixedHeight(22)
        title_area.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        tgrid = QGridLayout(title_area)
        tgrid.setContentsMargins(0, 0, 4, 0)
        tgrid.addWidget(name, 0, 0, Qt.AlignLeft | Qt.AlignVCenter)
        self.ticker = Ticker(name)
        tgrid.addWidget(self.ticker, 0, 0)
        left.addWidget(title_area, 1)
        row.addLayout(left, 1)

        # todo lo demás (apagar, vidrio, servidor, nombre, actividad...)
        # vive en la rueda de Opciones
        self.btn_options = _IconButton("menu")
        self.btn_options.setToolTip("Opciones")
        self.btn_options.clicked.connect(self._open_settings)
        row.addWidget(self.btn_options)

        self.btn_minimize = _IconButton("minimize")
        self.btn_minimize.setToolTip("Minimizar")
        self.btn_minimize.clicked.connect(self.showMinimized)
        row.addWidget(self.btn_minimize)

        self.btn_close = _IconButton("close", danger=True)
        self.btn_close.clicked.connect(self.close)
        row.addWidget(self.btn_close)

        tlay.addLayout(row)

        self.search_pill = _Pill("  Buscar", icon_name="search")
        self.search_pill.clicked.connect(self._open_search)
        # modo streamer: al lado de Buscar, el botón para pasar al mini
        self.mini_pill = _Pill("  Mini", icon_name="mini")
        self.mini_pill.clicked.connect(self.enter_mini)
        self.mini_pill.hide()
        pill_row = QHBoxLayout()
        pill_row.setSpacing(8)
        pill_row.addWidget(self.search_pill)
        pill_row.addWidget(self.mini_pill)
        pill_row.addStretch()
        tlay.addLayout(pill_row)

        self._chrome_widgets += [self.btn_options, self.btn_minimize, self.btn_close, self.search_pill, self.mini_pill]

        # ---- overlay inferior: ahora sonando ----
        self.now_overlay = QWidget(self)
        self.now_overlay.setGeometry(0, H - 216, W, 210)
        nlay = QVBoxLayout(self.now_overlay)
        nlay.setContentsMargins(20, 0, 20, 6)
        nlay.setSpacing(10)
        nlay.addStretch()

        self.swipe_hint = _SwipeHint()
        self.swipe_hint.clicked.connect(self._open_sheet)
        hint_box = QHBoxLayout()
        hint_box.addStretch()
        hint_box.addWidget(self.swipe_hint)
        hint_box.addStretch()
        nlay.addLayout(hint_box)

        mini_row = QHBoxLayout()
        mini_row.setSpacing(11)
        self.mini_thumb = QLabel()
        self.mini_thumb.setFixedSize(42, 42)
        mini_row.addWidget(self.mini_thumb)
        mini_info = QVBoxLayout()
        mini_info.setSpacing(0)
        self.now_title = _ElidedLabel("Nada sonando")
        self.now_title.setStyleSheet("color:#fff; font-size:16px; font-weight:800; background:transparent;")
        self.now_artist = _ElidedLabel("Agrega algo con el buscador")
        self.now_artist.setStyleSheet("color: rgba(255,255,255,0.62); font-size:12.5px; background:transparent;")
        mini_info.addWidget(self.now_title)
        mini_info.addWidget(self.now_artist)
        mini_row.addLayout(mini_info, 1)
        nlay.addLayout(mini_row)

        prog_row = QHBoxLayout()
        prog_row.setSpacing(8)
        self.time_elapsed = QLabel("0:00")
        self.time_elapsed.setStyleSheet("color: rgba(255,255,255,0.55); font-size:10px; background:transparent;")
        self.progress = _ProgressBar()
        self.time_total = QLabel("0:00")
        self.time_total.setStyleSheet("color: rgba(255,255,255,0.55); font-size:10px; background:transparent;")
        prog_row.addWidget(self.time_elapsed)
        prog_row.addWidget(self.progress, 1)
        prog_row.addWidget(self.time_total)
        nlay.addLayout(prog_row)

        transport = QHBoxLayout()
        transport.setSpacing(30)
        transport.addStretch()
        self.btn_prev = _IconButton("prev", size=36, icon_size=20, icon_color="#FFFFFF")
        self.btn_prev.setEnabled(False)
        self.btn_prev.setToolTip("Sin historial hacia atrás por ahora")
        transport.addWidget(self.btn_prev)
        self.btn_play = _IconButton("play", size=48, icon_size=20, icon_color="#FFFFFF")
        self.btn_play.clicked.connect(self._on_play_pause)
        transport.addWidget(self.btn_play)
        self.btn_next = _IconButton("next", size=36, icon_size=20, icon_color="#FFFFFF")
        self.btn_next.clicked.connect(lambda: self.send_command("skip"))
        transport.addWidget(self.btn_next)
        transport.addStretch()
        nlay.addLayout(transport)

        # atrás / siguiente: solo el ícono, sin círculo. Play/pausa: un
        # círculo de vidrio ("liquid"): medio transparente, con borde y un
        # brillo arriba, nada de blanco sólido.
        for b in (self.btn_prev, self.btn_next):
            b.setStyleSheet(
                "QPushButton { background: transparent; border:none; border-radius: 18px; }"
                "QPushButton:hover { background: rgba(255,255,255,0.10); }"
                "QPushButton:pressed { background: rgba(255,255,255,0.05); }"
            )
        self.btn_play.setStyleSheet(
            "QPushButton { border-radius: 24px;"
            " background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255,255,255,0.30),"
            " stop:0.55 rgba(255,255,255,0.13), stop:1 rgba(255,255,255,0.20));"
            " border: 1px solid rgba(255,255,255,0.42); border-top: 1px solid rgba(255,255,255,0.80); }"
            "QPushButton:hover { background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(255,255,255,0.40),"
            " stop:0.55 rgba(255,255,255,0.20), stop:1 rgba(255,255,255,0.27)); }"
            "QPushButton:pressed { background: rgba(255,255,255,0.12); }"
        )

        # ---- modo "solo portada" (después de IDLE_S sin tocar nada) ----
        # Solo queda la portada y, abajo, el nombre y el artista sobre un
        # degradado más bajito. Al mover el mouse vuelve todo.
        self.scrim_names = QLabel(self)
        self.scrim_names.setGeometry(0, H - 150, W, 150)
        self.scrim_names.setAttribute(Qt.WA_TransparentForMouseEvents)
        spix = QPixmap(W, 150)
        spix.fill(Qt.transparent)
        sp = QPainter(spix)
        sg = QLinearGradient(0, 0, 0, 150)
        sg.setColorAt(0.0, QColor(8, 8, 11, 0))
        sg.setColorAt(0.55, QColor(8, 8, 11, 120))
        sg.setColorAt(1.0, QColor(8, 8, 11, 200))
        sp.fillRect(spix.rect(), sg)
        sp.end()
        self.scrim_names.setPixmap(spix)
        self.scrim_names.hide()
        self.idle_caption = QWidget(self)
        self.idle_caption.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.idle_caption.setGeometry(22, H - 70, W - 44, 50)
        cap = QVBoxLayout(self.idle_caption)
        cap.setContentsMargins(0, 0, 0, 0)
        cap.setSpacing(1)
        self.idle_title = _ElidedLabel("")
        self.idle_title.setStyleSheet("color:#fff; font-size:17px; font-weight:800; background:transparent;")
        self.idle_artist = _ElidedLabel("")
        self.idle_artist.setStyleSheet("color: rgba(255,255,255,0.68); font-size:12.5px; background:transparent;")
        cap.addWidget(self.idle_title)
        cap.addWidget(self.idle_artist)
        self.idle_caption.hide()
        self._idle_fx = {}   # widget -> efecto de opacidad (solo durante el modo)

        # ---- estado vacío: "¿Qué escucharemos hoy?" ----
        # Se ve cuando no suena nada: Cumito feliz, lo último que sonó en
        # el servidor (clic = ponerla otra vez) y una barra de búsqueda.
        self.empty_view = QWidget(self)
        self.empty_view.setGeometry(0, 52, W, H - 52)
        elay = QVBoxLayout(self.empty_view)
        elay.setContentsMargins(22, 6, 22, 20)
        elay.setSpacing(0)

        self.empty_mascot = QLabel()
        # la imagen completa (es vertical), sin máscara ni recorte
        self.empty_mascot.setFixedSize(122, 160)
        self.empty_mascot.setAlignment(Qt.AlignCenter)
        self.empty_mascot.setStyleSheet("background:transparent;")
        mascot = icons.artwork("cumito_feliz", 122, 160)
        if mascot is not None:
            self.empty_mascot.setPixmap(mascot)
        mascot_row = QHBoxLayout()
        mascot_row.addStretch()
        mascot_row.addWidget(self.empty_mascot)
        mascot_row.addStretch()
        elay.addLayout(mascot_row)
        elay.addSpacing(8)

        self.empty_title = QLabel("¿Qué escucharemos hoy?")
        self.empty_title.setAlignment(Qt.AlignCenter)
        self.empty_title.setStyleSheet("color:#fff; font-size:19px; font-weight:800; background:transparent;")
        elay.addWidget(self.empty_title)
        self.empty_subtitle = QLabel("")
        self.empty_subtitle.setAlignment(Qt.AlignCenter)
        self.empty_subtitle.setWordWrap(True)
        self.empty_subtitle.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE}; font-size:11.5px; background:transparent;")
        elay.addWidget(self.empty_subtitle)
        elay.addSpacing(16)

        self.recent_header = QLabel("LO ÚLTIMO QUE SONÓ")
        self.recent_header.setStyleSheet(
            f"color:{theme.GLASS_TEXT_MUTE}; font-size:10px; font-weight:700; letter-spacing:1px; background:transparent;"
        )
        elay.addWidget(self.recent_header)
        elay.addSpacing(6)

        self.recent_list_widget = QWidget()
        self.recent_list_layout = QVBoxLayout(self.recent_list_widget)
        self.recent_list_layout.setContentsMargins(0, 0, 0, 0)
        self.recent_list_layout.setSpacing(2)
        self.recent_list_layout.addStretch()
        self.recent_scroll = _bare_scroll(self.recent_list_widget)
        elay.addWidget(self.recent_scroll, 1)

        self.recent_empty_label = QLabel("Todavía no ha sonado nada.\n¡Pon la primera!")
        self.recent_empty_label.setAlignment(Qt.AlignCenter)
        self.recent_empty_label.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE2}; font-size:11.5px; background:transparent;")
        elay.addWidget(self.recent_empty_label, 1)
        elay.addSpacing(12)

        self.empty_search = QPushButton("   Buscar canción o pegar link…")
        self.empty_search.setCursor(Qt.PointingHandCursor)
        self.empty_search.setFixedHeight(44)
        self.empty_search.setIcon(icons.icon("search", "#BDBAC6", 16))
        self.empty_search.setIconSize(QSize(16, 16))
        self.empty_search.setStyleSheet(
            f"QPushButton {{ text-align:left; padding-left:16px; background: rgba(255,255,255,0.10);"
            f" border:1px solid {theme.GLASS_BORDER}; border-radius:22px; color:#BDBAC6; font-size:12.5px; }}"
            "QPushButton:hover { background: rgba(255,255,255,0.16); }"
        )
        self.empty_search.clicked.connect(self._open_search)
        elay.addWidget(self.empty_search)

        # ---- bandeja de playlist ----
        self.playlist_sheet = _GlassPanel(self, top_radius=20)
        self.playlist_sheet.setGeometry(0, H, W, SHEET_H)
        slay = QVBoxLayout(self.playlist_sheet)
        slay.setContentsMargins(14, 8, 14, 10)
        slay.setSpacing(4)

        self.sheet_handle = QLabel()
        self.sheet_handle.setFixedSize(36, 4)
        self.sheet_handle.setStyleSheet("background: rgba(255,255,255,0.3); border-radius: 2px;")
        handle_row = QHBoxLayout()
        handle_row.addStretch()
        handle_row.addWidget(self.sheet_handle)
        handle_row.addStretch()
        slay.addLayout(handle_row)
        slay.addSpacing(6)

        sheet_head = QHBoxLayout()
        head_lbl = QLabel("PLAYLIST")
        head_lbl.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE}; font-size:11px; font-weight:700; letter-spacing:1px; background:transparent;")
        sheet_head.addWidget(head_lbl)
        sheet_head.addStretch()
        self.btn_clear_queue = QPushButton(" Borrar lista")
        self.btn_clear_queue.setFixedHeight(28)
        self.btn_clear_queue.setCursor(Qt.PointingHandCursor)
        self.btn_clear_queue.setToolTip("Quita todas las canciones de la lista (lo que suena sigue sonando)")
        self.btn_clear_queue.setIcon(icons.icon("trash", "#E9A0A0", 14))
        self.btn_clear_queue.setIconSize(QSize(14, 14))
        self.btn_clear_queue.setStyleSheet(
            "QPushButton { background: rgba(228,91,91,0.14); border:1px solid rgba(228,91,91,0.30);"
            " border-radius:14px; color:#F1B3B3; font-size:11px; font-weight:700; padding:0 12px 0 9px; }"
            "QPushButton:hover { background: rgba(228,91,91,0.30); color:#fff; }"
            "QPushButton:disabled { background: rgba(255,255,255,0.05); border:1px solid rgba(255,255,255,0.08);"
            " color: rgba(255,255,255,0.3); }"
        )
        self.btn_clear_queue.clicked.connect(self._ask_clear_queue)
        sheet_head.addWidget(self.btn_clear_queue)
        slay.addLayout(sheet_head)

        self.sheet_list_widget = QWidget()
        self.sheet_list_layout = QVBoxLayout(self.sheet_list_widget)
        self.sheet_list_layout.setContentsMargins(0, 0, 0, 0)
        self.sheet_list_layout.setSpacing(2)
        self.sheet_list_layout.addStretch()
        self.sheet_scroll = _bare_scroll(self.sheet_list_widget)
        slay.addWidget(self.sheet_scroll, 1)

        self._sheet_anim = QPropertyAnimation(self.playlist_sheet, b"pos")
        self._sheet_anim.setDuration(320)
        self._sheet_anim.setEasingCurve(QEasingCurve.OutCubic)

        # ---- buscador: hoja de vidrio que sube desde abajo ----
        # (deja visible la fila de arriba: cerrar, minimizar, etc.)
        self.search_view = _GlassPanel(self, top_radius=22, tint_alpha=165)
        self.search_view.setGeometry(0, PANEL_TOP, W, H - PANEL_TOP)
        self.search_view.hide()
        qlay = QVBoxLayout(self.search_view)
        qlay.setContentsMargins(14, 8, 14, 0)
        qlay.setSpacing(10)
        qlay.addLayout(self._handle_row())

        shead = QHBoxLayout()
        shead.setSpacing(8)
        self.btn_back = _IconButton("back", size=30)
        self.btn_back.clicked.connect(self._close_search)
        shead.addWidget(self.btn_back)
        self._chrome_widgets.append(self.btn_back)
        # la barra "líquida": vidrio con brillo arriba y borde de luz; al
        # abrir el buscador se estira con un pequeño rebote
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Canción, artista o link de playlist")
        self.search_input.setFixedHeight(38)
        self.search_input.addAction(icons.icon("search", "#CFCBD8", 16), QLineEdit.LeadingPosition)
        self.search_input.setStyleSheet(
            "QLineEdit { background: qlineargradient(x1:0, y1:0, x2:0, y2:1,"
            " stop:0 rgba(255,255,255,0.22), stop:0.55 rgba(255,255,255,0.10), stop:1 rgba(255,255,255,0.06));"
            " border: 1px solid rgba(255,255,255,0.32); border-radius: 19px; padding: 0 12px 0 4px;"
            f" color: {theme.GLASS_TEXT}; font-size: 12.5px; }}"
            "QLineEdit:focus { border: 1px solid rgba(142,108,242,0.95); }"
        )
        self.search_input.returnPressed.connect(self._submit_search)
        self.search_input.textChanged.connect(self._on_search_text_changed)
        shead.addWidget(self.search_input, 1)
        qlay.addLayout(shead)

        # pestañas: "Música" (como YouTube Music: versiones de audio oficiales)
        # y "Todo" (YouTube normal: videos, en vivo, covers...)
        self._search_kind = "music"
        tabs = QHBoxLayout()
        tabs.setSpacing(8)
        tabs.setContentsMargins(2, 2, 0, 2)
        self.search_tabs = {}
        for kind, text in (("music", "Música"), ("all", "Todo")):
            b = QPushButton(text)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(30)
            b.clicked.connect(lambda _=False, k=kind: self._set_search_kind(k))
            self.search_tabs[kind] = b
            tabs.addWidget(b)
        tabs.addStretch()
        qlay.addLayout(tabs)
        self._style_search_tabs()

        # 1) antes de buscar: búsquedas recientes + lo último que sonó
        self.search_home_widget = QWidget()
        self.search_home_layout = QVBoxLayout(self.search_home_widget)
        self.search_home_layout.setContentsMargins(0, 4, 0, 70)
        self.search_home_layout.setSpacing(4)
        self.search_home = _bare_scroll(self.search_home_widget)
        qlay.addWidget(self.search_home, 1)

        # 2) buscando: Cumito saltando
        self.search_loader = QWidget()
        llay = QVBoxLayout(self.search_loader)
        llay.setContentsMargins(0, 0, 0, 70)
        llay.addStretch()
        self.hop = HopLoader()
        hop_row = QHBoxLayout()
        hop_row.addStretch()
        hop_row.addWidget(self.hop)
        hop_row.addStretch()
        llay.addLayout(hop_row)
        self.loader_label = QLabel("Buscando…")
        self.loader_label.setAlignment(Qt.AlignCenter)
        self.loader_label.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE}; font-size:13px; font-weight:700; background:transparent;")
        llay.addWidget(self.loader_label)
        llay.addStretch()
        qlay.addWidget(self.search_loader, 1)
        self.search_loader.hide()

        # 3) resultados: mosaico + "Buscar más"
        self.mosaic_widget = QWidget()
        rlay = QVBoxLayout(self.mosaic_widget)
        rlay.setContentsMargins(0, 4, 0, 70)
        rlay.setSpacing(14)
        self.mosaic_grid = QGridLayout()
        self.mosaic_grid.setContentsMargins(0, 0, 0, 0)
        self.mosaic_grid.setHorizontalSpacing(12)
        self.mosaic_grid.setVerticalSpacing(14)
        rlay.addLayout(self.mosaic_grid)
        self.no_results_lbl = QLabel("No encontré nada con eso.\nPrueba escribiéndolo de otra forma.")
        self.no_results_lbl.setAlignment(Qt.AlignCenter)
        self.no_results_lbl.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE}; font-size:12px; background:transparent;")
        self.no_results_lbl.hide()
        rlay.addWidget(self.no_results_lbl)
        more_row = QHBoxLayout()
        more_row.addStretch()
        self.more_btn = QPushButton("Buscar más")
        self.more_btn.setCursor(Qt.PointingHandCursor)
        self.more_btn.setFixedHeight(36)
        self.more_btn.setMinimumWidth(150)
        self.more_btn.setStyleSheet(
            f"QPushButton {{ background: rgba(255,255,255,0.10); border:1px solid {theme.GLASS_BORDER};"
            f" border-radius:18px; color:{theme.GLASS_TEXT}; font-size:12px; font-weight:700; padding: 0 18px; }}"
            "QPushButton:hover { background: rgba(255,255,255,0.18); }"
            "QPushButton:disabled { color: rgba(242,240,247,0.5); }"
        )
        self.more_btn.clicked.connect(self._search_more)
        more_row.addWidget(self.more_btn)
        self.more_spinner = Spinner(18)
        self.more_spinner.hide()
        more_row.addWidget(self.more_spinner)
        more_row.addStretch()
        rlay.addLayout(more_row)
        rlay.addStretch()
        self.results_scroll = _bare_scroll(self.mosaic_widget)
        qlay.addWidget(self.results_scroll, 1)
        self.results_scroll.hide()

        # 4) vista previa de una playlist: "¿Quieres poner esta playlist?"
        self.preview_box = QWidget()
        pvl = QVBoxLayout(self.preview_box)
        pvl.setContentsMargins(0, 2, 0, 8)   # aquí el mini-reproductor se esconde: hace falta el espacio
        pvl.setSpacing(8)
        self.preview_question = QLabel("¿Quieres poner esta playlist?")
        self.preview_question.setStyleSheet("color:#fff; font-size:16px; font-weight:800; background:transparent;")
        pvl.addWidget(self.preview_question)
        self.preview_name = QLabel("")
        self.preview_name.setWordWrap(True)
        self.preview_name.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE}; font-size:11.5px; background:transparent;")
        pvl.addWidget(self.preview_name)
        self.preview_stack = _CardStack()
        pvl.addWidget(self.preview_stack)
        self.preview_list_widget = QWidget()
        self.preview_list_layout = QVBoxLayout(self.preview_list_widget)
        self.preview_list_layout.setContentsMargins(2, 4, 2, 4)
        self.preview_list_layout.setSpacing(3)
        self.preview_scroll = _bare_scroll(self.preview_list_widget)
        pvl.addWidget(self.preview_scroll, 1)

        def _pbtn(text, primary=False):
            b = QPushButton(text)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedHeight(38)
            if primary:
                b.setStyleSheet(
                    f"QPushButton {{ background:{theme.GLASS_ACCENT}; color:white; border:none; border-radius:19px;"
                    " font-size:12.5px; font-weight:800; }"
                    "QPushButton:hover { background:#9C7EF5; }"
                )
            else:
                b.setStyleSheet(
                    f"QPushButton {{ background: rgba(255,255,255,0.09); border:1px solid {theme.GLASS_BORDER};"
                    f" border-radius:19px; color:{theme.GLASS_TEXT}; font-size:12px; font-weight:700; }}"
                    "QPushButton:hover { background: rgba(255,255,255,0.16); }"
                )
            return b

        self.preview_add = _pbtn("Añadir", primary=True)
        self.preview_add.clicked.connect(self._preview_accept)
        pvl.addWidget(self.preview_add)
        prow = QHBoxLayout()
        prow.setSpacing(8)
        self.preview_single = _pbtn("Solo esta canción")
        self.preview_single.clicked.connect(self._preview_single_song)
        prow.addWidget(self.preview_single)
        # "No gracias" descarta la playlist: también se mantiene presionado
        self.preview_no = HoldButton("No gracias", height=38, font_size=12, strong=False)
        self.preview_no.confirmed.connect(self._preview_cancel)
        prow.addWidget(self.preview_no)
        pvl.addLayout(prow)
        qlay.addWidget(self.preview_box, 1)
        self.preview_box.hide()
        self._preview = None
        self._tiles = []
        self.recent_searches = []      # lo que buscaste último (lo guarda main.py)
        self._search_query = None
        self._search_count = 0

        # ---- ajustes: también una hoja que sube desde abajo ----
        self.settings_view = _GlassPanel(self, top_radius=22, tint_alpha=165)
        self.settings_view.setGeometry(0, PANEL_TOP, W, H - PANEL_TOP)
        self.settings_view.hide()
        stlay = QVBoxLayout(self.settings_view)
        stlay.setContentsMargins(14, 8, 14, 16)
        stlay.setSpacing(8)
        stlay.addLayout(self._handle_row())
        sthead = QHBoxLayout()
        sthead.setSpacing(10)
        self.btn_settings_back = _IconButton("back", size=30)
        self.btn_settings_back.clicked.connect(self._options_back)
        self._chrome_widgets.append(self.btn_settings_back)
        sthead.addWidget(self.btn_settings_back)
        sthead.addStretch()
        stlay.addLayout(sthead)
        st_title = self.options_title = QLabel("Opciones")
        st_title.setStyleSheet("color:#fff; font-size:30px; font-weight:800; background:transparent;"
                               " padding-left:6px;")
        stlay.addWidget(st_title)
        st_sub = self.options_sub = QLabel("Gira la rueda del mouse\ny toca la que quieras")
        st_sub.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE2}; font-size:11px; background:transparent;"
                             " padding-left:7px;")
        stlay.addWidget(st_sub)
        self.option_wheel = OptionWheel()
        self.option_wheel.activated.connect(self._on_option)
        stlay.addWidget(self.option_wheel, 1)
        self.dim_editor = DimEditor()
        self.dim_editor.changed.connect(self._on_dim_changed)
        self.dim_editor.hide()
        stlay.addWidget(self.dim_editor, 1)
        self._dim_save = QTimer(self)
        self._dim_save.setSingleShot(True)
        self._dim_save.setInterval(400)
        self._dim_save.timeout.connect(lambda: self.on_visual_changed(dict(self.visual)))

        # ---- actividad: otra hoja, estilo chat ----
        self.activity_view = _GlassPanel(self, top_radius=22, tint_alpha=170)
        self.activity_view.setGeometry(0, PANEL_TOP, W, H - PANEL_TOP)
        self.activity_view.hide()
        alay = QVBoxLayout(self.activity_view)
        alay.setContentsMargins(14, 8, 8, 0)
        alay.setSpacing(6)
        alay.addLayout(self._handle_row())
        ahead = QHBoxLayout()
        ahead.setSpacing(10)
        self.btn_activity_back = _IconButton("back", size=30)
        self.btn_activity_back.clicked.connect(self._close_activity)
        self._chrome_widgets.append(self.btn_activity_back)
        ahead.addWidget(self.btn_activity_back)
        atitles = QVBoxLayout()
        atitles.setSpacing(0)
        a_title = QLabel("Actividad")
        a_title.setStyleSheet("color:#fff; font-size:17px; font-weight:800; background:transparent;")
        a_sub = QLabel("Quién puso qué en Cumito")
        a_sub.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE2}; font-size:10.5px; background:transparent;")
        atitles.addWidget(a_title)
        atitles.addWidget(a_sub)
        ahead.addLayout(atitles)
        ahead.addStretch()
        self.activity_spinner = Spinner(18)
        ahead.addWidget(self.activity_spinner)
        ahead.addSpacing(8)
        alay.addLayout(ahead)
        self.activity_feed = ActivityFeed(self.art_cache)
        self.activity_scroll = _bare_scroll(self.activity_feed)
        alay.addWidget(self.activity_scroll, 1)

        # ---- mini-reproductor (durante el buscador) ----
        self.mini_player = _GlassPanel(self, tint_alpha=175)
        self.mini_player.setGeometry(0, H - 58, W, 58)
        self.mini_player.hide()
        mplay = QHBoxLayout(self.mini_player)
        mplay.setContentsMargins(16, 0, 16, 0)
        mplay.setSpacing(10)
        self.mp_thumb = QLabel()
        self.mp_thumb.setFixedSize(32, 32)
        mplay.addWidget(self.mp_thumb)
        mp_info = QVBoxLayout()
        mp_info.setSpacing(0)
        self.mp_title = _ElidedLabel("Nada sonando")
        self.mp_title.setStyleSheet(f"color:{theme.GLASS_TEXT}; font-size:11.5px; font-weight:700; background:transparent;")
        self.mp_artist = _ElidedLabel("")
        self.mp_artist.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE2}; font-size:10px; background:transparent;")
        mp_info.addWidget(self.mp_title)
        mp_info.addWidget(self.mp_artist)
        mplay.addLayout(mp_info, 1)
        self.mp_play = _IconButton("play", size=32, icon_size=15, icon_color="#111111")
        self.mp_play.clicked.connect(self._on_play_pause)
        mplay.addWidget(self.mp_play)
        self.mp_play.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.92); color:#111; border:none; border-radius: 16px; font-size: 12px; }"
        )

        self._chrome_widgets += [self.playlist_sheet, self.search_view, self.settings_view, self.activity_view,
                                 self.mini_player]

        # ---- aviso de actualización (baja desde arriba como notificación) ----
        self._build_update_banner()

        # ---- cuadro de texto flotante (encima de todo lo demás) ----
        self.text_overlay = _GlassTextOverlay(self)

        # ---- el aviso "¿Seguro?" con botón de mantener presionado ----
        self.hold_confirm = HoldConfirm(self)

    # ================= pintado de capas =================
    def _paint_scrim(self, label: QLabel, top: bool):
        pix = QPixmap(label.width(), label.height())
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        g = QLinearGradient(0, 0, 0, label.height())
        if top:
            g.setColorAt(0, QColor(0, 0, 0, 140))
            g.setColorAt(1, QColor(0, 0, 0, 0))
        else:
            g.setColorAt(0, QColor(8, 8, 11, 0))
            g.setColorAt(0.45, QColor(8, 8, 11, 170))
            g.setColorAt(1, QColor(8, 8, 11, 235))
        p.fillRect(pix.rect(), g)
        p.end()
        label.setPixmap(pix)

    def _build_update_banner(self):
        b = QWidget(self)
        b.setObjectName("updbanner")
        b.setStyleSheet(
            "QWidget#updbanner { background: rgba(28,26,38,0.96); border: 1px solid rgba(142,108,242,0.55);"
            " border-radius: 16px; }"
        )
        b.setGeometry(12, -60, W - 24, 52)
        lay = QVBoxLayout(b)
        lay.setContentsMargins(14, 7, 8, 7)
        lay.setSpacing(5)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.upd_label = QLabel("")
        self.upd_label.setStyleSheet(f"color:{theme.GLASS_TEXT}; font-size:12px; font-weight:700; background:transparent;")
        row.addWidget(self.upd_label, 1)
        self.upd_btn = QPushButton("Actualizar")
        self.upd_btn.setCursor(Qt.PointingHandCursor)
        self.upd_btn.setFixedHeight(28)
        self.upd_btn.setStyleSheet(
            f"QPushButton {{ background:{theme.GLASS_ACCENT}; color:white; border:none; border-radius:14px;"
            " font-size:11.5px; font-weight:800; padding:0 14px; }"
            "QPushButton:hover { background:#9C7EF5; }"
        )
        self.upd_btn.clicked.connect(lambda: self.update_requested.emit())
        row.addWidget(self.upd_btn)
        self.upd_close = QPushButton("")
        self.upd_close.setFixedSize(26, 26)
        self.upd_close.setCursor(Qt.PointingHandCursor)
        self.upd_close.setToolTip("Más tarde")
        self.upd_close.setIcon(icons.icon("close", "#A9A6B2", 12))
        self.upd_close.setIconSize(QSize(12, 12))
        self.upd_close.setStyleSheet(
            "QPushButton { background:transparent; border:none; border-radius:13px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.12); }"
        )
        self.upd_close.clicked.connect(self.hide_update)
        row.addWidget(self.upd_close)
        lay.addLayout(row)
        self.upd_progress = _ProgressBar()
        self.upd_progress.hide()
        lay.addWidget(self.upd_progress)
        b.hide()
        self.update_banner = b

    # ---- aviso de actualización: lo maneja main.py ----
    def show_update(self, version):
        self.upd_label.setText(f"Nueva versión de Cumito · {version}")
        self.upd_btn.setText("Actualizar")
        self.upd_btn.show()
        self.upd_close.show()
        self.upd_progress.hide()
        self._slide_banner(True)

    def set_update_progress(self, f):
        self.upd_btn.hide()
        self.upd_close.hide()
        self.upd_progress.show()
        self.upd_progress.setFraction(f)
        self.upd_label.setText(f"Descargando actualización… {int(f * 100)}%")

    def set_update_installing(self):
        self.upd_progress.setFraction(1.0)
        self.upd_label.setText("Instalando… Cumito se volverá a abrir")

    def set_update_failed(self, message=""):
        self.upd_progress.hide()
        self.upd_label.setText("No se pudo descargar. Intenta más tarde.")
        self.upd_btn.setText("Reintentar")
        self.upd_btn.show()
        self.upd_close.show()

    def hide_update(self):
        self._slide_banner(False)

    def _slide_banner(self, show):
        b = self.update_banner
        b.show()
        b.raise_()
        self.text_overlay.raise_()
        anim = QPropertyAnimation(b, b"pos", self)
        anim.setDuration(420 if show else 260)
        anim.setStartValue(b.pos())
        anim.setEndValue(QPoint(12, 8 if show else -60))
        anim.setEasingCurve(QEasingCurve.OutBack if show else QEasingCurve.InCubic)
        if not show:
            anim.finished.connect(b.hide)
        self._banner_anim = anim
        anim.start()

    def _handle_row(self):
        handle = QLabel()
        handle.setFixedSize(36, 4)
        handle.setStyleSheet("background: rgba(255,255,255,0.3); border-radius: 2px;")
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(handle)
        row.addStretch()
        return row

    def _repaint_panels(self):
        for w in (self.playlist_sheet, self.search_view, self.settings_view, self.activity_view, self.mini_player):
            w.update()

    # ================= switch de glass =================
    def _apply_glass(self, on: bool):
        self._glass_on = on
        for w in self._chrome_widgets:
            if isinstance(w, (_IconButton, _Pill)):
                w.apply_glass(on)
        self._repaint_panels()

    # ================= portada =================
    def _on_art_loaded(self, url, pixmap):
        np = self.state.get("now_playing")
        if np and np.get("art_url") == url:
            self._set_art_background(pixmap)
            self.mini_thumb.setPixmap(_rounded(_cover_pixmap(pixmap, 42, 42), 10))
            self.mp_thumb.setPixmap(_rounded(_cover_pixmap(pixmap, 32, 32), 9))
        self._refresh_sheet_list()
        self._refresh_recent()
        self._refresh_mosaic_thumbs(url, pixmap)
        self._refresh_preview_cards(url, pixmap)
        self.activity_feed.on_art_loaded(url, pixmap)

    def _set_art_background(self, pixmap):
        self._now_art = pixmap
        if self.mini is not None:
            self.mini.set_art(pixmap)
        # un poco más ancha que la ventana, para que se pasee de lado a lado
        if pixmap is not None and not pixmap.isNull():
            natural = int(pixmap.width() * H / max(1, pixmap.height()))
            pw = max(W, min(PAN_MAX_W, natural))
        else:
            pw = W
        self.art_bg.setPixmap(_cover_pixmap(pixmap, pw, H))
        self.art_bg.resize(pw, H)
        self._pan_range = pw - W
        self._on_pan()
        # el vidrio de los paneles usa esta misma portada, desenfocada
        self._blur_pix = _blur_pixmap(pixmap, W, H)
        if hasattr(self, "mini_player"):
            self._repaint_panels()

    def _refresh_mosaic_thumbs(self, url, pixmap):
        for tile, result in self._tiles:
            if result.get("art_url") == url:
                tile._set_art(pixmap, tile._size)

    # ================= estado =================
    def set_state(self, state: dict):
        prev_title = (self.state.get("now_playing") or {}).get("title")
        self.state.update(state)
        np = self.state.get("now_playing")
        if np and np.get("title") != prev_title:
            self._local_elapsed = 0.0
        if np:
            self._local_elapsed = float(np.get("elapsed", 0))
        self._refresh_now()
        self._refresh_sheet_list()
        self._refresh_recent()
        self._update_req_tiles()
        self._update_mode()
        self._on_activity(state.get("activity_last"))
        self._sync_mini()

    # ---- actividad ----
    def _on_activity(self, a):
        if not isinstance(a, dict) or a.get("id") is None:
            return
        key = (a.get("id"), a.get("text"))
        if key == self._last_act:
            return
        first = self._last_act is None
        new_id = first or a.get("id") != self._last_act[0]
        self._last_act = key
        if self._activity_loaded:
            self.activity_feed.add_or_update(a)
            if self._panel_mode == "activity":
                QTimer.singleShot(30, self._activity_to_bottom)
        # al conectarse llega la última que hubo: solo se anuncia si es reciente
        if new_id and (not first or time.time() - float(a.get("ts") or 0) < 15):
            self.ticker.show_activity(a)

    # ---- lo peligroso se confirma manteniendo presionado ----
    def _ask_clear_queue(self):
        n = len(self.state.get("queue") or [])
        if not n:
            return
        self.hold_confirm.ask(
            "¿Seguro que quieres borrar TODO?",
            f"Se van a quitar {'la canción' if n == 1 else f'las {n} canciones'} de la lista. "
            "Lo que está sonando ahora sigue sonando.",
            "Mantén presionado para borrar", "trash",
            lambda: self.send_command("queue_clear"),
        )

    def _ask_stop_bot(self):
        self.hold_confirm.ask(
            "¿Apagar a Cumito?",
            "Se detiene la música, se borra la lista y Cumito sale del canal de voz.",
            "Mantén presionado para apagar", "power",
            lambda: self.send_command("stop_and_leave"),
        )

    def open_activity(self):
        if self._panel_mode == "search":
            self.search_view.hide()
            self.mini_player.hide()
        if self._panel_mode == "settings":
            self.settings_view.hide()
        self._close_sheet()
        self._panel_mode = "activity"
        self._searching = True
        self._set_pills_visible(False)
        self.activity_spinner.setVisible(not self._activity_loaded)
        self._panel_in(self.activity_view)
        self.text_overlay.raise_()
        self.request_activity()
        QTimer.singleShot(420, self._activity_to_bottom)

    def set_activity_list(self, entries):
        self._activity_loaded = True
        self.activity_spinner.hide()
        self.activity_feed.set_entries(entries or [])
        QTimer.singleShot(40, self._activity_to_bottom)

    def _activity_to_bottom(self):
        bar = self.activity_scroll.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _close_activity(self):
        self._panel_out(self.activity_view)
        self._after_panel_closed()

    # ---- vista vacía vs. "ahora sonando" ----
    def _update_mode(self, animate=True):
        connected = self.state.get("connected", True)
        empty = (not self.state.get("now_playing")) or (not connected)

        if connected:
            self.empty_title.setText("¿Qué escucharemos hoy?")
            self.empty_subtitle.setText("")
            self.empty_subtitle.hide()
        else:
            self.empty_title.setText("Buscando a Cumito…")
            self.empty_subtitle.setText("No se pudo conectar con el servidor. Reintentando solo.")
            self.empty_subtitle.show()

        if empty == self._empty_mode:
            return
        self._empty_mode = empty
        if empty:
            self._close_sheet()
        self._set_pills_visible(not empty)  # en vacío ya está la barra grande
        if animate:
            self._fade(self.empty_view, show=empty)
            self._fade(self.now_overlay, show=not empty)
        else:
            self.empty_view.setVisible(empty)
            self.now_overlay.setVisible(not empty)

    def _fade(self, widget, show, duration=260):
        """Aparece/desaparece un panel suavemente. El efecto de opacidad solo
        existe mientras dura la animación (luego se quita), así que no deja
        ningún costo extra pegado."""
        prev = self._anims.pop(id(widget), None)
        if prev is not None:
            prev.stop()
        effect = QGraphicsOpacityEffect(widget)
        widget.setGraphicsEffect(effect)
        effect.setOpacity(0.0 if show else 1.0)
        if show:
            widget.show()
        anim = QPropertyAnimation(effect, b"opacity", self)
        anim.setDuration(duration)
        anim.setStartValue(0.0 if show else 1.0)
        anim.setEndValue(1.0 if show else 0.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)

        def _done():
            if not show:
                widget.hide()
            widget.setGraphicsEffect(None)
            self._anims.pop(id(widget), None)

        anim.finished.connect(_done)
        self._anims[id(widget)] = anim
        anim.start()

    def _refresh_recent(self, force=False):
        recent = self.state.get("recent") or []
        sig = tuple((r.get("webpage_url"), bool(self.art_cache.get(r.get("art_url")))) for r in recent)
        if sig == self._recent_sig and not force:
            return
        self._recent_sig = sig

        while self.recent_list_layout.count() > 1:
            item = self.recent_list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        for r in recent:
            self.art_cache.request(r.get("art_url"))
            row = _TrackRow(r.get("title") or "Sin título", r.get("uploader") or "", r.get("duration"),
                            pixmap=self.art_cache.get(r.get("art_url")), removable=False)
            row.setToolTip("Ponerla otra vez")
            row.clicked.connect(lambda url=r.get("webpage_url"): url and self.send_command("play", query=url))
            self.recent_list_layout.insertWidget(self.recent_list_layout.count() - 1, row)

        has_recent = bool(recent)
        self.recent_header.setVisible(has_recent)
        self.recent_scroll.setVisible(has_recent)
        self.recent_empty_label.setVisible(not has_recent)

    def _refresh_now(self):
        np = self.state.get("now_playing")
        if not np:
            self.now_title.setText("Nada sonando")
            self.now_artist.setText("")
            self.mp_title.setText("Nada sonando")
            self.mp_artist.setText("")
            self.progress.setFraction(0)
            self.time_elapsed.setText("0:00")
            self.time_total.setText("0:00")
            if self._showing_placeholder is not True:
                self._set_art_background(_placeholder_art(W, H))
                self._showing_placeholder = True
            self.mini_thumb.setPixmap(_gradient_label(42, 42, 10))
            self.mp_thumb.setPixmap(_gradient_label(32, 32, 9))
            self._set_play_icon(False)
            return

        self._showing_placeholder = False
        self.now_title.setText(np["title"])
        self.idle_title.setText(np["title"])
        self.idle_artist.setText(np.get("uploader") or "")
        self.mp_title.setText(np["title"])
        self.now_artist.setText(np.get("uploader") or "")
        self.mp_artist.setText(np.get("uploader") or "")

        art_url = np.get("art_url")
        cached = self.art_cache.get(art_url)
        if cached is not None:
            self._set_art_background(cached)
            self.mini_thumb.setPixmap(_rounded(_cover_pixmap(cached, 42, 42), 10))
            self.mp_thumb.setPixmap(_rounded(_cover_pixmap(cached, 32, 32), 9))
        else:
            self.art_cache.request(art_url)
            self.mini_thumb.setPixmap(_gradient_label(42, 42, 10))
            self.mp_thumb.setPixmap(_gradient_label(32, 32, 9))

        dur = np.get("duration") or 0
        elapsed = min(self._local_elapsed, dur) if dur else self._local_elapsed
        self.time_elapsed.setText(fmt_time(elapsed))
        self.time_total.setText(fmt_time(dur))
        self.progress.setFraction(elapsed / dur if dur else 0)
        self._set_play_icon(not np.get("paused"))

    def _set_play_icon(self, playing: bool):
        name = "pause" if playing else "play"
        self.btn_play.set_icon(name)
        self.mp_play.set_icon(name)

    def _refresh_sheet_list(self, force=False):
        # solo se rehace si de verdad cambió algo (con playlists largas,
        # rehacer 200 filas en cada aviso del servidor la pondría lenta)
        np_ = self.state.get("now_playing") or {}
        now_ = time.monotonic()
        sig = (
            np_.get("title"), bool(self.art_cache.get(np_.get("art_url"))),
            tuple((t.get("uid"), t.get("title"), t.get("ready", True), bool(t.get("loading")),
                   bool(self.art_cache.get(t.get("art_url"))), self._flash_until.get(t.get("uid"), 0) > now_)
                  for t in self.state.get("queue", [])),
        )
        if sig == self._sheet_sig and not force:
            return
        self._sheet_sig = sig
        # limpia lo anterior
        while self.sheet_list_layout.count() > 1:
            item = self.sheet_list_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        np = self.state.get("now_playing")
        queue = self.state.get("queue", [])
        self.btn_clear_queue.setEnabled(bool(queue))
        rows = []
        if np:
            row = _TrackRow(np["title"], np.get("uploader") or "", np.get("duration"),
                             pixmap=self.art_cache.get(np.get("art_url")), active=True, removable=False)
            rows.append(row)
        now = time.monotonic()
        seen_ready = set()
        for i, t in enumerate(queue):
            uid = t.get("uid")
            # servidores viejos no mandan "ready": se toma como lista
            ready = t.get("ready", True)
            status = "ready" if ready else ("loading" if t.get("loading") else "pending")
            if ready and uid is not None:
                seen_ready.add(uid)
                # recién quedó lista (antes la vimos sin estar lista): destello verde
                if uid in self._seen_unready:
                    self._seen_unready.discard(uid)
                    self._flash_until[uid] = now + 2.0
                    QTimer.singleShot(2100, lambda: self._refresh_sheet_list(force=True))
            elif uid is not None:
                self._seen_unready.add(uid)
            flash = ready and self._flash_until.get(uid, 0) > now
            if ready:
                self.art_cache.request(t.get("art_url"))
            row = _TrackRow(t["title"], t.get("uploader") or "", t.get("duration"),
                            pixmap=self.art_cache.get(t.get("art_url")), status=status, flash=flash)
            row.remove_clicked.connect(lambda idx=i, u=uid: self.send_command("queue_remove", index=idx))
            if status == "ready":
                row.setToolTip("Tócala para ponerla ya")
                row.clicked.connect(lambda idx=i, u=uid: self.send_command("play_index", index=idx, uid=u))
            elif status == "pending":
                row.clicked.connect(lambda idx=i, u=uid: self.send_command("prepare", index=idx, uid=u))
            rows.append(row)
        # que no crezcan sin fin
        self._flash_until = {u: t for u, t in self._flash_until.items() if t > now}

        for row in rows:
            self.sheet_list_layout.insertWidget(self.sheet_list_layout.count() - 1, row)

    # ================= controles =================
    def _on_play_pause(self):
        np = self.state.get("now_playing")
        if np and np.get("paused"):
            self.send_command("resume")
        elif np:
            self.send_command("pause")

    # ================= bandeja de playlist (scroll para abrir/cerrar) =================
    def _open_sheet(self):
        # en la vista vacía no hay cola que mostrar
        if self._sheet_open or self._searching or self._empty_mode:
            return
        self._sheet_open = True
        self._sheet_anim.stop()
        self._sheet_anim.setStartValue(self.playlist_sheet.pos())
        self._sheet_anim.setEndValue(QPoint(0, H - SHEET_H))
        self._sheet_anim.start()

    def _close_sheet(self):
        if not self._sheet_open:
            return
        self._sheet_open = False
        self._sheet_anim.stop()
        self._sheet_anim.setStartValue(self.playlist_sheet.pos())
        self._sheet_anim.setEndValue(QPoint(0, H))
        self._sheet_anim.start()

    def wheelEvent(self, ev):
        if self._searching:
            return
        delta = ev.angleDelta().y()
        if not self._sheet_open and delta < 0:
            self._open_sheet()
        elif self._sheet_open and delta > 0:
            self._close_sheet()
        ev.accept()

    def eventFilter(self, obj, ev):
        # Clic en una zona "vacía" (sin botón) de la barra de título o del
        # overlay de "ahora sonando": Qt entrega el evento directo a ese
        # widget contenedor y no lo sube solo al padre, así que si no lo
        # atendemos aquí, arrastrar la ventana desde ahí no funcionaría.
        # Los botones de adentro siguen recibiendo sus propios clics
        # normalmente (Qt los detecta primero, antes de llegar a este
        # filtro, así que no hay conflicto).
        #
        # Blindado a propósito: un error aquí adentro no se puede quedar
        # "suelto" (Qt lo convierte en un cierre de la app), así que si algo
        # raro pasa, simplemente se ignora ese evento y la ventana sigue.
        if not self._filters_ready:
            return False
        try:
            return self._handle_filtered_event(obj, ev)
        except Exception:
            return False

    def _handle_filtered_event(self, obj, ev):
        if obj is self.titlebar or obj is self.now_overlay or obj is self.empty_view:
            t = ev.type()
            if t == QEvent.MouseButtonPress and ev.button() == Qt.LeftButton:
                self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()
                return True
            if t == QEvent.MouseMove and self._drag_pos is not None and ev.buttons() & Qt.LeftButton:
                self.move(ev.globalPosition().toPoint() - self._drag_pos)
                return True
            if t == QEvent.MouseButtonRelease:
                self._drag_pos = None
                return True
            return False
        if obj is self.sheet_handle and ev.type() == QEvent.MouseButtonPress:
            self._close_sheet() if self._sheet_open else self._open_sheet()
            return True
        if obj is self.sheet_scroll.viewport() and ev.type() == QEvent.Wheel:
            bar = self.sheet_scroll.verticalScrollBar()
            if ev.angleDelta().y() > 0 and bar.value() <= bar.minimum():
                self._close_sheet()
                return True
        return super().eventFilter(obj, ev)

    # ================= paneles a pantalla completa (buscador / ajustes) =================
    def _panel_in(self, widget):
        """La hoja sube desde abajo, como la playlist."""
        self._stop_panel_anim()
        widget.move(0, H)
        widget.show()
        widget.raise_()
        anim = QPropertyAnimation(widget, b"pos", self)
        anim.setDuration(380)
        anim.setStartValue(QPoint(0, H))
        anim.setEndValue(QPoint(0, PANEL_TOP))
        anim.setEasingCurve(QEasingCurve.OutCubic)
        self._panel_anim = anim
        anim.start()

    def _panel_out(self, widget):
        """Y baja de vuelta."""
        self._stop_panel_anim()
        if not widget.isVisible():
            return
        anim = QPropertyAnimation(widget, b"pos", self)
        anim.setDuration(260)
        anim.setStartValue(widget.pos())
        anim.setEndValue(QPoint(0, H))
        anim.setEasingCurve(QEasingCurve.InCubic)

        def done():
            widget.hide()
            widget.move(0, PANEL_TOP)

        anim.finished.connect(done)
        self._panel_anim = anim
        anim.start()

    def _stop_panel_anim(self):
        anim = getattr(self, "_panel_anim", None)
        if anim is not None and anim.state() == QAbstractAnimation.Running:
            anim.setCurrentTime(anim.totalDuration())  # lo deja terminado al instante
        self._panel_anim = None

    def _after_panel_closed(self):
        self._searching = False
        self._panel_mode = None
        self._set_pills_visible(not self._empty_mode)

    # ---- buscador ----
    def _open_search(self):
        if self._panel_mode == "settings":
            self.settings_view.hide()
        if self._panel_mode == "activity":
            self.activity_view.hide()
        self._close_sheet()
        self._panel_mode = "search"
        self._searching = True
        self._set_pills_visible(False)
        if not self.search_input.text().strip():
            self._refresh_search_home()
            self._show_search_state("home")
        self._panel_in(self.search_view)
        self.mini_player.show()
        self.mini_player.raise_()
        self.text_overlay.raise_()
        self._liquid_bar_in()
        self.search_input.setFocus()
        self.search_input.selectAll()

    def _liquid_bar_in(self):
        """La barra de búsqueda se "estira" al aparecer, con un rebotito."""
        anim = QPropertyAnimation(self.search_input, b"maximumWidth", self)
        anim.setDuration(560)
        anim.setStartValue(70)
        anim.setEndValue(W - 28 - 30 - 8)
        anim.setEasingCurve(QEasingCurve.OutBack)
        anim.finished.connect(lambda: self.search_input.setMaximumWidth(16777215))
        self._bar_anim = anim
        anim.start()

    def _close_search(self):
        self._panel_out(self.search_view)
        self.mini_player.hide()
        self._after_panel_closed()

    def _show_search_state(self, state):
        """"home" (recientes), "loading" (Cumito saltando) o "results"."""
        self.search_home.setVisible(state == "home")
        self.search_loader.setVisible(state == "loading")
        self.results_scroll.setVisible(state == "results")
        self.preview_box.setVisible(state == "preview")
        if self._panel_mode == "search":
            self.mini_player.setVisible(state != "preview")

    def _on_search_text_changed(self, text):
        if not text.strip() and self._panel_mode == "search":
            self._search_query = None
            self._refresh_search_home()
            self._show_search_state("home")

    def _section_label(self, text):
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color:{theme.GLASS_TEXT_MUTE}; font-size:10px; font-weight:700; letter-spacing:1px;"
            " background:transparent; padding-top:8px;"
        )
        return lbl

    def _refresh_search_home(self):
        lay = self.search_home_layout
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if self.recent_searches:
            lay.addWidget(self._section_label("BÚSQUEDAS RECIENTES"))
            for q in self.recent_searches:
                btn = QPushButton("  " + q)
                btn.setCursor(Qt.PointingHandCursor)
                btn.setFixedHeight(36)
                btn.setIcon(icons.icon("search", "#A9A6B2", 14))
                btn.setIconSize(QSize(14, 14))
                btn.setStyleSheet(
                    f"QPushButton {{ text-align:left; padding-left:10px; background:transparent; border:none;"
                    f" border-radius:10px; color:{theme.GLASS_TEXT}; font-size:12px; }}"
                    "QPushButton:hover { background: rgba(255,255,255,0.08); }"
                )
                btn.clicked.connect(lambda _=False, q=q: (self.search_input.setText(q), self._submit_search()))
                lay.addWidget(btn)

        recent = self.state.get("recent") or []
        if recent:
            lay.addWidget(self._section_label("LO ÚLTIMO QUE SONÓ"))
            for r in recent:
                row = _TrackRow(r.get("title") or "Sin título", r.get("uploader") or "", r.get("duration"),
                                pixmap=self.art_cache.get(r.get("art_url")), removable=False)
                row.setToolTip("Ponerla otra vez")
                row.clicked.connect(lambda url=r.get("webpage_url"): url and self.send_command("play", query=url))
                lay.addWidget(row)

        if not self.recent_searches and not recent:
            hint = QLabel("Busca una canción o pega el link\nde una canción o playlist.")
            hint.setAlignment(Qt.AlignCenter)
            hint.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE}; font-size:12px; background:transparent; padding-top:40px;")
            lay.addWidget(hint)
        lay.addStretch()

    def _remember_search(self, query):
        q = query.strip()
        if not q:
            return
        searches = [s for s in self.recent_searches if s.lower() != q.lower()]
        self.recent_searches = ([q] + searches)[:6]
        self.on_recent_searches_changed(list(self.recent_searches))

    def _submit_search(self):
        query = self.search_input.text().strip()
        if not query:
            return
        # Un link (canción o playlist) se pone directo: no tiene sentido
        # mostrarlo en el mosaico para que lo vuelvan a elegir.
        if query.lower().startswith(("http://", "https://", "www.", "youtu.be/", "youtube.com/", "soundcloud.com/")):
            if not query.lower().startswith(("http://", "https://")):
                query = "https://" + query
            low = query.lower()
            if "list=" in low or ("soundcloud.com" in low and "/sets/" in low):
                # es (o trae) una playlist: primero se muestra qué tiene
                self._preview = {"url": query, "loading": True}
                self.loader_label.setText("Abriendo playlist…")
                self._show_search_state("loading")
                self.send_command("playlist_preview", url=query)
                return
            self.send_command("play", query=query)
            self.search_input.clear()
            self._close_search()
            return
        self.loader_label.setText("Buscando…")
        self._remember_search(query)
        self._search_query = query
        self._search_count = 0
        self._clear_mosaic()
        self._show_search_state("loading")
        self.do_search(query, 8, 0, kind=self._search_kind)

    # ---- vista previa de playlist ----
    def show_playlist_preview(self, data):
        if self._panel_mode != "search" or not self._preview or data.get("url") != self._preview.get("url"):
            return  # llegó tarde o ya se cerró
        self._preview = data
        entries = data.get("entries") or []
        url = (data.get("url") or "").lower()
        lay = self.preview_list_layout
        while lay.count():
            item = lay.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.preview_stack.set_cards([None, None, None], "", "")
        if not entries:
            self.preview_question.setText("No pude abrir esa playlist")
            self.preview_name.setText("Puede que sea privada o que el link esté incompleto.")
            self.preview_add.hide()
            self.preview_single.setVisible("v=" in url or "youtu.be/" in url)
            self.preview_no.setText("Volver")
            self.preview_no.hold_required = False   # aquí no hay nada que descartar
        else:
            self.preview_question.setText("¿Quieres poner esta playlist?")
            name = data.get("title") or "Playlist"
            self.preview_name.setText(f"{name} · {len(entries)} canciones")
            self.preview_add.show()
            self.preview_add.setText(f"Añadir las {len(entries)}")
            self.preview_single.setVisible("v=" in url or "youtu.be/" in url)
            self.preview_no.setText("No gracias")
            self.preview_no.hold_required = True
            self.preview_no.reset()
            pix = []
            for e in entries[:3]:
                self.art_cache.request(e.get("art_url"))
                pix.append(self.art_cache.get(e.get("art_url")))
            self.preview_stack.set_cards(pix, name, f"{len(entries)} canciones")
            for i, e in enumerate(entries, 1):
                lbl = _ElidedLabel(f"{i}.  {e.get('title') or 'Sin título'}")
                lbl.setStyleSheet(f"color:{theme.GLASS_TEXT}; font-size:12px; background:transparent; padding:3px 0;")
                lay.addWidget(lbl)
        lay.addStretch()
        self._show_search_state("preview")
        self.preview_stack.play_intro()

    def _set_preview_card(self, i, pixmap):
        self.preview_stack.set_card(i, pixmap)

    def _refresh_preview_cards(self, url, pixmap):
        entries = (self._preview or {}).get("entries") or []
        for i, e in enumerate(entries[:3]):
            if e.get("art_url") == url:
                self._set_preview_card(i, pixmap)

    def _preview_accept(self):
        if self._preview and self._preview.get("url"):
            self.send_command("play", query=self._preview["url"], as_playlist=True)
        self._preview = None
        self.search_input.clear()
        self._close_search()

    def _preview_single_song(self):
        if self._preview and self._preview.get("url"):
            self.send_command("play", query=self._preview["url"])
        self._preview = None
        self.search_input.clear()
        self._close_search()

    def _preview_cancel(self):
        self._preview = None
        self.search_input.clear()   # vuelve a "recientes"
        self._refresh_search_home()
        self._show_search_state("home")

    def _style_search_tabs(self):
        for kind, b in self.search_tabs.items():
            on = kind == self._search_kind
            b.setStyleSheet(
                "QPushButton { border-radius: 10px; padding: 0 15px; font-size: 12.5px; font-weight: 700;"
                + (" background: rgba(255,255,255,0.92); color: #141318; border: none; }"
                   if on else
                   " background: rgba(255,255,255,0.09); color: #F2F0F7; border: 1px solid rgba(255,255,255,0.10); }"
                   "QPushButton:hover { background: rgba(255,255,255,0.16); }")
            )

    def _set_search_kind(self, kind):
        if kind == self._search_kind:
            return
        self._search_kind = kind
        self._style_search_tabs()
        # si ya había una búsqueda, se repite en la pestaña nueva
        if self._search_query and not self._preview and (
                self.results_scroll.isVisible() or self.search_loader.isVisible()):
            self._search_count = 0
            self._clear_mosaic()
            self.loader_label.setText("Buscando…")
            self._show_search_state("loading")
            self.do_search(self._search_query, 8, 0, kind=self._search_kind)

    def _search_more(self):
        if not self._search_query:
            return
        self.more_btn.setEnabled(False)
        self.more_btn.setText("Buscando más…")
        self.more_spinner.show()
        self.do_search(self._search_query, 8, self._search_count, kind=self._search_kind)

    # ---- añadir desde el buscador: "Añadiendo…" -> "Añadido · #3" ----
    def _add_from_search(self, tile, result):
        req = uuid.uuid4().hex[:12]
        tile.set_adding()
        self._req_tiles[req] = tile
        self.send_command("play", query=result["webpage_url"], req=req)
        QTimer.singleShot(45000, lambda: self._add_timeout(req))

    def _add_timeout(self, req):
        tile = self._req_tiles.get(req)
        try:
            if tile is not None and tile.state == "adding":
                tile.set_failed()
                self._req_tiles.pop(req, None)
        except RuntimeError:
            self._req_tiles.pop(req, None)  # el resultado ya no existe

    def _update_req_tiles(self):
        if not self._req_tiles:
            return
        np_ = self.state.get("now_playing") or {}
        pos = {t.get("req"): i + 1 for i, t in enumerate(self.state.get("queue") or []) if t.get("req")}
        for req, tile in list(self._req_tiles.items()):
            try:
                if np_.get("req") == req:
                    tile.set_added("Sonando ahora")
                elif req in pos:
                    tile.set_added(f"Añadido · #{pos[req]} en la lista")
                # si ya no está ni sonando ni en la cola (ya sonó), se queda como estaba
            except RuntimeError:
                self._req_tiles.pop(req, None)

    def _clear_mosaic(self):
        self._req_tiles = {}
        for tile, _ in self._tiles:
            tile.deleteLater()
        self._tiles = []
        while self.mosaic_grid.count():
            item = self.mosaic_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    def set_search_results(self, query, results, offset=0, kind=None):
        if self._panel_mode != "search" or query != self._search_query:
            return  # llegó tarde: ya se buscó otra cosa
        if kind is not None and kind != self._search_kind:
            return  # era de la otra pestaña
        if offset == 0:
            self._clear_mosaic()
            self._search_count = 0
            self.results_scroll.verticalScrollBar().setValue(0)
        tile_size = (W - 28 - 12) // 2
        new_tiles = []
        for k, r in enumerate(results):
            i = self._search_count + k
            tile = _Tile(r["title"], r.get("uploader") or "", pixmap=self.art_cache.get(r.get("art_url")), size=tile_size)
            tile.clicked.connect(lambda t=tile, res=r: self._add_from_search(t, res))
            self.mosaic_grid.addWidget(tile, i // 2, i % 2)
            self._tiles.append((tile, r))
            new_tiles.append(tile)
            self.art_cache.request(r.get("art_url"))
        self._search_count += len(results)
        self.no_results_lbl.setVisible(self._search_count == 0)
        self.more_spinner.hide()
        self.more_btn.setText("Buscar más")
        self.more_btn.setEnabled(True)
        # si llegaron menos de los pedidos, ya no hay más que buscar
        self.more_btn.setVisible(len(results) >= 8)
        self._show_search_state("results")
        stagger_fade_in(self, new_tiles)

    # ---- ajustes (pantalla propia) ----
    # ---------- la rueda de Opciones y sus secciones ----------
    MENU_TITLES = {"main": "Opciones", "apariencia": "Apariencia", "size": "Tamaño",
                   "streamer": "Modo streamer", "shape": "Forma del mini", "chroma": "Fondo para OBS",
                   "dim": "Oscuridad"}
    MENU_PARENT = {"apariencia": "main", "streamer": "main", "size": "apariencia",
                   "shape": "streamer", "chroma": "streamer", "dim": "apariencia"}
    SCALES = [(1.0, "100%"), (0.9, "90%"), (0.8, "80%"), (0.7, "70%")]
    DIMS = [(0.0, "Sin oscurecer"), (0.15, "15%"), (0.3, "30%"), (0.5, "50%"), (0.75, "75%"),
            (1.0, "100%")]

    @staticmethod
    def _pct(value, table):
        return min(table, key=lambda t: abs(t[0] - value))[1]

    def _menu_items(self, menu):
        v = self.visual
        back = {"key": "back", "label": "Volver", "icon": "back_list"}
        if menu == "apariencia":
            return [back,
                    {"key": "glass", "label": "Efecto vidrio", "icon": "sparkle",
                     "hint": "Encendido" if self._glass_on else "Apagado"},
                    {"key": "menu:size", "label": "Tamaño de Cumito", "icon": "resize",
                     "hint": self._pct(self.ui_scale, self.SCALES)},
                    {"key": "dim_editor", "label": "Oscuridad del mini", "icon": "dim",
                     "hint": f"{round(v['mini_dim'] * 100)}%"}]
        if menu == "size":
            return [back] + [{"key": f"scale:{val}", "label": name, "icon": "resize",
                              "hint": "Actual" if abs(val - self.ui_scale) < 0.01 else None}
                             for val, name in self.SCALES]
        if menu == "streamer":
            return [back,
                    {"key": "streamer", "label": "Modo streamer", "icon": "streamer",
                     "hint": "Encendido" if v["streamer"] else "Apagado"},
                    {"key": "menu:shape", "label": "Forma del mini", "icon": "shape_" + {
                        "cuadrado": "square", "vertical": "tall", "ancho": "wide",
                        "circulo": "circle", "disco": "disc"}[v["mini_shape"]], "hint": SHAPE_NAMES[v["mini_shape"]]},
                    {"key": "menu:chroma", "label": "Fondo para OBS", "icon": "palette",
                     "hint": CHROMAS.get(v["chroma"], "Sin fondo")}]
        if menu == "shape":
            icon = {"cuadrado": "shape_square", "vertical": "shape_tall", "ancho": "shape_wide",
                    "circulo": "shape_circle", "disco": "shape_disc"}
            return [back] + [{"key": "shape:" + k, "label": name, "icon": icon[k],
                              "hint": "Elegida" if v["mini_shape"] == k else None}
                             for k, name in SHAPE_NAMES.items()]
        if menu == "chroma":
            return [back] + [{"key": "chroma:" + k, "label": name, "icon": "palette",
                              "hint": "Elegido" if v["chroma"] == k else None}
                             for k, name in CHROMAS.items()]
        if menu == "dim":
            return [back] + [{"key": f"dim:{val}", "label": name, "icon": "dim",
                              "hint": "Elegida" if abs(val - v["mini_dim"]) < 0.01 else None}
                             for val, name in self.DIMS]
        # menú principal
        items = [{"key": "activity", "label": "Actividad", "icon": "chat"},
                 {"key": "menu:apariencia", "label": "Apariencia", "icon": "sparkle"},
                 {"key": "menu:streamer", "label": "Modo streamer", "icon": "streamer",
                  "hint": "Encendido" if v["streamer"] else "Apagado"}]
        for row in self.settings_rows():
            label, icon = (row, "settings") if isinstance(row, str) else row
            items.append({"key": "row:" + label, "label": label, "icon": icon})
        items.append({"key": "power", "label": "Apagar Cumito", "icon": "power", "danger": True})
        return items

    def _show_dim_editor(self):
        self._menu = "dim"
        self.options_title.setText("Oscuridad del mini")
        self.options_sub.setText("Arrastra la barrita o usa\nla rueda del mouse")
        self.option_wheel.hide()
        self.dim_editor.show()
        np = self.state.get("now_playing") or {}
        self.dim_editor.open(self.visual["mini_dim"], self.visual["mini_shape"], self.visual["chroma"],
                             self._now_art, np.get("title") or "Nada sonando", np.get("uploader") or "Cumito")

    def _on_dim_changed(self, value):
        self.visual["mini_dim"] = round(value, 3)
        self.visual["mini_dim_set"] = True
        if self.mini is not None:
            self.mini.set_dim(value)
        self._dim_save.start()

    def _options_back(self):
        """La flechita de arriba: sube un nivel (o cierra si ya está en el principal)."""
        menu = getattr(self, "_menu", "main")
        if menu == "main":
            self._close_settings()
            return
        parent = self.MENU_PARENT.get(menu, "main")
        self._show_menu(parent, keep_key="dim_editor" if menu == "dim" else "menu:" + menu)

    def _show_menu(self, menu, keep_key=None):
        self._menu = menu
        self.dim_editor.hide()
        self.option_wheel.show()
        self.options_sub.setText("Gira la rueda del mouse\ny toca la que quieras")
        self.option_wheel.setFocus()
        self.options_title.setText(self.MENU_TITLES.get(menu, "Opciones"))
        items = self._menu_items(menu)
        if keep_key is None and len(items) > 1 and items[0]["key"] == "back":
            keep_key = items[1]["key"]   # al entrar a una sección: la primera opción, no "Volver"
        self.option_wheel.set_items(items, keep_key=keep_key)

    def _visual_changed(self):
        self.on_visual_changed(dict(self.visual))
        self._set_pills_visible(not self._empty_mode and not self._panel_mode)
        if self.mini is not None:
            self.mini.set_shape(self.visual["mini_shape"])
            self.mini.set_chroma(self.visual["chroma"])
            self.mini.set_dim(self.visual["mini_dim"])

    def _open_settings(self):
        if self._panel_mode == "search":
            self.search_view.hide()
            self.mini_player.hide()
        if self._panel_mode == "activity":
            self.activity_view.hide()
        self._close_sheet()
        self._panel_mode = "settings"
        self._searching = True
        self._set_pills_visible(False)
        self._show_menu("main", keep_key=self._last_option)
        self._panel_in(self.settings_view)
        self.text_overlay.raise_()
        self.option_wheel.setFocus()

    def _on_option(self, key):
        menu = getattr(self, "_menu", "main")
        if key == "back":
            parent = self.MENU_PARENT.get(menu, "main")
            self._show_menu(parent, keep_key="menu:" + menu)
            return
        if key.startswith("menu:"):
            sub = key[5:]
            if menu == "main":
                self._last_option = key
            cur = {"size": f"scale:{self.ui_scale}", "shape": "shape:" + self.visual["mini_shape"],
                   "chroma": "chroma:" + self.visual["chroma"]}.get(sub)
            if sub == "dim":
                cur = "dim:" + str(min(self.DIMS, key=lambda t: abs(t[0] - self.visual["mini_dim"]))[0])
            if sub == "size":
                cur = "scale:" + str(min(self.SCALES, key=lambda t: abs(t[0] - self.ui_scale))[0])
            self._show_menu(sub, keep_key=cur)
            return
        if key.startswith("shape:") or key.startswith("chroma:") or key.startswith("dim:"):
            name, val = key.split(":", 1)
            if name == "shape":
                self.visual["mini_shape"] = val
            elif name == "chroma":
                self.visual["chroma"] = val
            else:
                self.visual["mini_dim"] = float(val)
            self._visual_changed()
            self._show_menu("streamer", keep_key="menu:" + name)
            return
        if key.startswith("scale:"):
            val = float(key[6:])
            if abs(val - self.ui_scale) < 0.01:
                self._show_menu("apariencia", keep_key="menu:size")
                return
            # el tamaño se aplica al abrir: Cumito se reinicia solo
            self.on_scale_changed(val)
            return
        if key == "streamer":
            self.visual["streamer"] = not self.visual["streamer"]
            self._visual_changed()
            self._show_menu(menu, keep_key="streamer")
        elif key == "glass":
            self._apply_glass(not self._glass_on)
            self.visual["glass"] = self._glass_on
            self._visual_changed()
            self._show_menu(menu, keep_key="glass")
        elif key == "dim_editor":
            self._show_dim_editor()
        elif key == "activity":
            self._last_option = key
            self.open_activity()
        elif key == "power":
            self._last_option = key
            self._close_settings()
            self._ask_stop_bot()
        elif key.startswith("row:"):
            self._last_option = key
            self._close_settings()
            self.on_settings_row(key[4:])

    def _close_settings(self):
        self._panel_out(self.settings_view)
        self._after_panel_closed()

    def keyPressEvent(self, ev):
        if ev.key() == Qt.Key_Escape:
            if self._panel_mode == "search":
                self._close_search()
                return
            if self._panel_mode == "settings":
                self._options_back()
                return
            if self._panel_mode == "activity":
                self._close_activity()
                return
        super().keyPressEvent(ev)

    # ================= ventana: arrastrar =================
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, ev):
        if self._drag_pos is not None and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, ev):
        self._drag_pos = None

    # ================= pausar la animación si la ventana no se ve =================
    def hideEvent(self, ev):
        self._timer.stop()
        self._pan_timer.stop()
        super().hideEvent(ev)

    def showEvent(self, ev):
        if not self._timer.isActive():
            self._timer.start(TICK_MS)
        if not self._pan_timer.isActive():
            self._pan_timer.start(PAN_TICK_MS)
        super().showEvent(ev)

    def changeEvent(self, ev):
        if ev.type() == QEvent.WindowStateChange:
            if self.isMinimized():
                self._timer.stop()
                self._pan_timer.stop()
            else:
                if not self._timer.isActive():
                    self._timer.start(TICK_MS)
                if not self._pan_timer.isActive():
                    self._pan_timer.start(PAN_TICK_MS)
        super().changeEvent(ev)

    # ================= modo "solo portada" =================
    def enterEvent(self, ev):
        self._poke()
        super().enterEvent(ev)

    def _poke(self):
        self._last_poke = time.monotonic()
        if self._idle:
            self._set_idle(False)

    def _idle_blocked(self):
        return bool(
            self._panel_mode or self._sheet_open or self._empty_mode
            or not self.state.get("now_playing")
            or self.hold_confirm.isVisible() or self.text_overlay.isVisible()
            or (self.update_banner.isVisible() and self.update_banner.y() > 0)
        )

    def _check_idle(self):
        # el mouse se movió encima de la ventana = alguien está mirando
        pos = QCursor.pos()
        if pos != self._last_cursor:
            self._last_cursor = pos
            if self.frameGeometry().contains(pos):
                self._poke()
        if self._idle_blocked():
            self._last_poke = time.monotonic()
            if self._idle:
                self._set_idle(False)
        elif not self._idle and time.monotonic() - self._last_poke > IDLE_S:
            self._set_idle(True)

    def _check_streamer_idle(self):
        """En modo streamer, 8 s sin tocar nada = vuelve solo al mini."""
        pos = QCursor.pos()
        if pos != self._last_cursor:
            self._last_cursor = pos
            if self.frameGeometry().contains(pos):
                self._last_poke = time.monotonic()
        busy = (self._panel_mode or self._sheet_open or self.hold_confirm.isVisible()
                or self.text_overlay.isVisible())
        if busy:
            self._last_poke = time.monotonic()
        elif time.monotonic() - self._last_poke > IDLE_S:
            self.enter_mini()

    # ================= modo mini (streamer) =================
    def _set_pills_visible(self, visible):
        self.search_pill.setVisible(bool(visible))
        self.mini_pill.setVisible(bool(visible) and self.visual.get("streamer", False))

    def _sync_mini(self):
        m = self.mini
        if m is None:
            return
        np = self.state.get("now_playing")
        if np and self.state.get("connected", True):
            m.set_track(np.get("title"), np.get("uploader"))
            m.set_progress(self._local_elapsed, np.get("duration") or 0, np.get("paused"))
        else:
            m.set_track("Nada sonando", "Cumito")
            m.set_progress(0, 0, True)

    def enter_mini(self):
        if self.mini is None:
            self.mini = MiniWindow(self.visual["mini_shape"], self.visual["chroma"])
            self.mini.setWindowIcon(self.windowIcon())
            self.mini.expand.connect(self.exit_mini)
            self.mini.play_pause.connect(self._on_play_pause)
            self.mini.next_.connect(lambda: self.send_command("skip"))
            self.mini.move(self.pos())
        self.mini.set_shape(self.visual["mini_shape"])
        self.mini.set_chroma(self.visual["chroma"])
        self.mini.set_dim(self.visual["mini_dim"])
        if self._now_art is not None:
            self.mini.set_art(self._now_art)
        self._sync_mini()
        self.mini.show()
        self.mini.raise_()
        self.hide()

    def exit_mini(self):
        self._last_poke = time.monotonic()
        self._last_cursor = QCursor.pos()
        self.show()
        self.raise_()
        self.activateWindow()
        if self.mini is not None:
            self.mini.hide()

    def _idle_opacity(self, widget, show, ms, keep_effect=False):
        fx = self._idle_fx.get(widget)
        if fx is not None and widget.graphicsEffect() is not fx:
            fx = None  # otra animación le cambió el efecto: se arma uno nuevo
        if fx is None:
            fx = QGraphicsOpacityEffect(widget)
            fx.setOpacity(0.0 if show else 1.0)
            widget.setGraphicsEffect(fx)
            self._idle_fx[widget] = fx
        if show:
            widget.show()
        anim = QPropertyAnimation(fx, b"opacity", self)
        anim.setDuration(ms)
        anim.setStartValue(fx.opacity())
        anim.setEndValue(1.0 if show else 0.0)
        anim.setEasingCurve(QEasingCurve.InOutCubic)

        def done():
            if not show:
                widget.hide()
            if show and not keep_effect:
                # visible del todo: se quita el efecto (no cuesta nada mientras se usa)
                widget.setGraphicsEffect(None)
                self._idle_fx.pop(widget, None)
        anim.finished.connect(done)
        self._anims[("idle", id(widget))] = anim
        anim.start()

    def _set_idle(self, on):
        if on == self._idle:
            return
        self._idle = on
        ms = 700 if on else 380
        # barra de arriba: se va hacia arriba / vuelve
        tb = QPropertyAnimation(self.titlebar, b"pos", self)
        tb.setDuration(ms)
        tb.setStartValue(self.titlebar.pos())
        tb.setEndValue(QPoint(0, -self.titlebar.height() - 6) if on else QPoint(0, 0))
        tb.setEasingCurve(QEasingCurve.InOutCubic)
        self._anims["idle_tb"] = tb
        tb.start()
        self._idle_opacity(self.scrim_top, not on, ms, keep_effect=True)
        self._idle_opacity(self.scrim_bottom, not on, ms, keep_effect=True)
        self._idle_opacity(self.scrim_names, on, ms, keep_effect=True)
        if on or not self._empty_mode:
            self._idle_opacity(self.now_overlay, not on, ms)
        # el nombre baja a su lugar mientras aparece (o sube al irse)
        self.idle_caption.raise_()
        self._idle_opacity(self.idle_caption, on, ms, keep_effect=True)
        cap = QPropertyAnimation(self.idle_caption, b"pos", self)
        cap.setDuration(ms)
        low, high = QPoint(22, H - 70), QPoint(22, H - 150)
        cap.setStartValue(high if on else self.idle_caption.pos())
        cap.setEndValue(low if on else high)
        cap.setEasingCurve(QEasingCurve.OutCubic if on else QEasingCurve.InCubic)
        self._anims["idle_cap"] = cap
        cap.start()

    # ================= el fondo se pasea lento de lado a lado =================
    def _on_pan(self):
        if self.visual.get("streamer"):
            return  # modo streamer: más liviano, el fondo queda quieto
        if self._pan_range <= 0:
            if self.art_bg.x() != 0:
                self.art_bg.move(0, 0)
            return
        # ida y vuelta: PAN_EDGE_S segundos de una esquina a la otra, suave
        # al llegar a cada esquina (como un coseno)
        t = (time.monotonic() - self._pan_t0) / PAN_EDGE_S
        x = -round(self._pan_range * (0.5 - 0.5 * math.cos(math.pi * t)))
        if x != self.art_bg.x():
            self.art_bg.move(x, 0)

    # ================= animación / reloj =================
    def _on_tick(self):
        if self.visual.get("streamer"):
            if self._idle:
                self._set_idle(False)
            self._check_streamer_idle()
        else:
            self._check_idle()
        np = self.state.get("now_playing")
        if np and not np.get("paused") and self.state.get("connected", True):
            self._local_elapsed += TICK_MS / 1000
            dur = np.get("duration") or 0
            elapsed = min(self._local_elapsed, dur) if dur else self._local_elapsed
            self.time_elapsed.setText(fmt_time(elapsed))
            self.progress.setFraction(elapsed / dur if dur else 0)
        if self._sheet_open:
            # el ecualizador solo se anima mientras la bandeja está visible
            # -- si está cerrada, nadie lo ve, así que no tiene sentido
            # seguir repintándolo cada rato
            for row in self.sheet_list_widget.findChildren(_TrackRow):
                if row.eq is not None:
                    row.eq.tick()
