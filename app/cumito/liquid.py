"""
Piezas del diseño "Liquid" (la 2.0 aprobada en el lienzo):

  - SearchPill: la píldora de "Buscar" que, al tocarla, se estira hasta
    arriba (con rebote) y se vuelve el buscador.
  - SegTabs: pestañas con un indicador blanco que se desliza (Música / Todo).
  - Chip: búsqueda reciente en forma de pastilla.
  - RecentCard / AlbumCard / ActivityLine / Members: las piezas del inicio.
  - CoverThumb: la miniatura de lo que suena (se achica un poquito en pausa).
  - TitleEq: las barritas que bailan al lado de "Cumito" mientras suena.
  - burst(): el estallido de puntitos del corazón.

Rendimiento: nada de esto se anima solo todo el rato. Las animaciones son
cortas (al tocar algo) y las barritas del título van a pocos cuadros por
segundo y se paran en pausa o con la ventana minimizada.
"""
from __future__ import annotations

import math

from PySide6.QtCore import (
    QEasingCurve, QPointF, QPropertyAnimation, QRect, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal,
)
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QLineEdit, QPushButton, QSizePolicy, QWidget

from . import icons, theme

SPRING = QEasingCurve(QEasingCurve.OutBack)
SPRING.setOvershoot(1.25)


def _font(px, weight=QFont.Bold):
    f = QFont(theme.GLASS_FONT_FAMILY)
    f.setPixelSize(int(px))
    f.setWeight(weight)
    return f


def paint_glass(p: QPainter, rect: QRectF, radius: float, focus=0.0):
    """El vidrio "liquid": degradado claro arriba, borde de luz y un filo
    brillante arriba. focus (0..1) le pone el halo morado del buscador."""
    path = QPainterPath()
    path.addRoundedRect(rect, radius, radius)
    if focus > 0:
        halo = QPainterPath()
        halo.addRoundedRect(rect.adjusted(-4, -4, 4, 4), radius + 4, radius + 4)
        p.fillPath(halo.subtracted(path), QColor(142, 108, 242, int(52 * focus)))
    g = QLinearGradient(0, rect.top(), 0, rect.bottom())
    g.setColorAt(0, QColor(255, 255, 255, 46))
    g.setColorAt(1, QColor(255, 255, 255, 18))
    p.fillPath(path, QColor(16, 14, 22, 70))
    p.fillPath(path, g)
    border = QColor(201, 180, 248, int(51 + 128 * focus)) if focus else QColor(255, 255, 255, 51)
    p.setPen(QPen(border, 1))
    p.setBrush(Qt.NoBrush)
    p.drawPath(path)
    # filo de luz arriba
    p.save()
    p.setClipPath(path)
    p.setPen(QPen(QColor(255, 255, 255, 97), 1))
    p.drawLine(QPointF(rect.left() + radius * 0.6, rect.top() + 1), QPointF(rect.right() - radius * 0.6, rect.top() + 1))
    p.restore()


