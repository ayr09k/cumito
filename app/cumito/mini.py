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

import math
import sys
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (QColor, QConicalGradient, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath,
                           QPen, QPixmap, QRadialGradient, QRegion)
from PySide6.QtWidgets import QWidget

from . import icons, theme

SHAPES = {
    "cuadrado": (230, 230),
    "vertical": (230, 470),
    "ancho": (470, 230),
    "circulo": (240, 240),
    "disco": (250, 314),
}
SHAPE_NAMES = {"cuadrado": "Cuadrado", "vertical": "Vertical", "ancho": "Ancho", "circulo": "Círculo",
               "disco": "Disco"}

# --- forma "disco": un vinilo con la portada que gira, y una tarjeta de vidrio ---
DISC_D = 212            # diámetro del disco
DISC_CY = 122           # centro del disco (y)
CARD_TOP = 150          # donde empieza la tarjeta de abajo
DISC_FPS = 24           # bajito a propósito: se ve fluido y casi no gasta
DISC_DEG_S = 110.0      # velocidad de giro sonando
SPIN_UP_S = 0.7         # cuánto tarda en agarrar velocidad al dar play
SPIN_DOWN_S = 1.8       # cuánto tarda en frenar al pausar (lento, como un tocadiscos)
CARD_TINT = QColor(7, 5, 12)   # negro con ~5% de morado


