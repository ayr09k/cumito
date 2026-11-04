"""
La rueda de Opciones (como el selector de un iPhone, pero en curva).

Las opciones están colocadas sobre un arco a la derecha: la elegida queda en
el centro, más grande y con su cuadrito lila; las demás se van achicando,
apagando y corriendo hacia el borde a medida que se alejan. Con la rueda del
mouse (o arrastrando) se pasa de una a otra y cada paso suena un "tic"
cortito. Tocar la elegida la activa; tocar otra la trae al centro.
"""
from __future__ import annotations

import math
import struct
import tempfile
import time
import wave
from pathlib import Path

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from . import icons, theme

LILAC = QColor("#C9B4F8")
BOX = QColor(44, 43, 50)
STEP_PX = 50          # distancia vertical entre opciones (en el centro del arco)
RADIUS = 300          # radio del arco


# ---------------------------------------------------------------- sonido
class _Tick:
    """El "tic" de cada paso. Se genera una sola vez (unos milisegundos de
    sonido) y se reproduce con lo que ya trae Windows; en otro sistema,
    simplemente no suena."""

    def __init__(self):
        self._path = None
        self._last = 0.0
        try:
            import winsound  # solo existe en Windows
            self._ws = winsound
        except ImportError:
            self._ws = None
            return
        try:
            path = Path(tempfile.gettempdir()) / "cumito_tic.wav"
            if not path.exists():
                rate, n = 44100, int(44100 * 0.012)
                frames = bytearray()
                for i in range(n):
                    t = i / rate
                    env = math.exp(-t * 520)
                    v = 0.32 * env * (0.75 * math.sin(2 * math.pi * 2900 * t) + 0.25 * math.sin(2 * math.pi * 5100 * t))
                    frames += struct.pack("<h", int(max(-1, min(1, v)) * 32767))
                with wave.open(str(path), "wb") as w:
                    w.setnchannels(1)
                    w.setsampwidth(2)
                    w.setframerate(rate)
                    w.writeframes(bytes(frames))
            self._path = str(path)
        except Exception:
            self._path = None

    def play(self):
        if not self._ws or not self._path:
            return
        now = time.monotonic()
        if now - self._last < 0.028:  # si gira muy rápido, que no se amontonen
            return
        self._last = now
        try:
            self._ws.PlaySound(self._path, self._ws.SND_FILENAME | self._ws.SND_ASYNC | self._ws.SND_NODEFAULT)
        except Exception:
            pass


_tick = None


def tick():
    global _tick
    if _tick is None:
        _tick = _Tick()
    _tick.play()