# ---------------------------------------------------------------------------
# La píldora del buscador
# ---------------------------------------------------------------------------
class SearchPill(QWidget):
    """Cerrada: ícono + "Buscar" (cualquier clic la abre). Abierta: ícono +
    el campo de texto + una X para cerrar. El cambio de tamaño lo anima la
    ventana (morph) con geometry."""

    opened = Signal()
    close_clicked = Signal()

    def __init__(self, line_edit: QLineEdit, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self._open = False
        self._focus = 0.0
        self.word = "Buscar"
        self.edit = line_edit
        line_edit.setParent(self)
        line_edit.setFrame(False)
        line_edit.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none; color: #FFFFFF; font-size: 14px;"
            f" font-weight: 600; selection-background-color: rgba(142,108,242,0.6); }}")
        line_edit.hide()
        self.x_btn = QPushButton(self)
        self.x_btn.setCursor(Qt.PointingHandCursor)
        self.x_btn.setFixedSize(34, 34)
        self.x_btn.setIcon(icons.icon("close", "#FFFFFF", 14))
        self.x_btn.setIconSize(QSize(14, 14))
        self.x_btn.setToolTip("Cerrar la búsqueda")
        self.x_btn.setStyleSheet("QPushButton { background: rgba(255,255,255,0.14); border:none; border-radius:17px; }"
                                 "QPushButton:hover { background: rgba(255,255,255,0.24); }")
        self.x_btn.clicked.connect(self.close_clicked.emit)
        self.x_btn.hide()
        self._fa = QVariantAnimation(self)
        self._fa.setDuration(450)
        self._fa.valueChanged.connect(self._on_focus)

    def _on_focus(self, v):
        self._focus = float(v)
        self.update()

    def set_open(self, on: bool):
        self._open = on
        self.edit.setVisible(on)
        self.x_btn.setVisible(on)
        self.setCursor(Qt.ArrowCursor if on else Qt.PointingHandCursor)
        self._fa.stop()
        self._fa.setStartValue(self._focus)
        self._fa.setEndValue(1.0 if on else 0.0)
        self._fa.start()
        self._layout()
        self.update()

    def is_open(self):
        return self._open

    def resizeEvent(self, ev):
        self._layout()
        super().resizeEvent(ev)

    def _layout(self):
        h = self.height()
        self.edit.setGeometry(40, 0, max(10, self.width() - 40 - 46), h)
        self.x_btn.move(self.width() - 34 - 6, (h - 34) // 2)

    def mousePressEvent(self, ev):
        if not self._open and ev.button() == Qt.LeftButton:
            self.opened.emit()
        ev.accept()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(4.5, 4.5, -4.5, -4.5)
        paint_glass(p, r, r.height() / 2, self._focus)
        ic = icons.pixmap("search", "#FFFFFF", 15)
        p.drawPixmap(QPointF(r.left() + 12, r.center().y() - 7.5), ic)
        if not self._open:
            p.setFont(_font(13 if r.height() < 40 else 14, QFont.Bold))
            p.setPen(QColor(255, 255, 255, 235 if r.height() < 40 else 180))
            p.drawText(QRectF(r.left() + 34, r.top(), r.width() - 40, r.height()), Qt.AlignLeft | Qt.AlignVCenter,
                       self.word)
        p.end()


# ---------------------------------------------------------------------------
# Pestañas con indicador que se desliza
# ---------------------------------------------------------------------------
class SegTabs(QWidget):
    changed = Signal(str)

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items   # [(key, texto, ancho)]
        self.cur = items[0][0]
        self.setFixedHeight(32)
        self.setFixedWidth(sum(w for _k, _t, w in items) + 8 * (len(items) - 1))
        self.setCursor(Qt.PointingHandCursor)
        r = self._rect(self.cur)
        self._l, self._r = r.left(), r.right()
        self._al = QVariantAnimation(self)
        self._ar = QVariantAnimation(self)
        for a in (self._al, self._ar):
            a.setEasingCurve(SPRING)
            a.valueChanged.connect(lambda _v: self.update())

    def _rect(self, key):
        x = 0
        for k, _t, w in self.items:
            if k == key:
                return QRectF(x, 0, w, 32)
            x += w + 8
        return QRectF(0, 0, 10, 32)

    def set_current(self, key, animate=True):
        if key == self.cur and not animate:
            return
        old = self._rect(self.cur)
        new = self._rect(key)
        self.cur = key
        if not animate:
            self._l, self._r = new.left(), new.right()
            self.update()
            return
        # el borde que va adelante corre primero y el de atrás lo alcanza (como gota)
        going_right = new.left() > old.left()
        lead, tail = (self._ar, self._al) if going_right else (self._al, self._ar)
        for a in (self._al, self._ar):
            a.stop()
        self._al.setStartValue(float(self._cur_l()))
        self._al.setEndValue(float(new.left()))
        self._ar.setStartValue(float(self._cur_r()))
        self._ar.setEndValue(float(new.right()))
        lead.setDuration(380)
        tail.setDuration(620)
        self._al.start()
        self._ar.start()

    def _cur_l(self):
        v = self._al.currentValue()
        return v if self._al.state() == QVariantAnimation.Running and v is not None else self._l

    def _cur_r(self):
        v = self._ar.currentValue()
        return v if self._ar.state() == QVariantAnimation.Running and v is not None else self._r

    def paintEvent(self, ev):
        l = self._cur_l() if self._al.state() == QVariantAnimation.Running else self._rect(self.cur).left()
        r = self._cur_r() if self._ar.state() == QVariantAnimation.Running else self._rect(self.cur).right()
        self._l, self._r = l, r
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(255, 255, 255, 240))
        p.drawRoundedRect(QRectF(l, 0, max(10.0, r - l), 32), 12, 12)
        p.setFont(_font(12.5, QFont.ExtraBold))
        for k, t, _w in self.items:
            rr = self._rect(k)
            inside = l <= rr.center().x() <= r
            p.setPen(QColor("#141318") if inside else QColor(255, 255, 255, 190))
            p.drawText(rr, Qt.AlignCenter, t)
        p.end()

    def mouseReleaseEvent(self, ev):
        for k, _t, _w in self.items:
            if self._rect(k).contains(ev.position()) and k != self.cur:
                self.set_current(k)
                self.changed.emit(k)
                break
        ev.accept()

    def mousePressEvent(self, ev):
        ev.accept()