def _set_blur_behind(widget, on):
    """Windows: que lo transparente de la ventana muestre lo de atrás
    desenfocado (vidrio de verdad). En otros sistemas no hace nada."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class ACCENT(ctypes.Structure):
            _fields_ = [("AccentState", ctypes.c_int), ("AccentFlags", ctypes.c_int),
                        ("GradientColor", ctypes.c_uint), ("AnimationId", ctypes.c_int)]

        class DATA(ctypes.Structure):
            _fields_ = [("Attribute", ctypes.c_int), ("Data", ctypes.POINTER(ACCENT)),
                        ("SizeOfData", ctypes.c_size_t)]

        accent = ACCENT(3 if on else 0, 0, 0, 0)        # 3 = desenfocar lo de atrás
        data = DATA(19, ctypes.pointer(accent), ctypes.sizeof(accent))   # 19 = WCA_ACCENT_POLICY
        fn = ctypes.windll.user32.SetWindowCompositionAttribute
        fn.argtypes = [wintypes.HWND, ctypes.POINTER(DATA)]
        return bool(fn(int(widget.winId()), ctypes.byref(data)))
    except Exception:
        return False
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
        self._disc = None              # el vinilo ya dibujado (cambia solo con la portada)
        self._angle = 0.0
        self._omega = 0.0              # velocidad actual (grados/s)
        self._spin_last = time.monotonic()
        self._blur_on = False
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
        self._spin = QTimer(self)
        self._spin.setInterval(int(1000 / DISC_FPS))
        self._spin.timeout.connect(self._spin_step)
        self.set_shape(shape)

    # ---------------- datos ----------------
    def set_shape(self, shape):
        self._shape = shape if shape in SHAPES else "cuadrado"
        w, h = SHAPES[self._shape]
        self.setFixedSize(w, h)
        self._f_title.setPixelSize(15 if self._shape == "ancho" else 14)
        self._rescale_art()
        self._check_marquee()
        self._apply_window_shape()
        self._update_spin()
        self.update()

    def set_dim(self, value):
        self._dim = max(0.0, min(1.0, float(value)))
        self.update()

    def set_chroma(self, color):
        self._chroma = color or ""
        self._apply_window_shape()
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
        self._update_spin()
        self.update()

    def _rescale_art(self):
        src = self._art_src
        if src is None or src.isNull():
            self._art = None
            return
        w, h = self.width(), self.height()
        scaled = src.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
        self._art = scaled.copy((scaled.width() - w) // 2, (scaled.height() - h) // 2, w, h)
        self._disc = None

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
        if s == "disco":
            return QRectF(22, CARD_TOP + 52, w - 22 - 72, 22)
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
        self._apply_window_shape()
        self._update_spin()

    def hideEvent(self, ev):
        self._marq.stop()
        self._sec.stop()
        self._spin.stop()
        super().hideEvent(ev)

    # ---------------- disco: forma de la ventana, vidrio y giro ----------------
    def _disc_rect(self):
        return QRectF((self.width() - DISC_D) / 2, DISC_CY - DISC_D / 2, DISC_D, DISC_D)

    def _card_rect(self):
        return QRectF(0, CARD_TOP, self.width(), self.height() - CARD_TOP)

    def _apply_window_shape(self):
        """En "disco" la ventana tiene la forma del disco + la tarjeta (así
        el vidrio solo aparece en la tarjeta y no en un rectángulo entero).
        Con fondo para OBS no: ahí va el color sólido alrededor."""
        disco = self._shape == "disco" and not self._chroma
        if disco:
            card = QPainterPath()
            card.addRoundedRect(self._card_rect(), 26, 26)
            reg = QRegion(self._disc_rect().toRect(), QRegion.Ellipse)
            reg = reg.united(QRegion(card.toFillPolygon().toPolygon()))
            self.setMask(reg)
        else:
            self.clearMask()
        if self.isVisible():
            if disco and not self._blur_on:
                self._blur_on = _set_blur_behind(self, True)
            elif not disco and self._blur_on:
                _set_blur_behind(self, False)
                self._blur_on = False

    def _update_spin(self):
        if self._shape == "disco" and self.isVisible() and (not self._paused or self._omega > 0.5):
            if not self._spin.isActive():
                self._spin_last = time.monotonic()
                self._spin.start()

    def _spin_step(self):
        now = time.monotonic()
        dt = min(0.2, now - self._spin_last)
        self._spin_last = now
        target = 0.0 if self._paused else DISC_DEG_S
        tau = SPIN_DOWN_S / 3 if target < self._omega else SPIN_UP_S / 3
        self._omega += (target - self._omega) * (1 - math.exp(-dt / tau))
        if self._paused and self._omega < 0.5:
            self._omega = 0.0
            self._spin.stop()
        self._angle = (self._angle + self._omega * dt) % 360
        self.update(self._disc_rect().toAlignedRect().adjusted(-2, -2, 2, 2))

    def _make_disc(self):
        """El vinilo: la portada impresa en todo el disco, con surcos encima
        y el agujerito del centro. Se dibuja una sola vez por canción."""
        d = DISC_D
        pm = QPixmap(d, d)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        circle = QPainterPath()
        circle.addEllipse(QRectF(0, 0, d, d))
        p.setClipPath(circle)
        src = self._art_src
        if src is not None and not src.isNull():
            sc = src.scaled(d, d, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            p.drawPixmap((d - sc.width()) // 2, (d - sc.height()) // 2, sc)
        else:
            g = QLinearGradient(0, 0, d, d)
            g.setColorAt(0, QColor(theme.GLASS_GRAD_1))
            g.setColorAt(1, QColor(theme.GLASS_GRAD_3))
            p.fillRect(pm.rect(), g)
        # un poco de negro de vinilo hacia el borde
        rg = QRadialGradient(d / 2, d / 2, d / 2)
        rg.setColorAt(0.0, QColor(0, 0, 0, 0))
        rg.setColorAt(0.62, QColor(0, 0, 0, 40))
        rg.setColorAt(0.97, QColor(0, 0, 0, 150))
        rg.setColorAt(1.0, QColor(0, 0, 0, 200))
        p.fillRect(pm.rect(), rg)
        # surcos
        p.setBrush(Qt.NoBrush)
        r = d / 2 - 3
        k = 0
        while r > d * 0.20:
            p.setPen(QPen(QColor(0, 0, 0, 34 if k % 2 else 18), 1))
            p.drawEllipse(QRectF(d / 2 - r, d / 2 - r, 2 * r, 2 * r))
            r -= 2.6
            k += 1
        # aro de la etiqueta y agujero
        p.setPen(QPen(QColor(255, 255, 255, 50), 1.2))
        lr = d * 0.19
        p.drawEllipse(QRectF(d / 2 - lr, d / 2 - lr, 2 * lr, 2 * lr))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(18, 16, 22))
        p.drawEllipse(QRectF(d / 2 - 7, d / 2 - 7, 14, 14))
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawEllipse(QRectF(d / 2 - 2.5, d / 2 - 2.5, 5, 5))
        p.end()
        self._disc = pm

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
        elif key in ("pause", "disc"):
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
        if self._shape == "disco":
            return self._paint_disco()
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

    def _paint_disco(self):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        w, h = self.width(), self.height()
        if self._chroma:
            p.fillRect(self.rect(), QColor(self._chroma))
        if self._disc is None:
            self._make_disc()
        dr = self._disc_rect()
        card = self._card_rect()
        # el disco: solo la parte de arriba (lo demás queda "metido" en la tarjeta)
        p.save()
        p.setClipRect(QRectF(0, 0, w, card.top() + 12))
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 70))
        p.drawEllipse(dr.adjusted(2, 4, 2, 4))      # sombrita
        p.translate(dr.center())
        p.rotate(self._angle)
        p.drawPixmap(QPointF(-DISC_D / 2, -DISC_D / 2), self._disc)
        p.resetTransform()
        # brillo fijo (no gira): así se nota que es un disco brillante
        cg = QConicalGradient(dr.center(), 35)
        for pos, a in ((0.0, 0), (0.07, 46), (0.15, 0), (0.5, 0), (0.57, 34), (0.65, 0), (1.0, 0)):
            cg.setColorAt(pos, QColor(255, 255, 255, a))
        ring = QPainterPath()
        ring.addEllipse(dr)
        inner = QPainterPath()
        ri = DISC_D * 0.2
        inner.addEllipse(dr.center(), ri, ri)
        p.fillPath(ring.subtracted(inner), cg)
        p.restore()

        # la tarjeta: vidrio oscuro (negro con 5% de morado), deja ver lo de atrás
        cpath = QPainterPath()
        cpath.addRoundedRect(card, 26, 26)
        tint = QColor(CARD_TINT)
        tint.setAlpha(150 if self._blur_on else 228)
        p.fillPath(cpath, tint)
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawPath(cpath)
        p.setPen(QPen(QColor(255, 255, 255, 70), 1))
        p.drawLine(QPointF(card.left() + 26, card.top() + 0.5), QPointF(card.right() - 26, card.top() + 0.5))

        self._hits = {"disc": QRectF(dr.left() + 30, dr.top() + 10, DISC_D - 60, card.top() - dr.top() - 14)}
        self._radio(p, 34, card.top() + 30)
        box = self._title_box()
        self._texts(p, box)
        self._pause_btn(p, w - 24 - 17, box.center().y() + 7, 34)
        y = h - 32
        self._skip(p, "prev", 36, y)
        self._skip(p, "next", w - 36, y)
        self._line_progress(p, 62, w - 62, y + 1)
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