# ---------------------------------------------------------------- rueda
class OptionWheel(QWidget):
    activated = Signal(str)      # la clave de la opción tocada estando al centro

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._items = []             # [{"key","label","icon","danger"}]
        self._pos = 0.0              # posición actual (puede ir "entre" opciones)
        self._target = 0
        self._last_tick_idx = 0
        self._wheel_acc = 0
        self._drag = None            # (y inicial, pos inicial, movió?)
        self._hit = []               # (rect, índice) de lo dibujado
        self._hover = None
        self._anim = QVariantAnimation(self)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._set_pos)
        self._f_sel = QFont(theme.GLASS_FONT_FAMILY)
        self._f_sel.setPixelSize(15)
        self._f_sel.setBold(True)
        self._f_norm = QFont(theme.GLASS_FONT_FAMILY)
        self._f_norm.setPixelSize(12)
        self._f_norm.setWeight(QFont.DemiBold)

    # ---- API ----
    def set_items(self, items, keep_key=None):
        self._items = list(items)
        idx = 0
        for i, it in enumerate(self._items):
            if it["key"] == keep_key:
                idx = i
        self._anim.stop()
        self._target = idx
        self._pos = float(idx)
        self._last_tick_idx = idx
        self.update()

    def current_key(self):
        if not self._items:
            return None
        return self._items[max(0, min(len(self._items) - 1, round(self._pos)))]["key"]

    def go(self, idx):
        if not self._items:
            return
        idx = max(0, min(len(self._items) - 1, idx))
        self._target = idx
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(float(idx))
        self._anim.setDuration(int(180 + 70 * min(4, abs(idx - self._pos))))
        self._anim.start()

    # ---- movimiento + "tic" ----
    def _set_pos(self, v):
        self._pos = float(v)
        i = round(self._pos)
        if i != self._last_tick_idx:
            self._last_tick_idx = i
            tick()
        self.update()

    def wheelEvent(self, ev):
        self._wheel_acc += ev.angleDelta().y()
        steps = 0
        while self._wheel_acc >= 120:
            self._wheel_acc -= 120
            steps -= 1
        while self._wheel_acc <= -120:
            self._wheel_acc += 120
            steps += 1
        if steps:
            self.go(self._target + steps)
        ev.accept()

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Down, Qt.Key_S):
            self.go(self._target + 1)
        elif ev.key() in (Qt.Key_Up, Qt.Key_W):
            self.go(self._target - 1)
        elif ev.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            k = self.current_key()
            if k:
                self.activated.emit(k)
        else:
            super().keyPressEvent(ev)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._anim.stop()
            self._drag = [ev.position().y(), self._pos, False]

    def mouseMoveEvent(self, ev):
        if self._drag is not None and ev.buttons() & Qt.LeftButton:
            dy = ev.position().y() - self._drag[0]
            if abs(dy) > 4:
                self._drag[2] = True
            if self._drag[2] and self._items:
                p = self._drag[1] - dy / STEP_PX
                p = max(-0.35, min(len(self._items) - 0.65, p))  # un poquito de "elástico" en las puntas
                self._set_pos(p)
            return
        hov = self._index_at(ev.position())
        if hov != self._hover:
            self._hover = hov
            self.setCursor(Qt.PointingHandCursor if hov is not None else Qt.ArrowCursor)
            self.update()

    def mouseReleaseEvent(self, ev):
        if ev.button() != Qt.LeftButton or self._drag is None:
            return
        moved = self._drag[2]
        self._drag = None
        if moved:
            self.go(round(self._pos))
            return
        i = self._index_at(ev.position())
        if i is None:
            return
        if i == round(self._pos):
            self.activated.emit(self._items[i]["key"])
        else:
            self.go(i)

    def leaveEvent(self, ev):
        self._hover = None
        self.update()

    def _index_at(self, pt):
        for rect, i in self._hit:
            if rect.contains(pt):
                return i
        return None

    # ---- dibujo ----
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        w, h = self.width(), self.height()
        cy = h / 2
        arc_x = w - 74                    # dónde pasa el arco a la altura del centro
        cx = arc_x + RADIUS               # centro del círculo (fuera, a la derecha)
        step = math.asin(STEP_PX / RADIUS)

        # el arco: una línea fina que se desvanece arriba y abajo
        g = QLinearGradient(0, 0, 0, h)
        g.setColorAt(0.0, QColor(255, 255, 255, 0))
        g.setColorAt(0.3, QColor(255, 255, 255, 70))
        g.setColorAt(0.5, QColor(255, 255, 255, 95))
        g.setColorAt(0.7, QColor(255, 255, 255, 70))
        g.setColorAt(1.0, QColor(255, 255, 255, 0))
        pen = QPen(g, 1.2)
        p.setPen(pen)
        span = math.asin(min(1.0, (h / 2) / RADIUS))
        path = QPainterPath()
        for k in range(61):
            th = -span + 2 * span * k / 60
            pt = QPointF(cx - RADIUS * math.cos(th), cy + RADIUS * math.sin(th))
            path.moveTo(pt) if k == 0 else path.lineTo(pt)
        p.drawPath(path)

        # la marquita lila sobre el arco, a la altura de la elegida
        p.setPen(Qt.NoPen)
        p.setBrush(LILAC)
        p.drawRoundedRect(QRectF(arc_x - 7, cy - 3.5, 14, 7), 3.5, 3.5)

        self._hit = []
        sel = round(self._pos)
        for i, it in enumerate(self._items):
            d = i - self._pos
            if abs(d) > 4.6:
                continue
            th = d * step
            if abs(th) >= math.pi / 2:
                continue
            ax = cx - RADIUS * math.cos(th)
            ay = cy + RADIUS * math.sin(th)
            near = max(0.0, 1.0 - abs(d))           # 1 justo en el centro
            fade = max(0.0, 1.0 - 0.2 * abs(d))
            box = 30 + 10 * near
            gap = 40 + 14 * near                     # separación del arco
            bx = ax - gap - box / 2
            rect = QRectF(bx - box / 2, ay - box / 2, box, box)

            hov = self._hover == i
            # cuadrito del ícono
            if near > 0.01:
                col = QColor(
                    int(BOX.red() + (LILAC.red() - BOX.red()) * near),
                    int(BOX.green() + (LILAC.green() - BOX.green()) * near),
                    int(BOX.blue() + (LILAC.blue() - BOX.blue()) * near),
                )
            else:
                col = QColor(BOX).lighter(118 if hov else 100)
            col.setAlphaF(fade)
            p.setPen(Qt.NoPen)
            p.setBrush(col)
            p.drawRoundedRect(rect, 9 + 3 * near, 9 + 3 * near)
            danger = it.get("danger")
            ic_col = "#18171C" if near > 0.5 else ("#FF8A8A" if danger else "#F2F0F7")
            isz = int(15 + 4 * near)
            pm = icons.pixmap(it["icon"], ic_col, isz)
            p.setOpacity(fade)
            p.drawPixmap(QRectF(rect.center().x() - isz / 2, rect.center().y() - isz / 2, isz, isz), pm,
                         QRectF(pm.rect()))
            p.setOpacity(1.0)

            # texto a la izquierda del cuadrito
            f = self._f_sel if near > 0.5 else self._f_norm
            p.setFont(f)
            if near > 0.5:
                tc = QColor("#FFFFFF")
            else:
                tc = QColor(255, 140, 140) if danger else QColor(170, 168, 178)
                if hov:
                    tc = tc.lighter(125)
            tc.setAlphaF(max(0.0, min(1.0, fade)))
            p.setPen(tc)
            fm = QFontMetricsF(f)
            label = it["label"]
            tw = fm.horizontalAdvance(label)
            tx = rect.left() - 14 - tw
            text_rect = QRectF(tx, ay - 12, tw + 2, 24)
            p.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, label)
            if it.get("hint") and near > 0.5:
                p.setFont(self._f_norm)
                hc = QColor(LILAC)
                hc.setAlphaF(0.85)
                p.setPen(hc)
                hw = QFontMetricsF(self._f_norm).horizontalAdvance(it["hint"])
                p.drawText(QRectF(rect.left() - 14 - hw, ay + 9, hw + 2, 18), Qt.AlignLeft | Qt.AlignVCenter,
                           it["hint"])
            self._hit.append((QRectF(min(tx, rect.left()) - 6, ay - STEP_PX / 2 + 2,
                                     rect.right() - min(tx, rect.left()) + 12, STEP_PX - 4), i))
        p.end()