class Chip(QPushButton):
    """Búsqueda reciente: pastillita con un relojito."""

    def __init__(self, text, parent=None):
        super().__init__(" " + text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(32)
        self.setIcon(icons.icon("timer", "#BDB8CC", 12))
        self.setIconSize(QSize(12, 12))
        self.setStyleSheet(
            "QPushButton { background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.12);"
            " border-radius: 16px; padding: 0 13px; color: #FFFFFF; font-size: 12px; font-weight: 700; }"
            "QPushButton:hover { background: rgba(255,255,255,0.18); }")


class FlowBox(QWidget):
    """Acomoda pastillitas de izquierda a derecha y salta de renglón."""

    def __init__(self, gap=8, parent=None):
        super().__init__(parent)
        self.gap = gap
        self.items: list[QWidget] = []
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_items(self, widgets):
        for w in self.items:
            w.deleteLater()
        self.items = list(widgets)
        for w in self.items:
            w.setParent(self)
            w.show()
        self._relayout()

    def resizeEvent(self, ev):
        self._relayout()
        super().resizeEvent(ev)

    def _relayout(self):
        x = y = 0
        line_h = 0
        W = max(60, self.width())
        for w in self.items:
            s = w.sizeHint()
            if x and x + s.width() > W:
                x, y = 0, y + line_h + self.gap
                line_h = 0
            w.setGeometry(x, y, min(s.width(), W), s.height())
            x += s.width() + self.gap
            line_h = max(line_h, s.height())
        self.setFixedHeight(y + line_h if self.items else 0)


# ---------------------------------------------------------------------------
# Inicio
# ---------------------------------------------------------------------------
def _cover_fill(pix, w, h):
    s = pix.scaled(w, h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
    return s.copy((s.width() - w) // 2, (s.height() - h) // 2, w, h)


class _Press(QWidget):
    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self._hover = False
        self._down = False

    def enterEvent(self, ev):
        self._hover = True
        self.update()

    def leaveEvent(self, ev):
        self._hover = False
        self.update()

    def mousePressEvent(self, ev):
        self._down = ev.button() == Qt.LeftButton
        self.update()
        ev.accept()

    def mouseReleaseEvent(self, ev):
        was = self._down
        self._down = False
        self.update()
        if was and self.rect().contains(ev.position().toPoint()):
            self.clicked.emit()
        ev.accept()


class RecentCard(_Press):
    """Portada cuadrada de 112 px con el título abajo (clic = ponerla otra vez)."""

    S = 112

    def __init__(self, title, artist, pix=None, parent=None):
        super().__init__(parent)
        self.title, self.artist, self.pix = title, artist, pix
        self.setFixedSize(self.S, self.S + 40)
        self.setToolTip("Ponerla otra vez")

    def set_pix(self, pix):
        self.pix = pix
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        lift = -3 if self._hover and not self._down else 0
        sc = 0.96 if self._down else 1.0
        S = self.S * sc
        off = (self.S - S) / 2
        r = QRectF(off, off + lift + 2, S, S)
        path = QPainterPath()
        path.addRoundedRect(r, 18, 18)
        p.save()
        p.setClipPath(path)
        if self.pix is not None and not self.pix.isNull():
            p.drawPixmap(r, _cover_fill(self.pix, self.S * 2, self.S * 2), QRectF(0, 0, self.S * 2, self.S * 2))
        else:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, QColor(theme.GLASS_GRAD_1))
            g.setColorAt(1, QColor(theme.GLASS_GRAD_3))
            p.fillRect(r, g)
        shine = QLinearGradient(r.topLeft(), r.center())
        shine.setColorAt(0, QColor(255, 255, 255, 70))
        shine.setColorAt(1, QColor(255, 255, 255, 0))
        p.fillRect(r, shine)
        p.restore()
        if self._hover:
            # el botoncito de play aparece al pasar el mouse
            c = QPointF(r.right() - 20, r.bottom() - 20)
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 255, 255, 235))
            p.drawEllipse(c, 15, 15)
            tri = QPainterPath()
            tri.moveTo(c.x() - 4, c.y() - 6)
            tri.lineTo(c.x() + 7, c.y())
            tri.lineTo(c.x() - 4, c.y() + 6)
            tri.closeSubpath()
            p.fillPath(tri, QColor("#141318"))
        p.setFont(_font(12, QFont.ExtraBold))
        p.setPen(QColor("#FFFFFF"))
        fm = p.fontMetrics()
        p.drawText(QRectF(0, self.S + 6, self.S, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(self.title, Qt.ElideRight, self.S))
        p.setFont(_font(10.5, QFont.DemiBold))
        p.setPen(QColor(244, 242, 250, 140))
        fm = p.fontMetrics()
        p.drawText(QRectF(0, self.S + 23, self.S, 15), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(self.artist, Qt.ElideRight, self.S))
        p.end()


class AlbumCard(_Press):
    """Disco del grupo en el inicio: tarjeta del color del disco."""

    def __init__(self, album, cover=None, parent=None):
        super().__init__(parent)
        self.album = album
        self.cover = cover
        self.setFixedHeight(96)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def set_cover(self, pix):
        self.cover = pix
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        lift = -3 if self._hover and not self._down else 0
        r = QRectF(0, 3 + lift, self.width(), 92)
        if self._down:
            r = r.adjusted(3, 3, -3, -3)
        path = QPainterPath()
        path.addRoundedRect(r, 18, 18)
        col = QColor(self.album.get("color") or theme.GLASS_ACCENT)
        p.save()
        p.setClipPath(path)
        p.fillRect(r, col)
        if self.cover is not None and not self.cover.isNull():
            side = int(r.height())
            p.setOpacity(0.9)
            p.drawPixmap(QRectF(r.right() - side, r.top(), side, side),
                         _cover_fill(self.cover, side * 2, side * 2), QRectF(0, 0, side * 2, side * 2))
            p.setOpacity(1.0)
            fade = QLinearGradient(r.right() - side, 0, r.right() - side * 0.35, 0)
            fade.setColorAt(0, col)
            c2 = QColor(col)
            c2.setAlpha(0)
            fade.setColorAt(1, c2)
            p.fillRect(QRectF(r.right() - side, r.top(), side, side), fade)
        p.restore()
        light = col.lightnessF() > 0.62
        fg = QColor("#2A1A00") if light else QColor("#FFFFFF")
        p.setFont(_font(15, QFont.ExtraBold))
        p.setPen(fg)
        p.drawText(QRectF(r.left() + 12, r.top() + 10, r.width() - 24, 44), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                   self.album.get("name") or "Disco")
        n = self.album.get("count", 0)
        sub = (f"de {self.album['owner']} · " if self.album.get("owner") else "") + \
              (f"{n} canción" if n == 1 else f"{n} canciones")
        sub_c = QColor(fg)
        sub_c.setAlpha(185)
        p.setPen(sub_c)
        p.setFont(_font(10.5, QFont.Bold))
        p.drawText(QRectF(r.left() + 12, r.bottom() - 26, r.width() - 24, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(sub, Qt.ElideRight, int(r.width() - 24)))
        p.end()


PEOPLE = ["#4FB4D8", "#D1517A", "#8E6CF2", "#3DBE7A", "#F2A33A", "#1F5FBF", "#E0457B", "#22A699"]


def person_color(name):
    if not name:
        return QColor(theme.GLASS_ACCENT)
    if name == "Cumito":
        return QColor("#8E6CF2")
    return QColor(PEOPLE[sum(ord(c) for c in name) % len(PEOPLE)])


class Members(QWidget):
    """Las bolitas de quién está conectado + "Ana, Pedro y tú" + punto verde."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(26)
        self.names: list[str] = []
        self.me = None
        self._t = 0.0

    def set_members(self, names, me):
        self.names, self.me = list(names or []), me
        self.update()

    def text(self):
        others = [n for n in self.names if n != self.me]
        has_me = self.me in self.names
        if not others:
            return "Solo tú por ahora" if has_me else "Nadie conectado"
        if len(others) > 3:
            shown = ", ".join(others[:2]) + f" y {len(others) - 2} más"
        else:
            shown = ", ".join(others[:-1]) + (" y " if len(others) > 1 else "") + others[-1]
        return shown + (" y tú" if has_me else "")

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        x = 0.0
        shown = self.names[:4]
        for n in shown:
            p.setPen(QPen(QColor("#0B0A10"), 2))
            p.setBrush(person_color(n))
            p.drawEllipse(QRectF(x + 1, 1, 23, 23))
            p.setPen(QColor("#FFFFFF"))
            p.setFont(_font(10, QFont.ExtraBold))
            p.drawText(QRectF(x + 1, 1, 23, 23), Qt.AlignCenter, (n[:1] or "?").upper())
            x += 17
        if shown:
            x += 14
        p.setFont(_font(11, QFont.Bold))
        p.setPen(QColor(244, 242, 250, 170))
        t = self.text()
        tw = p.fontMetrics().horizontalAdvance(t)
        p.drawText(QRectF(x, 0, self.width() - x - 14, 26), Qt.AlignLeft | Qt.AlignVCenter, t)
        if self.names:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor("#3DDC84"))
            p.drawEllipse(QRectF(min(self.width() - 9, x + tw + 8), 9.5, 7, 7))
        p.end()


class ActivityLine(QWidget):
    """'(A) Ana agregó 1 canción: La Bachata' en una línea."""

    def __init__(self, a, parent=None):
        super().__init__(parent)
        self.a = a
        self.setFixedHeight(26)

    def paintEvent(self, ev):
        a = self.a
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        who = a.get("who") or "Alguien"
        p.setPen(Qt.NoPen)
        p.setBrush(person_color(who))
        p.drawEllipse(QRectF(0, 2, 22, 22))
        p.setPen(QColor("#FFFFFF"))
        p.setFont(_font(10, QFont.ExtraBold))
        p.drawText(QRectF(0, 2, 22, 22), Qt.AlignCenter, who[:1].upper())
        p.setFont(_font(11.5, QFont.ExtraBold))
        fm = p.fontMetrics()
        x = 31
        p.drawText(QRectF(x, 0, self.width() - x, 26), Qt.AlignLeft | Qt.AlignVCenter, who)
        x += fm.horizontalAdvance(who) + 5
        rest = a.get("text") or ""
        if a.get("title"):
            rest += f": {a['title']}"
        p.setFont(_font(11.5, QFont.Medium))
        p.setPen(QColor(244, 242, 250, 205))
        fm = p.fontMetrics()
        p.drawText(QRectF(x, 0, self.width() - x, 26), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(rest, Qt.ElideRight, int(self.width() - x)))
        p.end()


class Mascot(QLabel):
    """Cumito en el inicio: si lo tocas, salta."""

    def __init__(self, pix, parent=None):
        super().__init__(parent)
        self.setPixmap(pix) if pix is not None else None
        self.setFixedSize(112, 150)
        self.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("background: transparent;")
        self._base = None
        self._a = QVariantAnimation(self)
        self._a.setDuration(900)
        self._a.setStartValue(0.0)
        self._a.setEndValue(1.0)
        self._a.valueChanged.connect(self._on)

    def mousePressEvent(self, ev):
        if self._a.state() != QVariantAnimation.Running:
            self._base = self.pos()
            self._a.start()
        ev.accept()

    def _on(self, t):
        t = float(t)
        # un salto con rebote: sube rápido, cae y se aplasta un poquito
        y = -34 * math.sin(math.pi * min(1.0, t / 0.62)) if t < 0.62 else 3 * math.sin(math.pi * (t - 0.62) / 0.38)
        if self._base is not None:
            self.move(self._base.x(), int(self._base.y() + y))


# ---------------------------------------------------------------------------
# Ahora sonando
# ---------------------------------------------------------------------------
class CoverThumb(QWidget):
    """La portadita de 46 px: en pausa se achica un poquito (con rebote)."""

    def __init__(self, size=46, radius=12, parent=None):
        super().__init__(parent)
        self.S, self.R = size, radius
        self.setFixedSize(size + 8, size + 10)
        self.pix: QPixmap | None = None
        self._scale = 1.0
        self._a = QVariantAnimation(self)
        self._a.setDuration(600)
        self._a.setEasingCurve(SPRING)
        self._a.valueChanged.connect(self._on)

    def _on(self, v):
        self._scale = float(v)
        self.update()

    def set_pixmap(self, pix):
        self.pix = pix
        self.update()

    def set_paused(self, paused):
        target = 0.9 if paused else 1.0
        running = self._a.state() == QVariantAnimation.Running
        if (running and self._a.endValue() == target) or (not running and abs(self._scale - target) < 1e-3):
            return
        self._a.stop()
        self._a.setStartValue(self._scale)
        self._a.setEndValue(target)
        self._a.start()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        S = self.S * self._scale
        x, y = 4 + (self.S - S) / 2, 2 + (self.S - S) / 2
        r = QRectF(x, y, S, S)
        for k in range(5):   # sombrita
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, 16 - k * 3))
            p.drawRoundedRect(r.adjusted(-k, -k + 3, k, k + 4), self.R + k, self.R + k)
        path = QPainterPath()
        path.addRoundedRect(r, self.R, self.R)
        p.setClipPath(path)
        if self.pix is not None and not self.pix.isNull():
            p.drawPixmap(r, _cover_fill(self.pix, self.S * 2, self.S * 2), QRectF(0, 0, self.S * 2, self.S * 2))
        else:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, QColor(theme.GLASS_GRAD_1))
            g.setColorAt(1, QColor(theme.GLASS_GRAD_2))
            p.fillRect(r, g)
        p.end()


class TitleEq(QWidget):
    """Tres barritas al lado de "Cumito" que bailan mientras suena algo."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(13, 12)
        self._t = 0.0
        self.active = False
        self._timer = QTimer(self)
        self._timer.setInterval(110)    # ~9 cuadros por segundo: se ve vivo y no gasta
        self._timer.timeout.connect(self._tick)

    def set_active(self, on):
        on = bool(on)
        if on == self.active:
            return
        self.active = on
        (self._timer.start() if on else self._timer.stop())
        self.update()

    def hideEvent(self, ev):
        self._timer.stop()
        super().hideEvent(ev)

    def showEvent(self, ev):
        if self.active:
            self._timer.start()
        super().showEvent(ev)

    def _tick(self):
        self._t += 0.11
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor("#C9B4F8"))
        for i in range(3):
            if self.active:
                h = 3 + 8 * (0.5 + 0.5 * math.sin(2 * math.pi * (self._t + i * 0.35)))
            else:
                h = 3
            p.drawRoundedRect(QRectF(i * 5, 12 - h, 3, h), 1.5, 1.5)
        p.end()


class Burst(QWidget):
    """El estallido de puntitos rosados alrededor del corazón."""

    def __init__(self, parent, center, color="#FF8FA8"):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setGeometry(QRect(int(center.x() - 30), int(center.y() - 30), 60, 60))
        self.color = QColor(color)
        self._t = 0.0
        a = QVariantAnimation(self)
        a.setDuration(700)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.setEasingCurve(QEasingCurve.OutCubic)
        a.valueChanged.connect(self._on)
        a.finished.connect(self.deleteLater)
        self._a = a
        self.show()
        self.raise_()
        a.start()

    def _on(self, v):
        self._t = float(v)
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setPen(Qt.NoPen)
        c = QColor(self.color)
        c.setAlphaF(max(0.0, 1.0 - self._t))
        p.setBrush(c)
        for k in range(6):
            ang = math.radians(k * 60 - 90)
            d = 6 + 22 * self._t
            s = 5 * (1 - 0.6 * self._t)
            p.drawEllipse(QPointF(30 + d * math.cos(ang), 30 + d * math.sin(ang)), s / 2, s / 2)
        p.end()
