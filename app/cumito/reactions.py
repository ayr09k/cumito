"""
Reacciones: una barrita de emojis para reaccionar a lo que suena. Cuando
alguien del grupo reacciona, a todos les sube su emoji flotando por la
portada (con su nombre), y se desvanece.

Cada emoji flotante es un QLabel que vive ~2 s: no hay nada corriendo
cuando nadie reacciona.
"""
from __future__ import annotations

import random

from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

EMOJIS = ["🔥", "💜", "😂", "🕺", "👏", "😭"]
EMOJI_FONT = "Segoe UI Emoji"


class ReactionBar(QWidget):
    """Píldora de vidrio con los emojis (aparece sobre los controles)."""

    picked = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("rbar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("#rbar { background: rgba(20,18,28,0.92); border:1px solid rgba(255,255,255,0.22);"
                           " border-radius: 22px; }")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(2)
        f = QFont(EMOJI_FONT)
        f.setPixelSize(20)
        for e in EMOJIS:
            b = QPushButton(e)
            b.setFont(f)
            b.setCursor(Qt.PointingHandCursor)
            b.setFixedSize(36, 36)
            b.setStyleSheet("QPushButton { background: transparent; border:none; border-radius:18px; }"
                            "QPushButton:hover { background: rgba(255,255,255,0.14); }"
                            "QPushButton:pressed { background: rgba(255,255,255,0.06); }")
            b.clicked.connect(lambda _=False, e=e: (self.picked.emit(e), self.hide()))
            lay.addWidget(b)
        self.adjustSize()
        self.hide()

    def toggle_at(self, x_center, y_bottom):
        if self.isVisible():
            self.hide()
            return
        self.adjustSize()
        pw = self.parentWidget()
        x = max(8, min(pw.width() - self.width() - 8, x_center - self.width() // 2))
        self.move(x, y_bottom - self.height())
        self.show()
        self.raise_()


def float_reaction(parent: QWidget, emoji: str, who: str, x: int | None = None, y: int | None = None):
    """Sube un emoji flotando con el nombre de quien reaccionó."""
    box = QWidget(parent)
    box.setAttribute(Qt.WA_TransparentForMouseEvents)
    v = QVBoxLayout(box)
    v.setContentsMargins(0, 0, 0, 0)
    v.setSpacing(0)
    e = QLabel(emoji)
    f = QFont(EMOJI_FONT)
    f.setPixelSize(34)
    e.setFont(f)
    e.setAlignment(Qt.AlignCenter)
    e.setStyleSheet("background: transparent;")
    n = QLabel((who or "")[:14])
    n.setAlignment(Qt.AlignCenter)
    n.setStyleSheet("color:#fff; font-size:10px; font-weight:800; background: rgba(0,0,0,0.38);"
                    " border-radius: 7px; padding: 1px 6px;")
    v.addWidget(e, 0, Qt.AlignHCenter)
    v.addWidget(n, 0, Qt.AlignHCenter)
    box.adjustSize()
    W, H = parent.width(), parent.height()
    x0 = x if x is not None else random.randint(int(W * 0.18), int(W * 0.82))
    y0 = y if y is not None else int(H * 0.62)
    start = QPoint(x0 - box.width() // 2, y0)
    end = QPoint(start.x() + random.randint(-36, 36), y0 - random.randint(150, 220))
    box.move(start)
    box.show()
    box.raise_()
    fx = QGraphicsOpacityEffect(box)
    box.setGraphicsEffect(fx)
    group = QParallelAnimationGroup(box)
    mv = QPropertyAnimation(box, b"pos")
    mv.setDuration(2000)
    mv.setStartValue(start)
    mv.setEndValue(end)
    mv.setEasingCurve(QEasingCurve.OutCubic)
    op = QPropertyAnimation(fx, b"opacity")
    op.setDuration(2000)
    op.setKeyValueAt(0.0, 0.0)
    op.setKeyValueAt(0.12, 1.0)
    op.setKeyValueAt(0.65, 1.0)
    op.setKeyValueAt(1.0, 0.0)
    group.addAnimation(mv)
    group.addAnimation(op)
    group.finished.connect(box.deleteLater)
    group.start()
    return box
