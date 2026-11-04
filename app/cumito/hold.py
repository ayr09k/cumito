"""
Botones "mantén presionado" para todo lo que borra o apaga.

La idea (para todo Cumito): lo peligroso no se hace con un toque. Hay que
mantener el botón presionado 2 segundos: mientras tanto, un borde rojo le da
la vuelta como un reloj (empieza arriba al centro, sigue por la derecha,
abajo, la izquierda y vuelve al inicio) y el botón tiembla cada vez más,
como si fuera a explotar. Si se suelta antes, el borde se devuelve y no pasa
nada. Un toque corto solo avisa "Mantén presionado".

- HoldButton: el botón en sí.
- HoldConfirm: el aviso a pantalla completa ("¿Seguro que quieres borrar
  TODO?") con el HoldButton adentro y un "Cancelar".
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QEasingCurve, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import icons, theme

HOLD_MS = 2000
RED = QColor("#FF5A5F")


def _clockwise_from_top(r: QRectF, rad: float) -> QPainterPath:
    """Contorno redondeado que arranca arriba al centro y va en el sentido
    del reloj, para que el borde rojo "dé la vuelta" desde ahí."""
    rad = min(rad, r.height() / 2, r.width() / 2)
    l, t, rt, b = r.left(), r.top(), r.right(), r.bottom()
    p = QPainterPath(QPointF(r.center().x(), t))
    p.lineTo(rt - rad, t)
    p.arcTo(QRectF(rt - 2 * rad, t, 2 * rad, 2 * rad), 90, -90)
    p.lineTo(rt, b - rad)
    p.arcTo(QRectF(rt - 2 * rad, b - 2 * rad, 2 * rad, 2 * rad), 0, -90)
    p.lineTo(l + rad, b)
    p.arcTo(QRectF(l, b - 2 * rad, 2 * rad, 2 * rad), 270, -90)
    p.lineTo(l, t + rad)
    p.arcTo(QRectF(l, t, 2 * rad, 2 * rad), 180, -90)
    p.lineTo(r.center().x(), t)
    return p


class HoldButton(QWidget):
    confirmed = Signal()

    MARGIN = 5   # espacio para que el temblor no se corte

    def __init__(self, text, hold_ms=HOLD_MS, height=40, radius=None, font_size=12.5,
                 strong=True, parent=None):
        super().__init__(parent)
        self._text = text
        self._hint = None
        self._hold_ms = hold_ms
        self._radius = radius
        self._strong = strong          # fondo rojizo (borrar) o neutro (No gracias)
        self.hold_required = True      # False: funciona como un botón normal
        self._p = 0.0
        self._pressed = False
        self._done_flash = 0.0
        self._t0 = time.monotonic()
        self.setFixedHeight(height + 2 * self.MARGIN)
        from PySide6.QtWidgets import QSizePolicy
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self._font = QFont(theme.GLASS_FONT_FAMILY)
        self._font.setPixelSize(int(font_size))
        self._font.setBold(True)

        self._anim = QVariantAnimation(self)
        self._anim.valueChanged.connect(self._on_progress)
        self._anim.finished.connect(self._on_anim_done)
        self._shake = QTimer(self)
        self._shake.setInterval(16)
        self._shake.timeout.connect(self.update)
        self._hint_timer = QTimer(self)
        self._hint_timer.setSingleShot(True)
        self._hint_timer.timeout.connect(self._clear_hint)

    def sizeHint(self):
        from PySide6.QtGui import QFontMetrics
        from PySide6.QtCore import QSize
        w = QFontMetrics(self._font).horizontalAdvance(self._text or "") + 44 + 2 * self.MARGIN
        return QSize(w, self.height())

    # ---- API ----
    def setText(self, text):
        self._text = text
        self.update()

    def text(self):
        return self._text

    def reset(self):
        self._anim.stop()
        self._shake.stop()
        self._pressed = False
        self._p = 0.0
        self._done_flash = 0.0
        self.update()

    # ---- mouse ----
    def mousePressEvent(self, ev):
        if ev.button() != Qt.LeftButton or not self.isEnabled():
            return
        self._pressed = True
        self._press_at = time.monotonic()
        if not self.hold_required:
            return
        self._run_to(1.0, int(self._hold_ms * (1 - self._p)), QEasingCurve.Linear)
        self._shake.start()

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.LeftButton or not self._pressed:
            return
        self._pressed = False
        if not self.hold_required:
            if self.rect().contains(ev.position().toPoint()):
                self.confirmed.emit()
            return
        if self._p >= 1.0:
            return
        quick = time.monotonic() - self._press_at < 0.35
        # se soltó antes: el borde se devuelve
        self._run_to(0.0, 260, QEasingCurve.OutCubic)
        if quick:
            self._hint = "Mantén presionado"
            self._hint_timer.start(1300)
            self._nudge_until = time.monotonic() + 0.35
            self._shake.start()

    def _clear_hint(self):
        self._hint = None
        if not self._pressed:
            self._shake.stop()
        self.update()

    def _run_to(self, target, ms, curve):
        self._anim.stop()
        self._anim.setStartValue(float(self._p))
        self._anim.setEndValue(float(target))
        self._anim.setDuration(max(1, ms))
        self._anim.setEasingCurve(curve)
        self._anim.start()

    def _on_progress(self, v):
        self._p = float(v)
        self.update()

    def _on_anim_done(self):
        if self._p >= 1.0 and self._pressed:
            # ¡boom! un destello y se confirma
            self._shake.stop()
            self._pressed = False
            flash = QVariantAnimation(self)
            flash.setStartValue(1.0)
            flash.setEndValue(0.0)
            flash.setDuration(380)
            flash.valueChanged.connect(lambda v: (setattr(self, "_done_flash", float(v)), self.update()))
            flash.finished.connect(self.reset)
            self._flash_anim = flash
            flash.start()
            QTimer.singleShot(140, self.confirmed.emit)
        elif self._p <= 0.0 and not self._hint:
            self._shake.stop()

    # ---- dibujo ----
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        m = self.MARGIN
        r = QRectF(self.rect()).adjusted(m, m, -m, -m)
        rad = self._radius if self._radius is not None else r.height() / 2

        # temblor: más fuerte mientras más cerca de completarse
        t = time.monotonic() - self._t0
        amp = 0.0
        if self._pressed and self.hold_required:
            amp = 0.35 + 3.4 * (self._p ** 2)
        elif getattr(self, "_nudge_until", 0) > time.monotonic():
            amp = 1.4
        if amp:
            p.translate(amp * math.sin(t * 61.0), amp * 0.6 * math.cos(t * 47.0))
            p.rotate(amp * 0.25 * math.sin(t * 39.0))

        hover = self.underMouse()
        if self._strong:
            base = QColor(228, 91, 91, 46 if not hover else 62)
        else:
            base = QColor(255, 255, 255, 23 if not hover else 38)
        # se va poniendo más rojo mientras se mantiene
        fill = QColor(
            int(base.red() + (228 - base.red()) * self._p),
            int(base.green() + (70 - base.green()) * self._p),
            int(base.blue() + (75 - base.blue()) * self._p),
            int(base.alpha() + (110 - base.alpha()) * self._p),
        )
        shape = QPainterPath()
        shape.addRoundedRect(r, rad, rad)
        p.fillPath(shape, fill)
        p.setPen(QPen(QColor(255, 120, 120, 90) if self._strong else QColor(255, 255, 255, 50), 1))
        p.drawPath(shape)

        # el borde rojo que da la vuelta
        if self._p > 0.002:
            pw = 2.6
            path = _clockwise_from_top(r, rad)
            length = path.length()
            pen = QPen(RED, pw)
            pen.setCapStyle(Qt.FlatCap)
            pen.setDashPattern([max(0.01, length * self._p / pw), (length + 20) / pw])
            p.setPen(pen)
            p.drawPath(path)

        if self._done_flash > 0:
            p.fillPath(shape, QColor(255, 255, 255, int(150 * self._done_flash)))

        p.setFont(self._font)
        p.setPen(QColor("#FFFFFF") if (self._strong or self._p > 0.2) else QColor(theme.GLASS_TEXT))
        p.drawText(r, Qt.AlignCenter, self._hint or self._text)
        p.end()


class HoldConfirm(QWidget):
    """El aviso "¿Seguro?" a pantalla completa, con su botón de mantener."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setGeometry(parent.rect())
        self.hide()
        self._on_confirm = None
        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(0.0)
        self.setGraphicsEffect(self._fx)

        self.card = QWidget(self)
        self.card.setObjectName("holdcard")
        self.card.setAttribute(Qt.WA_StyledBackground, True)
        self.card.setStyleSheet(
            "QWidget#holdcard { background: rgba(26,24,34,0.97); border: 1px solid rgba(255,110,110,0.35);"
            " border-radius: 22px; }"
        )
        lay = QVBoxLayout(self.card)
        lay.setContentsMargins(20, 22, 20, 14)
        lay.setSpacing(8)
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignCenter)
        self.icon.setStyleSheet("background:transparent;")
        lay.addWidget(self.icon)
        self.title = QLabel("")
        self.title.setAlignment(Qt.AlignCenter)
        self.title.setWordWrap(True)
        self.title.setStyleSheet("color:#fff; font-size:17px; font-weight:800; background:transparent;")
        lay.addWidget(self.title)
        self.msg = QLabel("")
        self.msg.setAlignment(Qt.AlignCenter)
        self.msg.setWordWrap(True)
        self.msg.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE}; font-size:12px; background:transparent;")
        lay.addWidget(self.msg)
        lay.addSpacing(8)
        self.hold = HoldButton("Mantén presionado", height=44)
        self.hold.confirmed.connect(self._confirmed)
        lay.addWidget(self.hold)
        self.cancel = QPushButton("Cancelar")
        self.cancel.setCursor(Qt.PointingHandCursor)
        self.cancel.setFixedHeight(34)
        self.cancel.setStyleSheet(
            f"QPushButton {{ background:transparent; border:none; color:{theme.GLASS_TEXT_MUTE};"
            " font-size:12.5px; font-weight:700; border-radius:17px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.08); color:#fff; }"
        )
        self.cancel.clicked.connect(self.close_confirm)
        lay.addWidget(self.cancel)

    def ask(self, title, message, button_text, icon_name, on_confirm):
        self._on_confirm = on_confirm
        self.title.setText(title)
        self.msg.setText(message)
        self.hold.reset()
        self.hold.setText(button_text)
        self.icon.setPixmap(icons.pixmap(icon_name, "#FF6B70", 30))
        pw = self.parentWidget()
        self.setGeometry(pw.rect())
        cw = pw.width() - 40
        self.card.setFixedWidth(cw)
        self.card.adjustSize()
        ch = self.card.sizeHint().height()
        end_y = (pw.height() - ch) // 2
        self.show()
        self.raise_()
        a = QVariantAnimation(self)
        a.setDuration(260)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.valueChanged.connect(lambda v: (self._fx.setOpacity(float(v)),
                                          self.card.move(20, int(end_y + 26 * (1 - float(v))))))
        self._anim = a
        a.start()

    def close_confirm(self):
        a = QVariantAnimation(self)
        a.setDuration(180)
        a.setStartValue(self._fx.opacity())
        a.setEndValue(0.0)
        a.valueChanged.connect(lambda v: self._fx.setOpacity(float(v)))
        a.finished.connect(self.hide)
        self._anim = a
        a.start()

    def _confirmed(self):
        cb, self._on_confirm = self._on_confirm, None
        self.close_confirm()
        if cb:
            cb()

    def mousePressEvent(self, ev):
        # tocar fuera de la tarjeta = cancelar
        if not self.card.geometry().contains(ev.position().toPoint()):
            self.close_confirm()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(0, 0, 0, 150))
        p.end()
