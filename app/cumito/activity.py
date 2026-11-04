"""
Actividad de Cumito: quién hizo qué.

- Ticker: en la esquina de arriba, donde dice "Cumito", aparece por 4
  segundos lo último que pasó ("Juan agregó 1 canción: Título - Artista"),
  deslizándose si no cabe, y luego vuelve a decir "Cumito".
- ActivityFeed: la pantalla de Ajustes > Actividad, estilo chat: cada
  persona con su burbujita de color, la hora, y la portada de la canción.
"""
from __future__ import annotations

import math
import time
import zlib

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QTimer, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QFontMetrics, QFontMetricsF, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import QGraphicsOpacityEffect, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import icons, theme

AVATAR_COLORS = ["#8E6CF2", "#4FB4D8", "#D1517A", "#3DBE7A", "#E39A3B", "#5A8CF2", "#C46BD8", "#E0675A"]
BOT_NAME = "Cumito"
TICKER_MS = 4000


def color_for(name: str) -> str:
    return AVATAR_COLORS[zlib.crc32((name or "?").lower().encode("utf-8")) % len(AVATAR_COLORS)]


def sentence(a: dict) -> tuple[str, str]:
    """(quién, el resto) -> "Juan", "agregó 1 canción: Título - Artista"."""
    rest = a.get("text") or ""
    if a.get("title"):
        rest += f": {a['title']}"
        if a.get("sub"):
            rest += f" - {a['sub']}"
    return a.get("who") or "Alguien", rest


def clock(ts: float) -> str:
    t = time.localtime(ts)
    h = t.tm_hour % 12 or 12
    return f"{h}:{t.tm_min:02d} {'a. m.' if t.tm_hour < 12 else 'p. m.'}"


_MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def day_label(ts: float) -> str:
    d = time.localtime(ts)
    today = time.localtime()
    yday = time.localtime(time.time() - 86400)
    if (d.tm_year, d.tm_yday) == (today.tm_year, today.tm_yday):
        return "Hoy"
    if (d.tm_year, d.tm_yday) == (yday.tm_year, yday.tm_yday):
        return "Ayer"
    return f"{d.tm_mday} {_MESES[d.tm_mon - 1]}"


