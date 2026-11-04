"""
ConnectScreen: la bienvenida de la primera vez que se abre Cumito. Como el
servidor ya viene puesto de fábrica (config.DEFAULT_SERVER), solo pregunta
el nombre. El campo de dirección solo aparece si no hay servidor de
fábrica. Una vez que se guarda, no se vuelve a mostrar.
"""
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from . import icons, theme
from .config import DEFAULT_SERVER

W, H = 320, 300


class ConnectScreen(QWidget):
    connected = Signal(str, str)  # (direccion, nombre)

    def __init__(self, default_address="", default_name="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Cumito")
        self.setFixedSize(W, H)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Window)
        self.setStyleSheet(f"""
            QWidget {{ background: {theme.FLAT_PANEL_BG}; }}
            QLabel {{ color: {theme.GLASS_TEXT}; background: transparent; }}
            QLineEdit {{
                background: rgba(255,255,255,0.08); border: 1px solid {theme.GLASS_BORDER};
                border-radius: 8px; padding: 8px 10px; color: {theme.GLASS_TEXT}; font-size: 12px;
            }}
            QPushButton#go {{
                background: {theme.GLASS_ACCENT}; color: white; border: none;
                border-radius: 8px; padding: 10px; font-weight: 700; font-size: 12px;
            }}
        """)
        self._drag_pos = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 14, 26, 26)
        lay.setSpacing(10)

        close_row = QHBoxLayout()
        close_row.addStretch()
        close_btn = QPushButton("")
        close_btn.setFixedSize(24, 24)
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setIcon(icons.icon("close", "#A9A6B2", 14))
        close_btn.setIconSize(QSize(14, 14))
        close_btn.setStyleSheet(
            "QPushButton { background: transparent; border:none; color:#999; font-size:11px; border-radius:11px; }"
            "QPushButton:hover { background: rgba(255,255,255,0.12); color:#fff; }"
        )
        close_btn.clicked.connect(lambda: QApplication.instance().quit())
        close_row.addWidget(close_btn)
        lay.addLayout(close_row)

        title = QLabel("Cumito")
        title.setFont(QFont(theme.GLASS_FONT_FAMILY, 20, QFont.Bold))
        lay.addWidget(title)

        ask_address = not DEFAULT_SERVER
        subtitle = QLabel(
            "Conéctate al servidor de música de tu grupo." if ask_address
            else "¿Cómo quieres que te vean en el grupo?"
        )
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE}; font-size:11px;")
        lay.addWidget(subtitle)
        lay.addSpacing(8)

        address_label = QLabel("Dirección del servidor")
        self.address_edit = QLineEdit(default_address or DEFAULT_SERVER)
        self.address_edit.setPlaceholderText("ej. 123.45.67.89:8765")
        self.address_edit.returnPressed.connect(self._submit)
        lay.addWidget(address_label)
        lay.addWidget(self.address_edit)
        address_label.setVisible(ask_address)
        self.address_edit.setVisible(ask_address)

        lay.addWidget(QLabel("Tu nombre"))
        self.name_edit = QLineEdit(default_name)
        self.name_edit.setPlaceholderText("¿Cómo te mostramos?")
        self.name_edit.returnPressed.connect(self._submit)
        lay.addWidget(self.name_edit)

        lay.addSpacing(6)
        btn = QPushButton("Entrar" if not ask_address else "Conectar")
        btn.setObjectName("go")
        btn.setCursor(Qt.PointingHandCursor)
        btn.clicked.connect(self._submit)
        lay.addWidget(btn)

        self.error_label = QLabel("")
        self.error_label.setStyleSheet(f"color:{theme.GLASS_DANGER}; font-size:10.5px;")
        self.error_label.setWordWrap(True)
        lay.addWidget(self.error_label)
        lay.addStretch()

        (self.address_edit if ask_address else self.name_edit).setFocus()

    def _submit(self):
        address = self.address_edit.text().strip()
        name = self.name_edit.text().strip() or "Pana"
        if ":" not in address or address.startswith(":") or address.endswith(":"):
            self.error_label.setText("Falta la dirección completa, con :puerto (ej. 123.45.67.89:8765).")
            return
        self.error_label.setText("")
        self.connected.emit(address, name)

    # Sin barra de título propia -- se arrastra agarrando de cualquier
    # parte vacía de la tarjeta.
    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self._drag_pos = ev.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, ev):
        if self._drag_pos is not None and ev.buttons() & Qt.LeftButton:
            self.move(ev.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, ev):
        self._drag_pos = None
