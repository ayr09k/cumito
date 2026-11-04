"""
Modo mini (para stream): una ventanita con la forma que se elija en
Opciones, pensada para capturarla en OBS.

Formas: "cuadrado", "vertical", "ancho" y "circulo". Todo se dibuja a mano
en un solo paintEvent (sin widgets adentro), así pesa casi nada:
  - la portada de fondo con un velo oscuro,
  - el iconito de "radio" (las barritas) que vuelve al modo normal,
  - el nombre (se desliza si es largo) y el artista,
  - pausa, atrás, siguiente y la barrita de progreso (en curva en el
    vertical y en el círculo).
Opcional: un fondo de color sólido alrededor (verde, azul...) para quitarlo
en OBS con el filtro "Chroma Key".
"""
from __future__ import annotations

import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QWidget

from . import icons, theme

SHAPES = {
    "cuadrado": (230, 230),
    "vertical": (230, 470),
    "ancho": (470, 230),
    "circulo": (240, 240),
}
SHAPE_NAMES = {"cuadrado": "Cuadrado", "vertical": "Vertical", "ancho": "Ancho", "circulo": "Círculo"}
CHROMAS = {"": "Sin fondo", "#00B140": "Verde", "#0047BB": "Azul", "#FF00FF": "Magenta"}
RADIUS = 30
MARQUEE_PX_S = 28
MARQUEE_MS = 50   # ~20 cuadros/s, y SOLO si el nombre no cabe