def _round_pix(pix: QPixmap, size: int, radius: float) -> QPixmap:
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    p.setClipPath(path)
    scaled = pix.scaled(size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    p.drawPixmap((size - scaled.width()) // 2, (size - scaled.height()) // 2, scaled)
    p.end()
    return out


_bot_avatar_cache = {}


def avatar(name: str, size: int = 30) -> QPixmap:
    """Circulito con la inicial (o la carita de Cumito para lo que hace el bot)."""
    if name == BOT_NAME:
        if size not in _bot_avatar_cache:
            out = QPixmap(size, size)
            out.fill(Qt.transparent)
            p = QPainter(out)
            p.setRenderHint(QPainter.Antialiasing, True)
            p.setBrush(QColor(theme.GLASS_ACCENT))
            p.setPen(Qt.NoPen)
            p.drawEllipse(QRectF(0, 0, size, size))
            face = QPixmap(str(icons.ASSETS / "cumito_feliz.png"))
            if not face.isNull():
                f = face.scaled(int(size * 0.86), int(size * 0.86), Qt.KeepAspectRatio, Qt.SmoothTransformation)
                p.drawPixmap((size - f.width()) // 2, (size - f.height()) // 2 + 1, f)
            p.end()
            _bot_avatar_cache[size] = out
        return _bot_avatar_cache[size]
    out = QPixmap(size, size)
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing, True)
    g = QLinearGradient(0, 0, size, size)
    base = QColor(color_for(name))
    g.setColorAt(0, base.lighter(118))
    g.setColorAt(1, base.darker(112))
    p.setBrush(g)
    p.setPen(Qt.NoPen)
    p.drawEllipse(QRectF(0, 0, size, size))
    f = QFont(theme.GLASS_FONT_FAMILY)
    f.setPixelSize(int(size * 0.44))
    f.setBold(True)
    p.setFont(f)
    p.setPen(QColor("white"))
    p.drawText(QRectF(0, 0, size, size), Qt.AlignCenter, (name or "?").strip()[:1].upper())
    p.end()
    return out


# ======================================================================
# Ticker de la esquina
# ======================================================================

class Ticker(QWidget):
    """Va encima del texto "Cumito" de la barra de arriba. Cuando llega una
    actividad nueva: "Cumito" se desvanece, aparece la frase (se desliza si
    no cabe) y a los 4 segundos vuelve "Cumito"."""

    def __init__(self, name_label: QLabel, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._name = name_label
        self._name_fx = QGraphicsOpacityEffect(name_label)
        self._name_fx.setOpacity(1.0)
        name_label.setGraphicsEffect(self._name_fx)
        self._who = self._rest = ""
        self._t = 0.0
        self._queue = []
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(float(TICKER_MS))
        self._anim.setDuration(TICKER_MS)
        self._anim.valueChanged.connect(self._on_value)
        self._anim.finished.connect(self._on_done)
        self._font_who = QFont(theme.GLASS_FONT_FAMILY)
        self._font_who.setPixelSize(12)
        self._font_who.setBold(True)
        self._font_rest = QFont(theme.GLASS_FONT_FAMILY)
        self._font_rest.setPixelSize(12)
        self.hide()

    def show_activity(self, a: dict):
        if self._anim.state() == QVariantAnimation.Running:
            # si llegan varias seguidas, se encolan (máx. 2 en espera)
            self._queue = (self._queue + [a])[-2:]
            return
        self._who, self._rest = sentence(a)
        self._color = QColor(color_for(self._who)).lighter(135) if self._who != BOT_NAME else QColor("#C9B8FF")
        self._t = 0.0
        self.show()
        self.raise_()
        self._anim.start()

    def _on_done(self):
        self._name_fx.setOpacity(1.0)
        self.hide()
        if self._queue:
            nxt = self._queue.pop(0)
            QTimer.singleShot(250, lambda: self.show_activity(nxt))

    def _on_value(self, v):
        self._t = float(v)
        fade = 280.0
        if self._t < fade:
            op = self._t / fade
        elif self._t > TICKER_MS - fade:
            op = max(0.0, (TICKER_MS - self._t) / fade)
        else:
            op = 1.0
        self._name_fx.setOpacity(1.0 - op)
        self._op = op
        self.update()

    def _text_width(self):
        fw, fr = QFontMetricsF(self._font_who), QFontMetricsF(self._font_rest)
        return fw.horizontalAdvance(self._who + " "), fr.horizontalAdvance(self._rest)

    def paintEvent(self, ev):
        if not self._who:
            return
        w, h = self.width(), self.height()
        ww, rw = self._text_width()
        total = ww + rw
        # si no cabe: espera un poquito, se desliza hasta el final y espera
        travel = max(0.0, total - w + 12)
        hold, end_hold = 700.0, 650.0
        span = max(1.0, TICKER_MS - hold - end_hold)
        k = min(1.0, max(0.0, (self._t - hold) / span))
        k = 0.5 - 0.5 * math.cos(k * math.pi)  # suave al empezar y al terminar
        x = -travel * k

        buf = QPixmap(w, h)
        buf.fill(Qt.transparent)
        p = QPainter(buf)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        p.setFont(self._font_who)
        p.setPen(self._color)
        p.drawText(QRectF(x, 0, ww + 4, h), Qt.AlignVCenter | Qt.AlignLeft, self._who)
        p.setFont(self._font_rest)
        p.setPen(QColor(theme.GLASS_TEXT))
        p.drawText(QRectF(x + ww, 0, rw + 4, h), Qt.AlignVCenter | Qt.AlignLeft, self._rest)
        # bordes que se desvanecen (para que el texto no se corte en seco)
        p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
        g = QLinearGradient(0, 0, w, 0)
        left = 10.0 / w if x < 0 else 0.0
        g.setColorAt(0.0, QColor(0, 0, 0, 0 if x < 0 else 255))
        g.setColorAt(left, QColor(0, 0, 0, 255))
        g.setColorAt(max(left, 1 - 16.0 / w), QColor(0, 0, 0, 255))
        g.setColorAt(1.0, QColor(0, 0, 0, 0 if travel > 0 else 255))
        p.fillRect(buf.rect(), g)
        p.end()

        painter = QPainter(self)
        painter.setOpacity(getattr(self, "_op", 1.0))
        painter.drawPixmap(0, 0, buf)
        painter.end()


# ======================================================================
# Pantalla de actividad (estilo chat)
# ======================================================================

BUBBLE_MAX = 248   # ancho máximo de una burbuja


def _fit(label: QLabel, text: str, px: float, bold: bool, room: int):
    """Una QLabel con salto de línea calcula mal su ancho y queda angosta:
    se le da el ancho de su texto (hasta el máximo que cabe)."""
    f = QFont(theme.GLASS_FONT_FAMILY)
    f.setPixelSize(int(round(px)))
    f.setBold(bold)
    label.setMinimumWidth(min(QFontMetrics(f).horizontalAdvance(text) + 4, room))


class _Bubble(QWidget):
    """Una burbuja: el texto y, si fue sobre una canción, su tarjetita."""

    def __init__(self, a: dict, art: QPixmap | None, parent=None):
        super().__init__(parent)
        self.setObjectName("actbubble")
        self.setAttribute(Qt.WA_StyledBackground, True)
        bot = a.get("who") == BOT_NAME
        bg = "rgba(142,108,242,0.20)" if bot else "rgba(255,255,255,0.08)"
        border = "rgba(142,108,242,0.40)" if bot else "rgba(255,255,255,0.10)"
        self.setStyleSheet(f"QWidget#actbubble {{ background:{bg}; border:1px solid {border}; border-radius:13px; }}")
        self.setMaximumWidth(BUBBLE_MAX)
        room = BUBBLE_MAX - 24
        lay = QVBoxLayout(self)
        lay.setContentsMargins(11, 7, 11, 8)
        lay.setSpacing(6)
        raw = a.get("text") or ""
        txt = QLabel(raw[:1].upper() + raw[1:])
        txt.setWordWrap(True)
        txt.setStyleSheet(f"color:{theme.GLASS_TEXT}; font-size:12px; background:transparent;")
        _fit(txt, txt.text(), 12, False, room)
        lay.addWidget(txt)
        self.art_label = None
        if a.get("title"):
            card = QHBoxLayout()
            card.setSpacing(8)
            has_art = bool(a.get("art"))
            if has_art:
                self.art_label = QLabel()
                self.art_label.setFixedSize(34, 34)
                self.art_label.setStyleSheet("background: rgba(255,255,255,0.08); border-radius:8px;")
                if art is not None and not art.isNull():
                    self.set_art(art)
                card.addWidget(self.art_label, 0, Qt.AlignTop)
            info = QVBoxLayout()
            info.setSpacing(0)
            t = QLabel(a["title"])
            t.setWordWrap(True)
            t.setStyleSheet("color:#fff; font-size:11.5px; font-weight:700; background:transparent;")
            _fit(t, a["title"], 11.5, True, room - (42 if has_art else 0))
            info.addWidget(t)
            if a.get("sub"):
                s = QLabel(a["sub"])
                s.setWordWrap(True)
                s.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE}; font-size:10.5px; background:transparent;")
                _fit(s, a["sub"], 10.5, False, room - (42 if has_art else 0))
                info.addWidget(s)
            card.addLayout(info, 1)
            lay.addLayout(card)

    def set_art(self, pix: QPixmap):
        if self.art_label is not None and pix is not None and not pix.isNull():
            self.art_label.setStyleSheet("background:transparent;")
            self.art_label.setPixmap(_round_pix(pix, 34, 8))


class ActivityFeed(QWidget):
    """La lista de mensajes. Lo más nuevo abajo, como un chat."""

    GROUP_S = 5 * 60   # mensajes seguidos de la misma persona: una sola cabecera

    def __init__(self, art_cache, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background:transparent;")
        self.art_cache = art_cache
        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(2, 4, 6, 10)
        self._lay.setSpacing(3)
        self._lay.addStretch()
        self._entries = []
        self._bubbles = {}      # url de portada -> [burbujas que la esperan]
        self._last_sig = None

    def set_entries(self, entries):
        self._entries = [e for e in entries if isinstance(e, dict)]
        self._rebuild()

    def add_or_update(self, a: dict):
        """Una actividad nueva (o la última que cambió, ej. el volumen)."""
        if self._entries and self._entries[-1].get("id") == a.get("id"):
            self._entries[-1] = a
        else:
            self._entries.append(a)
        self._rebuild()

    def _clear(self):
        while self._lay.count() > 1:
            item = self._lay.takeAt(1)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._bubbles = {}

    def _rebuild(self):
        sig = tuple((e.get("id"), e.get("text"), e.get("ts")) for e in self._entries)
        if sig == self._last_sig:
            return
        self._last_sig = sig
        self._clear()
        if not self._entries:
            empty = QLabel("Todavía no hay actividad.\nCuando alguien ponga música, aparece aquí.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE2}; font-size:12px; background:transparent; padding:40px 0;")
            self._lay.addWidget(empty)
            return
        prev = None
        for a in self._entries:
            ts = float(a.get("ts") or 0)
            if prev is None or day_label(ts) != day_label(float(prev.get("ts") or 0)):
                self._lay.addSpacing(6)
                self._lay.addWidget(self._day_chip(day_label(ts)), 0, Qt.AlignHCenter)
                self._lay.addSpacing(4)
                prev = None
            grouped = (prev is not None and prev.get("who") == a.get("who")
                       and ts - float(prev.get("ts") or 0) < self.GROUP_S)
            self._lay.addWidget(self._row(a, grouped))
            prev = a

    def _day_chip(self, text):
        chip = QLabel(text)
        chip.setStyleSheet(
            f"color:{theme.GLASS_TEXT_MUTE}; font-size:10px; font-weight:700; letter-spacing:0.5px;"
            " background: rgba(255,255,255,0.08); border-radius:9px; padding:3px 10px;"
        )
        return chip

    def _row(self, a, grouped):
        row = QWidget()
        row.setStyleSheet("background:transparent;")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0 if grouped else 8, 0, 0)
        h.setSpacing(9)
        who = a.get("who") or "Alguien"
        av = QLabel()
        av.setFixedSize(30, 30)
        av.setStyleSheet("background:transparent;")
        if not grouped:
            av.setPixmap(avatar(who, 30))
        h.addWidget(av, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(3)
        if not grouped:
            head = QHBoxLayout()
            head.setSpacing(6)
            n = QLabel(who)
            c = QColor(color_for(who)).lighter(140) if who != BOT_NAME else QColor("#C9B8FF")
            n.setStyleSheet(f"color:{c.name()}; font-size:12px; font-weight:800; background:transparent;")
            head.addWidget(n)
            tm = QLabel(clock(float(a.get("ts") or 0)))
            tm.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE2}; font-size:10px; background:transparent;")
            head.addWidget(tm)
            head.addStretch()
            col.addLayout(head)
        art_url = a.get("art")
        pix = self.art_cache.get(art_url) if art_url else None
        b = _Bubble(a, pix)
        if art_url and pix is None:
            self._bubbles.setdefault(art_url, []).append(b)
            self.art_cache.request(art_url)
        bubble_row = QHBoxLayout()
        bubble_row.addWidget(b, 0)
        bubble_row.addStretch(1)
        col.addLayout(bubble_row)
        h.addLayout(col, 1)
        return row

    def on_art_loaded(self, url, pixmap):
        for b in self._bubbles.pop(url, []):
            try:
                b.set_art(pixmap)
            except RuntimeError:
                pass  # esa burbuja ya se borró
