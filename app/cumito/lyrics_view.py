"""
Karaoke: la letra de lo que suena, sincronizada. La línea que va sonando
queda blanca y se va "llenando" de izquierda a derecha; la lista se desliza
sola para dejarla cerca del centro. Tocar una línea adelanta la canción ahí.

Rendimiento: todo se dibuja a mano en un solo widget (nada de un QLabel por
línea). El repintado rápido (para el llenado) solo corre mientras el karaoke
está a la vista y la música suena; el deslizamiento usa una animación corta.
"""
from __future__ import annotations

import re
import time

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QPainter
from PySide6.QtWidgets import QWidget

from . import theme

_TS = re.compile(r"\[(\d+):(\d+(?:[.:]\d+)?)\]")


def parse_lrc(text: str) -> list[tuple[float, str]]:
    """'[00:12.34] hola' -> [(12.34, 'hola')]. Una línea puede traer varios
    tiempos (coros repetidos)."""
    out = []
    for raw in (text or "").splitlines():
        stamps = _TS.findall(raw)
        if not stamps:
            continue
        words = _TS.sub("", raw).strip()
        for m, s in stamps:
            try:
                out.append((int(m) * 60 + float(s.replace(":", ".")), words))
            except ValueError:
                pass
    out.sort(key=lambda x: x[0])
    return out


