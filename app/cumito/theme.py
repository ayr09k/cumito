"""Colores y medidas del diseño "glass" de Cumito -- esta vez sin ninguna
paleta vieja arrastrada: este proyecto solo tiene esta pantalla."""

GLASS_WINDOW_W, GLASS_WINDOW_H = 360, 600
GLASS_WINDOW_RADIUS = 28

GLASS_ACCENT = "#8E6CF2"
GLASS_ACCENT_SOFT = "rgba(142,108,242,0.35)"
GLASS_GRAD_1 = "#8E6CF2"   # morado
GLASS_GRAD_2 = "#4FB4D8"   # celeste
GLASS_GRAD_3 = "#D1517A"   # rosado

GLASS_TEXT = "#F2F0F7"
GLASS_TEXT_MUTE = "rgba(242,240,247,0.6)"
GLASS_TEXT_MUTE2 = "rgba(242,240,247,0.4)"
GLASS_DANGER = "#E45B5B"

GLASS_CHROME_BG = "rgba(255,255,255,0.14)"
GLASS_CHROME_BG_HOVER = "rgba(255,255,255,0.24)"
GLASS_PANEL_BG = "rgba(24,24,32,0.78)"
GLASS_BORDER = "rgba(255,255,255,0.2)"
FLAT_CHROME_BG = "#232330"
FLAT_PANEL_BG = "#17171F"

GLASS_FONT_FAMILY = "Segoe UI"


def load_fonts(app=None):
    """Manrope (la letra del diseño 2.0) si viene en assets/fonts; si no,
    Segoe UI. Se llama una vez, antes de armar las ventanas."""
    global GLASS_FONT_FAMILY
    import sys
    from pathlib import Path
    from PySide6.QtGui import QFont, QFontDatabase
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "assets" / "fonts"
    fams = set()
    for f in sorted(base.glob("*.ttf")) if base.exists() else []:
        fid = QFontDatabase.addApplicationFont(str(f))
        if fid >= 0:
            fams.update(QFontDatabase.applicationFontFamilies(fid))
    if "Manrope" in fams:
        GLASS_FONT_FAMILY = "Manrope"
    if app is not None:
        f = QFont(GLASS_FONT_FAMILY)
        f.setPixelSize(12)
        f.setHintingPreference(QFont.PreferNoHinting)
        app.setFont(f)
    return GLASS_FONT_FAMILY
