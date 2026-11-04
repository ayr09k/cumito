"""
Instalar Cumito -- el instalador, con el mismo estilo de la app.

Tres pasos:
  1. Dónde instalar (por defecto Documentos\\Cumito).
  2. Instalando: barra de progreso real + lo que va haciendo.
  3. ¡Listo!: acceso directo en el escritorio (marcado) y Abrir / Cerrar.

La app viene metida adentro de este mismo .exe (payload/cumito_app.zip):
no hace falta internet ni nada más para instalar.
"""
from __future__ import annotations

import sys
import tempfile
import traceback
from pathlib import Path

from PySide6.QtCore import QByteArray, QEasingCurve, QPropertyAnimation, QRectF, QSize, QStandardPaths, Qt, QThread, QTimer, Signal
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QColor, QFont, QIcon, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QFileDialog, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit,
    QPlainTextEdit, QPushButton, QStackedWidget, QVBoxLayout, QWidget,
)

import install_core as core

BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
ASSETS = BASE / "assets"
W, H = 440, 470

ACCENT = "#8E6CF2"
TEXT = "#F2F0F7"
MUTE = "rgba(242,240,247,0.62)"
MUTE2 = "rgba(242,240,247,0.42)"
BORDER = "rgba(255,255,255,0.20)"
FONT = "Segoe UI"


def _svg_pixmap(path: Path, size: int, color="#ffffff") -> QPixmap:
    """Dibuja un ícono SVG (de los de la app) al tamaño y color pedidos."""
    app = QApplication.instance()
    dpr = app.primaryScreen().devicePixelRatio() if app and app.primaryScreen() else 1.0
    pix = QPixmap(int(size * dpr), int(size * dpr))
    pix.fill(Qt.transparent)
    try:
        svg = path.read_text(encoding="utf-8").replace("currentColor", color)
        r = QSvgRenderer(QByteArray(svg.encode("utf-8")))
        p = QPainter(pix)
        p.setRenderHint(QPainter.Antialiasing, True)
        r.render(p)
        p.end()
    except Exception:
        pass
    pix.setDevicePixelRatio(dpr)
    return pix


def _check_png() -> str:
    """La palomita de la casilla, guardada como PNG temporal (así no depende
    de ningún complemento extra de Windows para leer SVG)."""
    out = Path(tempfile.gettempdir()) / "cumito_instalador_check.png"
    pix = _svg_pixmap(BASE / "check.svg", 16)
    pix.setDevicePixelRatio(1.0)
    pix.save(str(out), "PNG")
    return out.as_posix()


def _btn(text, primary=False, height=40):
    b = QPushButton(text)
    b.setCursor(Qt.PointingHandCursor)
    b.setFixedHeight(height)
    if primary:
        b.setStyleSheet(
            f"QPushButton {{ background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 #9A7BF5, stop:1 {ACCENT});"
            f" color: white; border: none; border-radius: {height // 2}px; font-size: 13px; font-weight: 800; padding: 0 22px; }}"
            "QPushButton:hover { background: #A68AF7; }"
            "QPushButton:disabled { background: rgba(142,108,242,0.35); color: rgba(255,255,255,0.6); }"
        )
    else:
        b.setStyleSheet(
            f"QPushButton {{ background: rgba(255,255,255,0.09); border: 1px solid {BORDER};"
            f" border-radius: {height // 2}px; color: {TEXT}; font-size: 12.5px; font-weight: 700; padding: 0 18px; }}"
            "QPushButton:hover { background: rgba(255,255,255,0.16); }"
        )
    return b


def _label(text, size=12, color=TEXT, weight=400, center=False):
    l = QLabel(text)
    l.setWordWrap(True)
    l.setStyleSheet(f"color:{color}; font-size:{size}px; font-weight:{weight}; background:transparent;")
    if center:
        l.setAlignment(Qt.AlignCenter)
    return l


def _mascot(height):
    l = QLabel()
    l.setAlignment(Qt.AlignCenter)
    l.setStyleSheet("background:transparent;")
    pix = QPixmap(str(ASSETS / "cumito_feliz.png"))
    if not pix.isNull():
        app = QApplication.instance()
        dpr = app.primaryScreen().devicePixelRatio() if app and app.primaryScreen() else 1.0
        pix = pix.scaledToHeight(int(height * dpr), Qt.SmoothTransformation)
        pix.setDevicePixelRatio(dpr)
        l.setPixmap(pix)
    l.setFixedHeight(height)
    return l