class LyricsView(QWidget):
    seek = Signal(float)

    PAD_X = 22
    GAP = 14            # entre líneas
    FOLLOW_PAUSE_S = 4  # tras mover la rueda, cuánto deja de seguir sola

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self._font = QFont(theme.GLASS_FONT_FAMILY)
        self._font.setPixelSize(20)
        self._font.setBold(True)
        self._small = QFont(theme.GLASS_FONT_FAMILY)
        self._small.setPixelSize(13)
        self._small.setBold(True)
        self._lines: list[tuple[float, str]] = []
        self._plain: list[str] = []
        self._msg = "Buscando la letra…"
        self._rows = []           # [(t, [fila, fila...], y, h)]
        self._content_h = 0.0
        self._layout_w = -1
        self._base, self._stamp, self._playing = 0.0, time.monotonic(), False
        self._cur = -1
        self._offset = 0.0
        self._manual_until = 0.0
        self._hover = -1
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(420)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self._fill = QTimer(self)
        self._fill.setInterval(80)      # ~12 cuadros por segundo: suave y barato
        self._fill.timeout.connect(self._on_fill)

    # ---------- datos ----------
    def set_message(self, text):
        self._lines, self._plain, self._msg = [], [], text
        self._relayout()

    def set_lyrics(self, data: dict | None):
        data = data or {}
        self._lines = parse_lrc(data.get("synced") or "")
        self._plain = [] if self._lines else [l.strip() for l in (data.get("plain") or "").splitlines()]
        if data.get("instrumental"):
            self._msg = "♪  Instrumental  ♪"
        elif data.get("pending"):
            self._msg = "Preparando la canción…"
        elif not self._lines and not any(self._plain):
            self._msg = "No encontré la letra de esta canción"
        else:
            self._msg = ""
        self._cur = -1
        self._offset = 0.0
        self._manual_until = 0.0
        self._relayout()

    @property
    def synced(self):
        return bool(self._lines)

    def set_position(self, seconds: float, playing: bool):
        self._base, self._stamp, self._playing = float(seconds or 0), time.monotonic(), bool(playing)
        self._sync_timer()
        self._update_current(animate=True)

    def _now(self):
        return self._base + ((time.monotonic() - self._stamp) if self._playing else 0.0)

    def _sync_timer(self):
        on = self._playing and self.synced and self.isVisible()
        if on and not self._fill.isActive():
            self._fill.start()
        elif not on and self._fill.isActive():
            self._fill.stop()

    def showEvent(self, ev):
        self._sync_timer()
        super().showEvent(ev)

    def hideEvent(self, ev):
        self._fill.stop()
        super().hideEvent(ev)

    # ---------- armado de filas ----------
    def _wrap(self, text, fm, width):
        words, rows, line = text.split(), [], ""
        for w in words:
            test = f"{line} {w}".strip()
            if fm.horizontalAdvance(test) <= width or not line:
                line = test
            else:
                rows.append(line)
                line = w
        if line:
            rows.append(line)
        return rows or ["♪"]

    def _relayout(self):
        fm = QFontMetricsF(self._font)
        width = max(60, self.width() - 2 * self.PAD_X)
        lh = fm.height()
        self._layout_w = self.width()
        self._rows = []
        y = 0.0
        src = self._lines or [(None, l) for l in self._plain]
        for t, text in src:
            rows = self._wrap(text, fm, width) if text else ["♪"]
            h = lh * len(rows)
            self._rows.append((t, rows, y, h))
            y += h + self.GAP
        self._content_h = y
        self.update()

    def resizeEvent(self, ev):
        if self.width() != self._layout_w:
            self._relayout()
            self._offset = self._target_offset()
        super().resizeEvent(ev)

    # ---------- seguir la canción ----------
    def _index_at(self, t):
        idx = -1
        for i, (lt, _r, _y, _h) in enumerate(self._rows):
            if lt is not None and lt <= t + 0.15:
                idx = i
            else:
                break
        return idx

    def _target_offset(self):
        if not self._rows:
            return 0.0
        anchor = self.height() * 0.36
        i = max(0, self._cur)
        _t, _r, y, h = self._rows[i]
        top = y + h / 2 - anchor
        return max(-anchor + 20, min(top, max(0.0, self._content_h - self.height() * 0.5)))

    def _update_current(self, animate=True):
        if not self.synced:
            return
        i = self._index_at(self._now())
        if i != self._cur:
            self._cur = i
            if time.monotonic() >= self._manual_until:
                self._glide(animate)
            self.update()

    def _glide(self, animate=True):
        target = self._target_offset()
        self._anim.stop()
        if not animate or abs(target - self._offset) < 1:
            self._offset = target
            self.update()
            return
        self._anim.setStartValue(float(self._offset))
        self._anim.setEndValue(float(target))
        self._anim.start()

    def _on_anim(self, v):
        self._offset = float(v)
        self.update()

    def _on_fill(self):
        self._update_current()
        if 0 <= self._cur < len(self._rows):
            self.update()

    # ---------- dibujo ----------
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        if self._msg:
            p.setFont(self._small)
            p.setPen(QColor(242, 240, 247, 150))
            p.drawText(self.rect().adjusted(20, 0, -20, -40), Qt.AlignCenter | Qt.TextWordWrap, self._msg)
            return
        fm = QFontMetricsF(self._font)
        lh = fm.height()
        p.setFont(self._font)
        now = self._now()
        H = self.height()
        for i, (t, rows, y, h) in enumerate(self._rows):
            top = y - self._offset
            if top + h < -10 or top > H + 10:
                continue
            if not self.synced:
                alpha, cur = 225, False
            elif i == self._cur:
                alpha, cur = 120, True
            elif i < self._cur:
                alpha, cur = 95, False
            else:
                alpha, cur = 70, False
            if i == self._hover and not cur and self.synced:
                alpha = 165
            # que lo de muy arriba y muy abajo se desvanezca
            edge = min(top + h / 2, H - (top + h / 2))
            if edge < 70:
                alpha = int(alpha * max(0.0, edge) / 70)
            p.setPen(QColor(255, 255, 255, alpha))
            for k, r in enumerate(rows):
                p.drawText(QRectF(self.PAD_X, top + k * lh, self.width() - 2 * self.PAD_X, lh),
                           Qt.AlignLeft | Qt.AlignVCenter, r)
            if cur:
                # el llenado: de izquierda a derecha según avanza la línea
                nxt = self._rows[i + 1][0] if i + 1 < len(self._rows) else (t + 5)
                span = max(0.6, (nxt or t + 5) - t)
                f = max(0.0, min(1.0, (now - t) / min(span, 8.0)))
                widths = [fm.horizontalAdvance(r) for r in rows]
                left = f * sum(widths)
                p.setPen(QColor(255, 255, 255, 255))
                for k, (r, w) in enumerate(zip(rows, widths)):
                    if left <= 0:
                        break
                    fill = min(w, left)
                    left -= w
                    p.save()
                    p.setClipRect(QRectF(self.PAD_X - 2, top + k * lh, fill + 2, lh))
                    p.drawText(QRectF(self.PAD_X, top + k * lh, self.width() - 2 * self.PAD_X, lh),
                               Qt.AlignLeft | Qt.AlignVCenter, r)
                    p.restore()
        p.end()

    # ---------- mouse ----------
    def _row_at(self, y):
        for i, (_t, _r, ry, h) in enumerate(self._rows):
            top = ry - self._offset
            if top - self.GAP / 2 <= y <= top + h + self.GAP / 2:
                return i
        return -1

    def mouseMoveEvent(self, ev):
        i = self._row_at(ev.position().y())
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, ev):
        self._hover = -1
        self.update()

    def mouseReleaseEvent(self, ev):
        i = self._row_at(ev.position().y())
        if self.synced and 0 <= i < len(self._rows) and self._rows[i][0] is not None:
            self._manual_until = 0.0
            self.seek.emit(float(self._rows[i][0]))
        ev.accept()

    def mousePressEvent(self, ev):
        ev.accept()   # que no arrastre la ventana

    def wheelEvent(self, ev):
        self._anim.stop()
        self._offset -= ev.angleDelta().y() / 2.4
        self._offset = max(-self.height() * 0.4, min(self._offset, max(0.0, self._content_h - self.height() * 0.3)))
        self._manual_until = time.monotonic() + self.FOLLOW_PAUSE_S if self.synced else float("inf")
        if self.synced:
            QTimer.singleShot(int(self.FOLLOW_PAUSE_S * 1000) + 50, lambda: self._glide(True))
        self.update()
        ev.accept()
