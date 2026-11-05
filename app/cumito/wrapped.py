"""
"Tu Wrapped": lo más escuchado en Cumito (semana, mes, año o siempre),
del grupo o solo lo que puse yo. Los números los calcula el servidor.
"""
from __future__ import annotations

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import theme
from .albums import _AlbumTrackRow, _label, _round_icon

PERIODS = [("week", "Semana"), ("month", "Mes"), ("year", "Año"), ("all", "Siempre")]
PERIOD_TITLE = {"week": "Esta semana", "month": "Este mes", "year": "Este año", "all": "Desde siempre"}
PEOPLE_COLORS = ["#8E6CF2", "#4FB4D8", "#D1517A", "#3DBE7A", "#F2A33A", "#1F5FBF", "#E0457B", "#22A699"]


def _hour_name(h):
    if h == 0:
        return "12 a. m."
    if h < 12:
        return f"{h} a. m."
    if h == 12:
        return "12 p. m."
    return f"{h - 12} p. m."


class _Hero(QWidget):
    """La tarjeta grande con los minutos."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(132)
        self.title, self.minutes, self.sub = "", "0", ""

    def set(self, title, minutes, sub):
        self.title, self.minutes, self.sub = title, minutes, sub
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(r, 20, 20)
        g = QLinearGradient(0, 0, r.width(), r.height())
        g.setColorAt(0, QColor("#8E6CF2"))
        g.setColorAt(0.55, QColor("#D1517A"))
        g.setColorAt(1, QColor("#F2A33A"))
        p.fillPath(path, g)
        p.setClipPath(path)
        p.setPen(Qt.NoPen)
        for cx, cy, rad, a in ((r.width() * 0.88, 14, 70, 40), (r.width() * 0.1, r.height(), 60, 30)):
            p.setBrush(QColor(255, 255, 255, a))
            p.drawEllipse(QRectF(cx - rad, cy - rad, rad * 2, rad * 2))
        f = QFont(theme.GLASS_FONT_FAMILY)
        f.setPixelSize(11)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 220))
        p.drawText(QRectF(18, 14, r.width() - 36, 16), Qt.AlignLeft, self.title.upper())
        f.setPixelSize(44)
        f.setWeight(QFont.Black)
        p.setFont(f)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRectF(16, 30, r.width() - 32, 54), Qt.AlignLeft | Qt.AlignVCenter, self.minutes)
        f.setPixelSize(12)
        f.setWeight(QFont.Bold)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 235))
        p.drawText(QRectF(18, 84, r.width() - 36, 18), Qt.AlignLeft, "minutos escuchados")
        f.setPixelSize(10)
        f.setWeight(QFont.DemiBold)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 200))
        p.drawText(QRectF(18, 104, r.width() - 36, 16), Qt.AlignLeft, self.sub)
        p.end()


class _Hours(QWidget):
    """24 barritas: a qué hora suena más Cumito."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(70)
        self.hours = [0] * 24

    def set(self, hours):
        self.hours = list(hours or [0] * 24)[:24] + [0] * max(0, 24 - len(hours or []))
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        top = max(self.hours) or 1
        best = self.hours.index(top) if any(self.hours) else -1
        w = self.width() / 24
        bh = self.height() - 16
        for i, v in enumerate(self.hours):
            h = max(3.0, bh * v / top) if v else 3.0
            x = i * w + w * 0.18
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(theme.GLASS_ACCENT) if i == best else QColor(255, 255, 255, 60 if v else 25))
            p.drawRoundedRect(QRectF(x, bh - h, w * 0.64, h), 2, 2)
        f = QFont(theme.GLASS_FONT_FAMILY)
        f.setPixelSize(9)
        p.setFont(f)
        p.setPen(QColor(242, 240, 247, 110))
        for i, t in ((0, "12a"), (6, "6a"), (12, "12p"), (18, "6p")):
            p.drawText(QRectF(i * w - 4, bh + 3, 30, 12), Qt.AlignLeft, t)
        p.end()