class MiniWindow(QWidget):
    expand = Signal()        # el iconito de radio: volver al modo normal
    play_pause = Signal()
    next_ = Signal()
    prev = Signal()

    def __init__(self, shape="cuadrado", chroma=""):
        super().__init__(None)
        self.setWindowTitle("Cumito mini")
        # ventana normal (para que OBS la encuentre en su lista) y siempre encima
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._shape = "cuadrado"
        self._chroma = chroma or ""
        self._dim = 0.3            # cuánto velo oscuro (1.0 = el de antes)
        self._title = "Nada sonando"
        self._artist = ""
        self._art = None           # portada ya recortada al tamaño
        self._art_src = None
        self._elapsed = 0.0
        self._dur = 0
        self._paused = True
        self._clock_at = time.monotonic()
        self._prev_enabled = False
        self._hits = {}
        self._hover = None
        self._press = None
        self._marquee_x = 0.0
        self._marquee_last = time.monotonic()
        self.setMouseTracking(True)

        self._f_title = QFont(theme.GLASS_FONT_FAMILY)
        self._f_title.setPixelSize(14)
        self._f_title.setWeight(QFont.DemiBold)
        self._f_artist = QFont(theme.GLASS_FONT_FAMILY)
        self._f_artist.setPixelSize(10)
        self._f_artist.setLetterSpacing(QFont.AbsoluteSpacing, 0.6)

        self._sec = QTimer(self)          # el progreso: una vez por segundo
        self._sec.timeout.connect(self.update)
        self._sec.start(1000)
        self._marq = QTimer(self)         # el nombre deslizándose
        self._marq.setInterval(MARQUEE_MS)
        self._marq.timeout.connect(self._marquee_step)
        self.set_shape(shape)

    # ---------------- datos ----------------
    def set_shape(self, shape):
        self._shape = shape if shape in SHAPES else "cuadrado"
        w, h = SHAPES[self._shape]
        self.setFixedSize(w, h)
        self._f_title.setPixelSize(15 if self._shape == "ancho" else 14)
        self._rescale_art()
        self._check_marquee()
        self.update()

    def set_dim(self, value):
        self._dim = max(0.0, min(1.0, float(value)))
        self.update()

    def set_chroma(self, color):
        self._chroma = color or ""
        self.update()

    def set_track(self, title, artist):
        title = title or "Nada sonando"
        if title != self._title:
            self._marquee_x = 0.0
        self._title, self._artist = title, (artist or "")
        self._check_marquee()
        self.update()

    def set_art(self, pixmap):
        self._art_src = pixmap
        self._rescale_art()
        self.update()

    def set_progress(self, elapsed, duration, paused):
        self._elapsed = float(elapsed or 0)
        self._dur = float(duration or 0)
        self._paused = bool(paused)
        self._clock_at = time.monotonic()
        self.update()

    def _rescale_art(self):
        src = self._art_src
        if src is None or src.isNull():
            self._art = None
            return
        w, h = self.width(), self.height()
        scaled = src.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        self._art = scaled.copy((scaled.width() - w) // 2, (scaled.height() - h) // 2, w, h)

    def _now_elapsed(self):
        e = self._elapsed
        if not self._paused:
            e += time.monotonic() - self._clock_at
        return min(e, self._dur) if self._dur else e

    # ---------------- nombre deslizándose ----------------
    def _title_box(self):
        w, h = self.width(), self.height()
        s = self._shape
        if s == "vertical":
            return QRectF(18, h * 0.47, w - 36, 22)
        if s == "circulo":
            return QRectF(30, h * 0.40, w - 60 - 46, 22)
        if s == "ancho":
            return QRectF(24, h * 0.36, w - 24 - 100, 24)
        return QRectF(22, h * 0.36, w - 22 - 72, 22)

    def _check_marquee(self):
        fm = QFontMetricsF(self._f_title)
        over = fm.horizontalAdvance(self._title) > self._title_box().width()
        if over and self.isVisible():
            if not self._marq.isActive():
                self._marquee_last = time.monotonic()
                self._marq.start()
        else:
            self._marq.stop()
            self._marquee_x = 0.0

    def _marquee_step(self):
        now = time.monotonic()
        self._marquee_x += (now - self._marquee_last) * MARQUEE_PX_S
        self._marquee_last = now
        self.update()

    def showEvent(self, ev):
        self._check_marquee()
        self._sec.start(1000)
        super().showEvent(ev)

    def hideEvent(self, ev):
        self._marq.stop()
        self._sec.stop()
        super().hideEvent(ev)

    # ---------------- mouse ----------------
    def _hit(self, pt):
        for key, r in self._hits.items():
            if r.contains(pt):
                return key
        return None

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._press = (ev.globalPosition().toPoint(), self.pos(), self._hit(ev.position()), False)

    def mouseMoveEvent(self, ev):
        if self._press and ev.buttons() & Qt.LeftButton:
            start, wpos, key, moved = self._press
            d = ev.globalPosition().toPoint() - start
            if moved or d.manhattanLength() > 4:
                self._press = (start, wpos, key, True)
                self.move(wpos + d)   # se arrastra desde cualquier parte
            return
        hov = self._hit(ev.position())
        if hov != self._hover:
            self._hover = hov
            self.setCursor(Qt.PointingHandCursor if hov else Qt.ArrowCursor)
            self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.LeftButton or not self._press:
            return
        _, _, key, moved = self._press
        self._press = None
        if moved or key is None or key != self._hit(ev.position()):
            return
        if key == "radio":
            self.expand.emit()
        elif key == "pause":
            self.play_pause.emit()
        elif key == "next":
            self.next_.emit()
        elif key == "prev" and self._prev_enabled:
            self.prev.emit()

    def leaveEvent(self, ev):
        self._hover = None
        self.update()

    # ---------------- dibujo ----------------
    def _shape_path(self):
        r = QRectF(self.rect())
        path = QPainterPath()
        if self._shape == "circulo":
            path.addEllipse(r)
        else:
            path.addRoundedRect(r, RADIUS, RADIUS)
        return path

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        w, h = self.width(), self.height()
        if self._chroma:
            p.fillRect(self.rect(), QColor(self._chroma))
        shape = self._shape_path()
        p.save()
        p.setClipPath(shape)
        if self._art is not None:
            p.drawPixmap(0, 0, self._art)
        else:
            g = QLinearGradient(0, 0, w, h)
            g.setColorAt(0, QColor(theme.GLASS_GRAD_1))
            g.setColorAt(0.55, QColor(theme.GLASS_GRAD_3))
            g.setColorAt(1, QColor("#2A1B3D"))
            p.fillRect(self.rect(), g)
        # velo para que todo se lea (cuánto, se elige en Opciones)
        k = self._dim
        if k > 0:
            p.fillRect(self.rect(), QColor(0, 0, 0, int(70 * k)))
            g2 = QLinearGradient(0, 0, 0, h)
            g2.setColorAt(0.0, QColor(0, 0, 0, int(60 * k)))
            g2.setColorAt(0.45, QColor(0, 0, 0, int(10 * k)))
            g2.setColorAt(1.0, QColor(0, 0, 0, int(130 * k)))
            p.fillRect(self.rect(), g2)
        p.restore()

        self._hits = {}
        s = self._shape
        if s == "vertical":
            self._layout_vertical(p, w, h)
        elif s == "circulo":
            self._layout_circle(p, w, h)
        else:
            self._layout_card(p, w, h, wide=(s == "ancho"))
        p.end()

    # --- piezas ---
    def _radio(self, p, cx, cy):
        """Las barritas de "radio": tocar = volver al modo normal."""
        hov = self._hover == "radio"
        p.setPen(QPen(QColor(255, 255, 255, 255 if hov else 225), 1.8, Qt.SolidLine, Qt.RoundCap))
        for dx, hh in ((-7.5, 9), (-2.5, 16), (2.5, 11), (7.5, 5)):
            p.drawLine(QPointF(cx + dx, cy - hh / 2), QPointF(cx + dx, cy + hh / 2))
        self._hits["radio"] = QRectF(cx - 18, cy - 16, 36, 32)

    def _pause_btn(self, p, cx, cy, d):
        r = QRectF(cx - d / 2, cy - d / 2, d, d)
        hov = self._hover == "pause"
        g = QLinearGradient(0, r.top(), 0, r.bottom())
        g.setColorAt(0, QColor(255, 255, 255, 120 if hov else 95))
        g.setColorAt(1, QColor(255, 255, 255, 55 if hov else 40))
        p.setBrush(g)
        p.setPen(QPen(QColor(255, 255, 255, 150), 1))
        p.drawEllipse(r)
        icon = "play" if self._paused else "pause"
        isz = int(d * 0.42)
        pm = icons.pixmap(icon, "#FFFFFF", isz)
        p.drawPixmap(QRectF(cx - isz / 2 + (1.5 if self._paused else 0), cy - isz / 2, isz, isz), pm, QRectF(pm.rect()))
        self._hits["pause"] = r.adjusted(-4, -4, 4, 4)

    def _skip(self, p, key, cx, cy, size=15):
        enabled = key != "prev" or self._prev_enabled
        alpha = 255 if self._hover == key else (215 if enabled else 90)
        pm = icons.pixmap("next" if key == "next" else "prev", "#FFFFFF", size)
        p.setOpacity(alpha / 255)
        p.drawPixmap(QRectF(cx - size / 2, cy - size / 2, size, size), pm, QRectF(pm.rect()))
        p.setOpacity(1.0)
        self._hits[key] = QRectF(cx - 16, cy - 16, 32, 32)

    def _shadow_text(self, p, rect, align, text, color):
        """Texto con una sombrita suave: así se lee aunque la portada sea
        clara y el velo esté bajito."""
        p.setPen(QColor(0, 0, 0, 120))
        p.drawText(rect.translated(0, 1), align, text)
        p.setPen(color)
        p.drawText(rect, align, text)

    def _texts(self, p, box: QRectF, center=False):
        fm = QFontMetricsF(self._f_title)
        tw = fm.horizontalAdvance(self._title)
        p.save()
        p.setClipRect(box.adjusted(0, -4, 0, 4))
        p.setFont(self._f_title)
        white = QColor(255, 255, 255, 245)
        if tw > box.width():
            gap = 34
            loop = tw + gap
            x0 = box.left() - (self._marquee_x % loop)
            for x in (x0, x0 + loop):
                self._shadow_text(p, QRectF(x, box.top(), tw + 2, box.height()), Qt.AlignVCenter | Qt.AlignLeft,
                                  self._title, white)
        else:
            align = (Qt.AlignHCenter if center else Qt.AlignLeft) | Qt.AlignVCenter
            self._shadow_text(p, box, align, self._title, white)
        p.restore()
        p.setFont(self._f_artist)
        fa = QFontMetricsF(self._f_artist)
        artist = fa.elidedText(self._artist.upper(), Qt.ElideRight, box.width())
        ar = QRectF(box.left(), box.bottom() + 1, box.width(), 16)
        self._shadow_text(p, ar, (Qt.AlignHCenter if center else Qt.AlignLeft) | Qt.AlignVCenter, artist,
                          QColor(255, 255, 255, 200))

    def _frac(self):
        return (self._now_elapsed() / self._dur) if self._dur else 0.0

    def _line_progress(self, p, x1, x2, y):
        f = max(0.0, min(1.0, self._frac()))
        p.setPen(QPen(QColor(255, 255, 255, 80), 1))
        p.drawLine(QPointF(x1, y), QPointF(x2, y))
        mx = x1 + (x2 - x1) * f
        p.setPen(QPen(QColor(255, 255, 255, 235), 1.3))
        p.drawLine(QPointF(x1, y), QPointF(mx, y))
        p.setPen(QPen(QColor(255, 255, 255, 255), 1.6, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(mx, y - 6), QPointF(mx, y + 1))

    def _arc_progress(self, p, x1, x2, y, sag):
        path = QPainterPath(QPointF(x1, y))
        path.quadTo(QPointF((x1 + x2) / 2, y + 2 * sag), QPointF(x2, y))
        f = max(0.0, min(1.0, self._frac()))
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(255, 255, 255, 80), 1))
        p.drawPath(path)
        if f > 0.002:
            pen = QPen(QColor(255, 255, 255, 235), 1.3)
            pen.setCapStyle(Qt.FlatCap)
            L = path.length()
            pen.setDashPattern([max(0.01, L * f / 1.3), (L + 10) / 1.3])
            p.setPen(pen)
            p.drawPath(path)
        pt = path.pointAtPercent(path.percentAtLength(path.length() * f))
        ang = path.angleAtPercent(path.percentAtLength(path.length() * f))
        p.save()
        p.translate(pt)
        p.rotate(-ang)
        p.setPen(QPen(QColor(255, 255, 255), 1.6, Qt.SolidLine, Qt.RoundCap))
        p.drawLine(QPointF(0, -6), QPointF(0, 1))
        p.restore()

    # --- formas ---
    def _layout_card(self, p, w, h, wide):
        self._radio(p, 34, 32)
        box = self._title_box()
        self._texts(p, box)
        d = 48 if wide else 34
        self._pause_btn(p, w - 24 - d / 2 - (8 if wide else 0), box.center().y() + 7, d)
        y = h - 36
        self._skip(p, "prev", 36, y)
        self._skip(p, "next", w - 36, y)
        self._line_progress(p, 62, w - 62, y + 1)

    def _layout_vertical(self, p, w, h):
        self._radio(p, w / 2, 34)
        self._texts(p, self._title_box(), center=True)
        self._pause_btn(p, w / 2, h * 0.73, 40)
        y = h * 0.86
        self._skip(p, "prev", 28, y - 8, 14)
        self._skip(p, "next", w - 28, y - 8, 14)
        self._arc_progress(p, 44, w - 44, y, 9)

    def _layout_circle(self, p, w, h):
        self._radio(p, w / 2, 36)
        box = self._title_box()
        self._texts(p, box)
        self._pause_btn(p, box.right() + 26, box.center().y() + 7, 34)
        y = h * 0.66
        self._skip(p, "prev", 34, y - 6, 14)
        self._skip(p, "next", w - 34, y - 6, 14)
        self._arc_progress(p, 50, w - 50, y, 16)
