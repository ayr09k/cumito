"""
Íconos de Cumito: archivos SVG en assets/icons/ (todos con viewBox 24x24).
Para cambiar un ícono, basta con reemplazar su archivo -- mientras use
"currentColor" para el color, aquí se pinta del color que toque.

También carga las ilustraciones grandes (logo, Cumito feliz) desde
assets/, con un PNG de respaldo si el SVG todavía no existe.

Se dibujan una sola vez por tamaño/color y se guardan en memoria, así que
no cuestan nada después de la primera vez.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

ASSETS = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "assets"
ICONS_DIR = ASSETS / "icons"

_svg_cache: dict[str, str] = {}
_pix_cache: dict[tuple, QPixmap] = {}


def _dpr() -> float:
    app = QGuiApplication.instance()
    screen = app.primaryScreen() if app else None
    return screen.devicePixelRatio() if screen else 1.0


def _render_svg(svg_text: str, w: int, h: int) -> QPixmap:
    dpr = _dpr()
    pix = QPixmap(int(w * dpr), int(h * dpr))
    pix.fill(Qt.transparent)
    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    # respeta la proporción del dibujo, centrado
    vb = renderer.viewBoxF()
    if vb.width() > 0 and vb.height() > 0:
        scale = min(pix.width() / vb.width(), pix.height() / vb.height())
        tw, th = vb.width() * scale, vb.height() * scale
        target = QRectF((pix.width() - tw) / 2, (pix.height() - th) / 2, tw, th)
    else:
        target = QRectF(0, 0, pix.width(), pix.height())
    renderer.render(p, target)
    p.end()
    pix.setDevicePixelRatio(dpr)
    return pix


def pixmap(name: str, color: str = "#F2F0F7", size: int = 18) -> QPixmap:
    """Un ícono de assets/icons/<name>.svg, del color y tamaño pedidos."""
    key = ("icon", name, color, size)
    if key in _pix_cache:
        return _pix_cache[key]
    if name not in _svg_cache:
        try:
            _svg_cache[name] = (ICONS_DIR / f"{name}.svg").read_text(encoding="utf-8")
        except Exception:
            _svg_cache[name] = ""
    svg = _svg_cache[name].replace("currentColor", color)
    pix = _render_svg(svg, size, size) if svg else QPixmap()
    _pix_cache[key] = pix
    return pix


def icon(name: str, color: str = "#F2F0F7", size: int = 18) -> QIcon:
    return QIcon(pixmap(name, color, size))


def artwork(base_name: str, width: int, height: int | None = None) -> QPixmap | None:
    """Ilustración grande, completa (sin recortes ni máscaras), ajustada
    para caber en width x height manteniendo su forma.

    Busca, en orden: assets/<base_name>.svg, assets/<base_name>.png,
    y por último assets/cumito_feliz.png (la mascota)."""
    height = height or width
    key = ("art", base_name, width, height)
    if key in _pix_cache:
        return _pix_cache[key]
    pix = None
    svg_path = ASSETS / f"{base_name}.svg"
    if svg_path.exists():
        try:
            pix = _render_svg(svg_path.read_text(encoding="utf-8"), width, height)
        except Exception:
            pix = None
    if pix is None or pix.isNull():
        for candidate in (ASSETS / f"{base_name}.png", ASSETS / "cumito_feliz.png"):
            if candidate.exists():
                raw = QPixmap(str(candidate))
                if not raw.isNull():
                    dpr = _dpr()
                    pix = raw.scaled(int(width * dpr), int(height * dpr),
                                     Qt.KeepAspectRatio, Qt.SmoothTransformation)
                    pix.setDevicePixelRatio(dpr)
                    break
    _pix_cache[key] = pix
    return pix