class _Bar(QWidget):
    """Una persona: nombre, barrita y cuántas puso."""

    def __init__(self, name, value, top, color, parent=None):
        super().__init__(parent)
        self.setFixedHeight(30)
        self.name, self.value, self.top, self.color = name, value, max(1, top), QColor(color)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        f = QFont(theme.GLASS_FONT_FAMILY)
        f.setPixelSize(11)
        f.setBold(True)
        p.setFont(f)
        # avatar con la inicial
        p.setPen(Qt.NoPen)
        p.setBrush(self.color)
        p.drawEllipse(QRectF(2, 4, 22, 22))
        p.setPen(QColor("#FFFFFF"))
        p.drawText(QRectF(2, 4, 22, 22), Qt.AlignCenter, (self.name or "?")[:1].upper())
        x0 = 32
        name_w = 78
        p.setPen(QColor(theme.GLASS_TEXT))
        p.drawText(QRectF(x0, 0, name_w, 30), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(self.name, Qt.ElideRight, name_w - 4))
        bx = x0 + name_w
        bw = self.width() - bx - 44
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 22))
        p.drawRoundedRect(QRectF(bx, 11, bw, 8), 4, 4)
        p.setBrush(self.color)
        p.drawRoundedRect(QRectF(bx, 11, max(8.0, bw * self.value / self.top), 8), 4, 4)
        p.setPen(QColor(242, 240, 247, 170))
        p.drawText(QRectF(self.width() - 40, 0, 40, 30), Qt.AlignRight | Qt.AlignVCenter, str(self.value))
        p.end()