class _Progress(QWidget):
    """Barra de progreso redondeada, que avanza suave hacia el valor real."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(10)
        self._target = 0.0
        self._shown = 0.0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._step)

    def set_value(self, f):
        self._target = max(0.0, min(1.0, f))
        if not self._timer.isActive():
            self._timer.start(16)

    def _step(self):
        self._shown += (self._target - self._shown) * 0.18
        if abs(self._target - self._shown) < 0.001:
            self._shown = self._target
            self._timer.stop()
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = self.height() / 2
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 30))
        p.drawRoundedRect(QRectF(0, 0, self.width(), self.height()), r, r)
        w = self.width() * self._shown
        if w > 1:
            g = QLinearGradient(0, 0, self.width(), 0)
            g.setColorAt(0, QColor("#4FB4D8"))
            g.setColorAt(1, QColor(ACCENT))
            p.setBrush(g)
            p.drawRoundedRect(QRectF(0, 0, max(w, self.height()), self.height()), r, r)
        p.end()


class _Worker(QThread):
    progress = Signal(float)
    log = Signal(str)
    finished_ok = Signal(bool, str)

    def __init__(self, target: Path):
        super().__init__()
        self.target = target

    def run(self):
        try:
            self.log.emit(f"Instalando en {self.target}")
            self.log.emit("Cerrando Cumito si estaba abierto…")
            core.close_running_app()
            if self.target.exists():
                core.remove_previous(self.target, self.log.emit)
            self.log.emit("Copiando los archivos de Cumito…")
            n = core.extract(core.payload_path(), self.target, lambda f: self.progress.emit(f * 0.96), self.log.emit)
            self.log.emit(f"{n} archivos copiados.")
            self.log.emit("Agregando Cumito al menú Inicio…")
            core.create_shortcut(core.start_menu_dir() / "Cumito.lnk", self.target / core.APP_EXE)
            self.progress.emit(1.0)
            self.log.emit("¡Listo!")
            self.finished_ok.emit(True, "")
        except PermissionError:
            self.finished_ok.emit(False, "No tengo permiso para escribir en esa carpeta. "
                                         "Prueba con otra (por ejemplo, Documentos).")
        except Exception as e:
            self.log.emit(traceback.format_exc())
            self.finished_ok.emit(False, f"No se pudo terminar la instalación: {e}")


class Installer(QWidget):
    def __init__(self, update_target: Path | None = None):
        """update_target: modo actualización (lo usa la propia app): instala
        directo en esa carpeta, sin preguntar nada, y vuelve a abrir Cumito."""
        super().__init__()
        self.update_mode = update_target is not None
        self.setWindowTitle("Instalar Cumito")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window | Qt.WindowMinimizeButtonHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(W, H)
        self.setFont(QFont(FONT, 10))
        self._drag = None
        self._installing = False

        docs = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation) or str(Path.home() / "Documents")
        self.target = update_target or (Path(docs) / "Cumito")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 14, 24, 22)
        outer.setSpacing(0)

        top = QHBoxLayout()
        top.addStretch()
        self.btn_close = QPushButton("")
        self.btn_close.setFixedSize(28, 28)
        self.btn_close.setIcon(QIcon(_svg_pixmap(ASSETS / "icons" / "close.svg", 14, "#C9C6D2")))
        self.btn_close.setIconSize(QSize(14, 14))
        self.btn_close.setCursor(Qt.PointingHandCursor)
        self.btn_close.setStyleSheet(
            "QPushButton { background: transparent; border: none; color: rgba(255,255,255,0.6); font-size: 13px; border-radius: 14px; }"
            "QPushButton:hover { background: rgba(228,91,91,0.35); color: white; }"
            "QPushButton:disabled { color: rgba(255,255,255,0.15); }"
        )
        self.btn_close.clicked.connect(self.close)
        top.addWidget(self.btn_close)
        outer.addLayout(top)

        self.stack = QStackedWidget()
        self.stack.setStyleSheet("background: transparent;")
        outer.addWidget(self.stack, 1)
        self.stack.addWidget(self._page_where())
        self.stack.addWidget(self._page_installing())
        self.stack.addWidget(self._page_done())
        self.stack.addWidget(self._page_error())
        if self.update_mode:
            self.install_title.setText("Actualizando Cumito…")
            QTimer.singleShot(1500, self._start)  # que Cumito termine de cerrarse

    # ---------- fondo: tarjeta oscura con brillo morado (como la app) ----------
    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, W - 1, H - 1), 22, 22)
        g = QLinearGradient(0, 0, 0, H)
        g.setColorAt(0.0, QColor("#221f2b"))
        g.setColorAt(1.0, QColor("#0e0d12"))
        p.fillPath(path, g)
        glow = QRadialGradient(W * 0.5, H * 0.18, W * 0.75)
        glow.setColorAt(0, QColor(142, 108, 242, 85))
        glow.setColorAt(1, QColor(142, 108, 242, 0))
        p.fillPath(path, glow)
        glow2 = QRadialGradient(W * 0.85, H * 0.95, W * 0.6)
        glow2.setColorAt(0, QColor(79, 180, 216, 45))
        glow2.setColorAt(1, QColor(79, 180, 216, 0))
        p.fillPath(path, glow2)
        p.setPen(QPen(QColor(255, 255, 255, 30), 1))
        p.drawPath(path)
        p.end()

    # ---------- páginas ----------
    def _page_where(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(_mascot(120))
        lay.addSpacing(4)
        lay.addWidget(_label("Instalar Cumito", 22, "#ffffff", 800, center=True))
        lay.addWidget(_label("La app de música de tu grupo de Discord.", 12, MUTE, center=True))
        lay.addStretch()
        lay.addWidget(_label("Se instalará en:", 11.5, MUTE, 700))
        row = QHBoxLayout()
        row.setSpacing(8)
        self.path_field = QLineEdit(str(self.target))
        self.path_field.setReadOnly(True)
        self.path_field.setFixedHeight(38)
        self.path_field.setCursorPosition(0)
        self.path_field.setStyleSheet(
            f"QLineEdit {{ background: rgba(255,255,255,0.07); border: 1px solid {BORDER}; border-radius: 10px;"
            f" padding: 0 10px; color: {TEXT}; font-size: 11.5px; }}"
        )
        row.addWidget(self.path_field, 1)
        change = _btn("Cambiar…", height=38)
        change.clicked.connect(self._choose_folder)
        row.addWidget(change)
        lay.addLayout(row)
        lay.addSpacing(14)
        self.btn_install = _btn("Instalar", primary=True, height=44)
        self.btn_install.clicked.connect(self._start)
        lay.addWidget(self.btn_install)
        return page

    def _page_installing(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(_mascot(84))
        self.install_title = _label("Instalando Cumito…", 19, "#ffffff", 800, center=True)
        lay.addWidget(self.install_title)
        lay.addSpacing(6)
        prow = QHBoxLayout()
        self.progress = _Progress()
        prow.addWidget(self.progress, 1)
        self.percent = _label("0%", 11.5, MUTE, 700)
        self.percent.setFixedWidth(40)
        self.percent.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        prow.addWidget(self.percent)
        lay.addLayout(prow)
        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        self.logbox.setMaximumBlockCount(400)
        self.logbox.setFont(QFont("Consolas", 9))
        self.logbox.setStyleSheet(
            f"QPlainTextEdit {{ background: rgba(0,0,0,0.28); border: 1px solid rgba(255,255,255,0.10);"
            f" border-radius: 12px; padding: 8px; color: {MUTE}; }}"
            "QScrollBar:vertical { background: transparent; width: 8px; margin: 4px 1px; }"
            "QScrollBar::handle:vertical { background: rgba(255,255,255,0.26); border-radius: 3px; min-height: 30px; margin: 0 1px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; border: none; background: none; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }"
        )
        lay.addWidget(self.logbox, 1)
        return page

    def _page_done(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        lay.addWidget(_mascot(130))
        lay.addWidget(_label("¡Cumito está listo!", 22, "#ffffff", 800, center=True))
        self.done_path = _label("", 11, MUTE2, center=True)
        lay.addWidget(self.done_path)
        lay.addStretch()
        check_icon = _check_png()
        self.chk_desktop = QCheckBox("Crear acceso directo en el escritorio")
        self.chk_desktop.setChecked(True)
        self.chk_desktop.setCursor(Qt.PointingHandCursor)
        self.chk_desktop.setStyleSheet(
            f"QCheckBox {{ color: {TEXT}; font-size: 12.5px; spacing: 10px; background: transparent; }}"
            "QCheckBox::indicator { width: 20px; height: 20px; border-radius: 6px;"
            f" border: 1px solid rgba(255,255,255,0.35); background: rgba(255,255,255,0.06); }}"
            f"QCheckBox::indicator:checked {{ background: {ACCENT}; border: 1px solid {ACCENT}; image: url({check_icon}); }}"
        )
        crow = QHBoxLayout()
        crow.addStretch()
        crow.addWidget(self.chk_desktop)
        crow.addStretch()
        lay.addLayout(crow)
        lay.addSpacing(14)
        brow = QHBoxLayout()
        brow.setSpacing(10)
        close = _btn("Cerrar", height=44)
        close.clicked.connect(lambda: self._finish(open_app=False))
        brow.addWidget(close, 1)
        open_btn = _btn("Abrir Cumito", primary=True, height=44)
        open_btn.clicked.connect(lambda: self._finish(open_app=True))
        brow.addWidget(open_btn, 2)
        lay.addLayout(brow)
        return page

    def _page_error(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        lay.addWidget(_mascot(100))
        lay.addWidget(_label("Algo salió mal", 20, "#ffffff", 800, center=True))
        self.error_msg = _label("", 12, MUTE, center=True)
        lay.addWidget(self.error_msg)
        lay.addStretch()
        brow = QHBoxLayout()
        brow.setSpacing(10)
        back = _btn("Probar otra carpeta", height=42)
        back.clicked.connect(lambda: self._go(0))
        brow.addWidget(back, 1)
        close = _btn("Cerrar", height=42)
        close.clicked.connect(self.close)
        brow.addWidget(close, 1)
        lay.addLayout(brow)
        return page

    # ---------- cambio de página con un fundido ----------
    def _go(self, index):
        self.stack.setCurrentIndex(index)
        eff = QGraphicsOpacityEffect(self.stack.currentWidget())
        self.stack.currentWidget().setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(260)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.OutCubic)
        w = self.stack.currentWidget()
        anim.finished.connect(lambda: w.setGraphicsEffect(None))
        self._page_anim = anim
        anim.start()

    # ---------- acciones ----------
    def _choose_folder(self):
        start = str(self.target.parent)
        chosen = QFileDialog.getExistingDirectory(self, "¿Dónde instalar Cumito?", start)
        if chosen:
            p = Path(chosen)
            self.target = p if p.name.lower() == "cumito" else p / "Cumito"
            self.path_field.setText(str(self.target))
            self.path_field.setCursorPosition(0)

    def _start(self):
        self._installing = True
        self.btn_close.setEnabled(False)
        self.logbox.clear()
        self._go(1)
        self.worker = _Worker(self.target)
        self.worker.progress.connect(self._on_progress)
        self.worker.log.connect(self.logbox.appendPlainText)
        self.worker.finished_ok.connect(self._on_done)
        self.worker.start()

    def _on_progress(self, f):
        self.progress.set_value(f)
        self.percent.setText(f"{int(f * 100)}%")

    def _on_done(self, ok, message):
        self._installing = False
        self.btn_close.setEnabled(True)
        if ok and self.update_mode:
            # actualización: sin preguntas, se abre Cumito ya actualizado
            self.install_title.setText("¡Listo! Abriendo Cumito…")
            QTimer.singleShot(700, lambda: self._finish(open_app=True, shortcut=False))
            return
        if ok:
            self.done_path.setText(f"Instalado en {self.target}")
            QTimer.singleShot(450, lambda: self._go(2))  # que se alcance a ver el 100%
        else:
            self.error_msg.setText(message)
            self._go(3)

    def _finish(self, open_app, shortcut=True):
        exe = self.target / core.APP_EXE
        if shortcut and self.chk_desktop.isChecked():
            desktop = QStandardPaths.writableLocation(QStandardPaths.DesktopLocation) or str(Path.home() / "Desktop")
            core.create_shortcut(Path(desktop) / "Cumito.lnk", exe)
        if open_app:
            try:
                core.launch(exe)
            except Exception:
                pass
        self.close()

    def closeEvent(self, ev):
        if self._installing:
            ev.ignore()  # no dejar a medias
            return
        super().closeEvent(ev)

    # ---------- arrastrar la ventana ----------
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, ev):
        if self._drag is not None and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag)

    def mouseReleaseEvent(self, ev):
        self._drag = None


def main():
    app = QApplication(sys.argv)
    icon = QIcon(str(ASSETS / "cumito.ico"))
    app.setWindowIcon(icon)
    update_target = None
    if "--actualizar" in sys.argv:
        i = sys.argv.index("--actualizar")
        if i + 1 < len(sys.argv) and sys.argv[i + 1].strip():
            update_target = Path(sys.argv[i + 1])
    if not core.payload_path().exists():
        # solo pasa si alguien corre el instalador sin haberlo construido bien
        w = Installer()
        w.error_msg.setText("Este instalador está incompleto (le falta la app adentro). "
                            "Vuelve a crearlo con CREAR_CUMITO.bat.")
        w.stack.setCurrentIndex(3)
    else:
        w = Installer(update_target)
    w.setWindowIcon(icon)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
