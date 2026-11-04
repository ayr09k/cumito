"""
Piezas animadas chicas de Cumito:

- Spinner: el circulito girando de "preparando...".
- HopLoader: Cumito saltando (2 saltos a la izquierda, gira, 2 a la
  derecha, gira, y así) mientras se busca.
- stagger_fade_in: hace aparecer una lista de widgets uno por uno.

Rendimiento: cada animación tiene su propio reloj que SOLO corre mientras
el widget está visible. Escondido, no gasta nada.
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPen, QTransform
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

from . import icons, theme

FRAME_MS = 16  # ~60 fps, solo mientras se ve


class _Animated(QWidget):
    """Base: un reloj que corre solo mientras el widget está visible."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._t0 = time.monotonic()
        self._clock = QTimer(self)
        self._clock.timeout.connect(self.update)

    def showEvent(self, ev):
        self._t0 = time.monotonic()
        self._clock.start(FRAME_MS)
        super().showEvent(ev)

    def hideEvent(self, ev):
        self._clock.stop()
        super().hideEvent(ev)

    def elapsed_ms(self):
        return (time.monotonic() - self._t0) * 1000


class Spinner(_Animated):
    def __init__(self, size=20, color=None, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._color = QColor(color or theme.GLASS_ACCENT)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        w = self.width()
        pen_w = max(2.0, w / 9)
        rect = QRectF(pen_w, pen_w, w - 2 * pen_w, w - 2 * pen_w)
        # aro de fondo tenue
        bg = QColor(self._color)
        bg.setAlpha(55)
        p.setPen(QPen(bg, pen_w))
        p.drawEllipse(rect)
        # arco que gira (y "respira" de largo, se ve más vivo)
        t = self.elapsed_ms()
        start = -(t * 0.36) % 360
        span = 70 + 80 * (0.5 + 0.5 * math.sin(t / 380))
        pen = QPen(self._color, pen_w)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawArc(rect, int(start * 16), int(span * 16))
        p.end()


class HopLoader(_Animated):
    """Cumito saltando: 2 saltos a la izquierda, gira, 2 a la derecha, gira."""

    HOP_MS = 380
    TURN_MS = 240
    STEP_PX = 16
    HEIGHT_PX = 20

    def __init__(self, width=170, height=120, img_h=66, parent=None):
        super().__init__(parent)
        self.setFixedSize(width, height)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._img_h = img_h
        pix = icons.artwork("cumito_feliz", img_h * 2, img_h)
        self._pix = pix

    def _pose(self, t):
        """(desplazamiento x, altura y, escala horizontal) en el instante t."""
        H, T, S = self.HOP_MS, self.TURN_MS, self.STEP_PX
        cycle = 4 * H + 2 * T
        t %= cycle

        def hop(i, direction, start_x):
            u = (t - i) / H
            return start_x + direction * S * u, math.sin(math.pi * u) * self.HEIGHT_PX

        # empieza a la derecha (+S) mirando a la izquierda
        if t < H:
            x, y = hop(0, -1, S); sx = 1
        elif t < 2 * H:
            x, y = hop(H, -1, 0); sx = 1
        elif t < 2 * H + T:
            u = (t - 2 * H) / T
            x, y, sx = -S, 0, math.cos(math.pi * u)          # gira: 1 -> -1
        elif t < 3 * H + T:
            x, y = hop(2 * H + T, 1, -S); sx = -1
        elif t < 4 * H + T:
            x, y = hop(3 * H + T, 1, 0); sx = -1
        else:
            u = (t - 4 * H - T) / T
            x, y, sx = S, 0, -math.cos(math.pi * u)          # gira: -1 -> 1
        return x, y, sx

    def paintEvent(self, ev):
        if self._pix is None or self._pix.isNull():
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        x, y, sx = self._pose(self.elapsed_ms())
        dpr = self._pix.devicePixelRatio() or 1
        pw, ph = self._pix.width() / dpr, self._pix.height() / dpr
        ground = self.height() - 12
        cx = self.width() / 2 + x

        # sombrita: se achica cuando está en el aire
        k = 1 - (y / self.HEIGHT_PX) * 0.45
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, int(70 * k)))
        p.drawEllipse(QRectF(cx - 22 * k, ground - 4, 44 * k, 8))

        # el pequeño "aplastón" al tocar el piso le da vida al salto
        squash = 1.0
        if y < 3:
            squash = 0.94
        sx = sx if abs(sx) > 0.06 else (0.06 if sx >= 0 else -0.06)
        p.save()
        p.translate(cx, ground - y)
        p.setTransform(QTransform().scale(sx, squash), True)
        p.drawPixmap(QRectF(-pw / 2, -ph, pw, ph), self._pix, QRectF(0, 0, self._pix.width(), self._pix.height()))
        p.restore()
        p.end()


def stagger_fade_in(owner, widgets, step_ms=70, duration=240):
    """Hace aparecer `widgets` uno por uno (para los resultados del
    buscador). El efecto de transparencia se quita al terminar."""
    anims = getattr(owner, "_stagger_anims", [])
    for i, w in enumerate(widgets):
        eff = QGraphicsOpacityEffect(w)
        eff.setOpacity(0.0)
        w.setGraphicsEffect(eff)

        def start(w=w, eff=eff):
            try:
                anim = QPropertyAnimation(eff, b"opacity", owner)
            except RuntimeError:
                return  # el widget ya no existe (se hizo otra búsqueda)
            anim.setDuration(duration)
            anim.setStartValue(0.0)
            anim.setEndValue(1.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)

            def done():
                try:
                    w.setGraphicsEffect(None)
                except RuntimeError:
                    pass
                if anim in anims:
                    anims.remove(anim)

            anim.finished.connect(done)
            anims.append(anim)
            anim.start()

        QTimer.singleShot(i * step_ms, start)
    owner._stagger_anims = anims