class WrappedView(QWidget):
    closed = Signal()

    def __init__(self, send, art_cache, scroll_factory, my_name=lambda: None, parent=None):
        super().__init__(parent)
        self.send = send
        self.art = art_cache
        self.my_name = my_name
        self.period = "month"
        self.mine = False
        self._rows = []
        self.art.loaded.connect(self._on_art)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(8)
        head = QHBoxLayout()
        b = _round_icon("back", 30, "Volver")
        b.clicked.connect(self.closed.emit)
        head.addWidget(b)
        tcol = QVBoxLayout()
        tcol.setSpacing(0)
        tcol.addWidget(_label("Tu Wrapped", 19, 800, "#FFFFFF"))
        self.sub = _label("Lo que más sonó en Cumito", 10.5, 600, theme.GLASS_TEXT_MUTE2)
        tcol.addWidget(self.sub)
        head.addLayout(tcol, 1)
        lay.addLayout(head)

        tabs = QHBoxLayout()
        tabs.setSpacing(6)
        self.tabs = {}
        for key, text in PERIODS:
            t = QPushButton(text)
            t.setCursor(Qt.PointingHandCursor)
            t.setFixedHeight(28)
            t.clicked.connect(lambda _=False, k=key: self.load(k))
            self.tabs[key] = t
            tabs.addWidget(t)
        tabs.addStretch()
        self.who_btn = QPushButton("Del grupo")
        self.who_btn.setCursor(Qt.PointingHandCursor)
        self.who_btn.setFixedHeight(28)
        self.who_btn.setToolTip("Cambiar entre todo el grupo y solo lo que pusiste tú")
        self.who_btn.clicked.connect(self._toggle_who)
        tabs.addWidget(self.who_btn)
        lay.addLayout(tabs)

        body = QWidget()
        self.bl = QVBoxLayout(body)
        self.bl.setContentsMargins(2, 4, 4, 24)
        self.bl.setSpacing(8)
        self.hero = _Hero()
        self.bl.addWidget(self.hero)
        self.empty = _label("Todavía no hay nada que contar en este tiempo.\n¡Pongan música!", 12, 600,
                            theme.GLASS_TEXT_MUTE, wrap=True)
        self.empty.setAlignment(Qt.AlignCenter)
        self.bl.addWidget(self.empty)
        self.songs_h = self._section("LO MÁS ESCUCHADO")
        self.songs_box = QVBoxLayout()
        self.songs_box.setSpacing(2)
        self.bl.addLayout(self.songs_box)
        self.artists_h = self._section("ARTISTAS")
        self.artists = _label("", 12.5, 700, theme.GLASS_TEXT, wrap=True)
        self.bl.addWidget(self.artists)
        self.people_h = self._section("QUIÉN PUSO MÁS")
        self.people_box = QVBoxLayout()
        self.people_box.setSpacing(0)
        self.bl.addLayout(self.people_box)
        self.hours_h = self._section("A QUÉ HORA SUENA CUMITO")
        self.hours = _Hours()
        self.bl.addWidget(self.hours)
        self.hours_note = _label("", 11, 600, theme.GLASS_TEXT_MUTE)
        self.bl.addWidget(self.hours_note)
        self.bl.addStretch()
        self.scroll = scroll_factory(body)
        lay.addWidget(self.scroll, 1)
        self._style_tabs()

    def _section(self, text):
        l = _label(text, 10, 800, theme.GLASS_TEXT_MUTE)
        l.setContentsMargins(2, 10, 0, 0)
        self.bl.addWidget(l)
        return l

    def _style_tabs(self):
        for k, t in self.tabs.items():
            on = k == self.period
            t.setStyleSheet(
                "QPushButton { border-radius:14px; padding:0 11px; font-size:11px; font-weight:800;"
                + (" background:#FFFFFF; color:#14121A; border:none; }" if on else
                   " background: rgba(255,255,255,0.10); color:#F2F0F7; border:1px solid rgba(255,255,255,0.18); }"
                   " QPushButton:hover { background: rgba(255,255,255,0.18); }"))
        self.who_btn.setText("Solo yo" if self.mine else "Del grupo")
        self.who_btn.setStyleSheet(
            "QPushButton { border-radius:14px; padding:0 11px; font-size:11px; font-weight:800;"
            " background: rgba(142,108,242,0.25); color:#E3D9FF; border:1px solid rgba(142,108,242,0.5); }"
            " QPushButton:hover { background: rgba(142,108,242,0.4); }")

    def _toggle_who(self):
        self.mine = not self.mine
        self.load(self.period)

    def load(self, period=None):
        self.period = period or self.period
        self._style_tabs()
        kw = {"period": self.period}
        if self.mine and self.my_name():
            kw["who"] = self.my_name()
        self.send("stats", **kw)

    def set_stats(self, d):
        if d.get("period") and d["period"] != self.period:
            return
        plays = d.get("plays") or 0
        title = PERIOD_TITLE.get(self.period, "") + (" · solo tú" if self.mine else "")
        sub = f"{plays} canciones · {d.get('days', 0)} días con música"
        if d.get("skipped"):
            sub += f" · {d['skipped']} saltadas"
        self.hero.set(title, f"{d.get('minutes', 0):,}".replace(",", "."), sub)
        has = plays > 0
        self.empty.setVisible(not has)
        for w in (self.songs_h, self.artists_h, self.people_h, self.hours_h, self.hours, self.hours_note,
                  self.artists):
            w.setVisible(has)
        # canciones
        for box in (self.songs_box, self.people_box):
            while box.count():
                it = box.takeAt(0)
                if it.widget():
                    it.widget().deleteLater()
        self._rows = []
        for i, s in enumerate((d.get("top_songs") or [])[:5], 1):
            t = {"title": f"{i}.  {s.get('title') or 'Sin título'}", "uploader": f"{s.get('uploader') or ''}"
                 f"{' · ' if s.get('uploader') else ''}{s['plays']} {'vez' if s['plays'] == 1 else 'veces'}",
                 "art_url": s.get("art_url"), "duration": None}
            pix = self.art.get(s.get("art_url"))
            if pix is None:
                self.art.request(s.get("art_url"))
            row = _AlbumTrackRow(t, pix)
            row.btn_x.hide()
            row.setCursor(Qt.ArrowCursor)
            self._rows.append(row)
            self.songs_box.addWidget(row)
        arts = d.get("top_artists") or []
        self.artists.setText("   ".join(f"{i}. {a['name']}" for i, a in enumerate(arts[:6], 1)))
        people = (d.get("top_people") or [])[:6]
        top = people[0]["plays"] if people else 1
        for i, pe in enumerate(people):
            self.people_box.addWidget(_Bar(pe["name"], pe["plays"], top, PEOPLE_COLORS[i % len(PEOPLE_COLORS)]))
        self.people_h.setVisible(has and bool(people) and not self.mine)
        for i in range(self.people_box.count()):
            w = self.people_box.itemAt(i).widget()
            if w:
                w.setVisible(not self.mine)
        hours = d.get("hours") or []
        self.hours.set(hours)
        if any(hours):
            h = hours.index(max(hours))
            self.hours_note.setText(f"La hora favorita: las {_hour_name(h)}")

    def _on_art(self, key, pix):
        for r in self._rows:
            if r.t.get("art_url") == key:
                r.set_pix(pix)
