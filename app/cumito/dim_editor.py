"""
Ajuste de la oscuridad del mini (Opciones -> Apariencia -> Oscuridad del
mini): una barrita para dejarla a gusto, con una vista previa del mini que
cambia mientras se mueve.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import theme
from .mini import MiniWindow
from .wheel import LILAC, tick

PREVIEW_BOX = (230, 210)


class Slider(QWidget):
    """Barrita: se arrastra, se toca en cualquier punto o se mueve con la
    rueda del mouse (de a 5%, con el mismo "tic" de la rueda de opciones)."""
    valueChanged = Signal(float)

    def __init__(self, value=0.15, parent=None):
        super().__init__(parent)
        self._v = float(value)
        self._drag = False
        self.setFixedHeight(34)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

    def value(self):
        return self._v

    def setValue(self, v, emit=False):
        v = max(0.0, min(1.0, float(v)))
        if abs(v - self._v) < 1e-4:
            return
        if round(v * 20) != round(self._v * 20):
            tick()  # un "tic" cada 5%
        self._v = v
        self.update()
        if emit:
            self.valueChanged.emit(v)

    def _track(self):
        return QRectF(12, self.height() / 2 - 3, self.width() - 24, 6)

    def _from_x(self, x):
        t = self._track()
        return (x - t.left()) / max(1.0, t.width())

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag = True
            self.setValue(self._from_x(ev.position().x()), emit=True)

    def mouseMoveEvent(self, ev):
        if self._drag:
            self.setValue(self._from_x(ev.position().x()), emit=True)

    def mouseReleaseEvent(self, ev):
        self._drag = False

    def wheelEvent(self, ev):
        step = 0.05 if ev.angleDelta().y() > 0 else -0.05
        self.setValue(round((self._v + step) * 20) / 20, emit=True)
        ev.accept()

    def keyPressEvent(self, ev):
        if ev.key() in (Qt.Key_Right, Qt.Key_Up):
            self.setValue(round((self._v + 0.05) * 20) / 20, emit=True)
        elif ev.key() in (Qt.Key_Left, Qt.Key_Down):
            self.setValue(round((self._v - 0.05) * 20) / 20, emit=True)
        else:
            super().keyPressEvent(ev)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        t = self._track()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 40))
        p.drawRoundedRect(t, 3, 3)
        filled = QRectF(t.left(), t.top(), t.width() * self._v, t.height())
        p.setBrush(LILAC)
        p.drawRoundedRect(filled, 3, 3)
        cx = t.left() + t.width() * self._v
        cy = t.center().y()
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawEllipse(QRectF(cx - 10, cy - 9, 20, 20))
        p.setBrush(QColor("#FFFFFF"))
        p.drawEllipse(QRectF(cx - 10, cy - 10, 20, 20))
        p.end()


class DimEditor(QWidget):
    changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 10)
        lay.setSpacing(10)
        lay.addStretch(1)
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setFixedHeight(PREVIEW_BOX[1])
        lay.addWidget(self.preview)
        cap = QLabel("Así se verá el mini")
        cap.setAlignment(Qt.AlignCenter)
        cap.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE2}; font-size:10.5px;")
        lay.addWidget(cap)
        lay.addSpacing(10)
        row = QHBoxLayout()
        lbl = QLabel("Oscuridad")
        lbl.setStyleSheet(f"color:{theme.GLASS_TEXT}; font-size:12.5px; font-weight:700;")
        row.addWidget(lbl)
        row.addStretch()
        self.pct = QLabel("15%")
        self.pct.setStyleSheet(f"color:{LILAC.name()}; font-size:15px; font-weight:800;")
        row.addWidget(self.pct)
        row.setContentsMargins(12, 0, 12, 0)
        lay.addLayout(row)
        self.slider = Slider()
        self.slider.valueChanged.connect(self._on_value)
        lay.addWidget(self.slider)
        ends = QHBoxLayout()
        ends.setContentsMargins(12, 0, 12, 0)
        a = QLabel("Más clara")
        b = QLabel("Más oscura")
        for w in (a, b):
            w.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE2}; font-size:10px;")
        ends.addWidget(a)
        ends.addStretch()
        ends.addWidget(b)
        lay.addLayout(ends)
        lay.addStretch(2)
        self._mini = None   # un mini de mentira, solo para dibujar la vista previa
        self._redraw = QTimer(self)
        self._redraw.setSingleShot(True)
        self._redraw.setInterval(16)
        self._redraw.timeout.connect(self._render)

    def open(self, value, shape, chroma, art, title, artist):
        if self._mini is None:
            self._mini = MiniWindow(shape, "")
        self._mini.set_shape(shape)
        self._mini.set_art(art)
        self._mini.set_track(title, artist)
        self._mini.set_progress(40, 200, False)
        self._chroma = chroma
        self.slider.setValue(value)
        self._show_pct(value)
        self._mini.set_dim(value)
        self._render()
        self.slider.setFocus()

    def _show_pct(self, v):
        self.pct.setText(f"{round(v * 100)}%")

    def _on_value(self, v):
        self._show_pct(v)
        if self._mini is not None:
            self._mini.set_dim(v)
            self._redraw.start()
        self.changed.emit(v)

    def _render(self):
        if self._mini is None:
            return
        pm = self._mini.grab()
        bw, bh = PREVIEW_BOX
        pm = pm.scaled(bw, bh, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.preview.setPixmap(pm)
