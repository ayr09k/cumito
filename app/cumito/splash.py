"""
Splash: la pantallita de bienvenida con el logo de Cumito, unos 2 segundos
al abrir la app. Aparece suave, el logo hace un pequeño "pop", y se
desvanece; luego main.py muestra la ventana de verdad.

La imagen sale de assets/logo.svg o assets/logo.png si existen; si no, de
assets/cumito_feliz.png (la mascota). Se muestra completa, sin máscaras.
"""
from PySide6.QtCore import QEasingCurve, QParallelAnimationGroup, QPropertyAnimation, QRect, QSequentialAnimationGroup, Qt, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel, QWidget

from . import icons

IMG_W, IMG_H = 240, 318   # la imagen completa, sin recortar (es vertical)
FADE_IN_MS = 420
HOLD_MS = 1150
FADE_OUT_MS = 430


class Splash(QWidget):
    finished = Signal()

    def __init__(self):
        super().__init__()
        # Ventana transparente: solo se ve la imagen, flotando sobre el escritorio.
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(IMG_W, IMG_H)
        self.setWindowTitle("Cumito")

        self.logo = QLabel(self)
        self.logo.setScaledContents(True)
        self.logo.setStyleSheet("background:transparent;")
        pix = icons.artwork("logo", IMG_W, IMG_H)
        if pix is not None:
            self.logo.setPixmap(pix)
            # el QLabel toma exactamente la forma de la imagen, así no se deforma
            lw = int(pix.width() / pix.devicePixelRatio() + 0.5)
            lh = int(pix.height() / pix.devicePixelRatio() + 0.5)
        else:
            lw, lh = IMG_W, IMG_H
        self._logo_full = QRect((IMG_W - lw) // 2, (IMG_H - lh) // 2, lw, lh)
        sw, sh = int(lw * 0.86), int(lh * 0.86)
        self._logo_small = QRect((IMG_W - sw) // 2, (IMG_H - sh) // 2, sw, sh)
        self.logo.setGeometry(self._logo_small)

        # centrado en la pantalla
        screen = QGuiApplication.primaryScreen()
        if screen is not None:
            g = screen.availableGeometry()
            self.move(g.center().x() - IMG_W // 2, g.center().y() - IMG_H // 2)

    def start(self):
        self.setWindowOpacity(0.0)
        self.show()

        fade_in = QPropertyAnimation(self, b"windowOpacity", self)
        fade_in.setDuration(FADE_IN_MS)
        fade_in.setStartValue(0.0)
        fade_in.setEndValue(1.0)
        fade_in.setEasingCurve(QEasingCurve.OutCubic)

        pop = QPropertyAnimation(self.logo, b"geometry", self)
        pop.setDuration(FADE_IN_MS + 180)
        pop.setStartValue(self._logo_small)
        pop.setEndValue(self._logo_full)
        pop.setEasingCurve(QEasingCurve.OutBack)

        intro = QParallelAnimationGroup(self)
        intro.addAnimation(fade_in)
        intro.addAnimation(pop)

        fade_out = QPropertyAnimation(self, b"windowOpacity", self)
        fade_out.setDuration(FADE_OUT_MS)
        fade_out.setStartValue(1.0)
        fade_out.setEndValue(0.0)
        fade_out.setEasingCurve(QEasingCurve.InCubic)

        self._seq = QSequentialAnimationGroup(self)
        self._seq.addAnimation(intro)
        self._seq.addPause(HOLD_MS)
        self._seq.addAnimation(fade_out)
        self._seq.finished.connect(self._done)
        self._seq.start()

    def _done(self):
        # Primero se avisa (para que aparezca la siguiente ventana) y recién
        # después se cierra esta: si se cerrara antes, por un instante no
        # habría ninguna ventana abierta y Windows podría dar la app por
        # terminada.
        self.finished.emit()
        self.close()


def fade_in_window(widget, duration=320):
    """Muestra una ventana apareciendo suave (se usa justo después del splash)."""
    widget.setWindowOpacity(0.0)
    widget.show()
    anim = QPropertyAnimation(widget, b"windowOpacity", widget)
    anim.setDuration(duration)
    anim.setStartValue(0.0)
    anim.setEndValue(1.0)
    anim.setEasingCurve(QEasingCurve.OutCubic)
    widget._fade_in_anim = anim  # que no lo recoja el recolector de basura
    anim.start()
