"""
La lista de la playlist, en dos grupos:

  - arriba, LISTAS PARA SONAR (con un fondo morado suave): las canciones ya
    preparadas, en el orden en que van a sonar. Se pueden reordenar
    agarrándolas y soltándolas donde uno quiera.
  - una línea gris, y abajo SIN PREPARAR: el resto (p. ej. de una playlist
    de 200). Al tocar una, se prepara y sube sola al grupo de arriba.

Cada canción es una "celda" que se reutiliza: cuando la lista cambia (pasa
a la siguiente, se agrega o se quita una), solo se agrega, quita o mueve esa
celda; no se vuelve a armar toda la lista (antes con 200 canciones se veía
cómo se apilaban otra vez).
"""
from __future__ import annotations

import time

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QColor, QCursor, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import theme

ROW_H = 46


class _Placeholder(QWidget):
    """El hueco donde va a caer la canción que se está arrastrando."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(ROW_H)

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        p.setBrush(QColor(142, 108, 242, 30))
        pen = QPen(QColor(170, 140, 255, 150), 1.4, Qt.DashLine)
        p.setPen(pen)
        p.drawRoundedRect(r, 10, 10)
        p.end()


class _Ghost(QWidget):
    """La canción "sostenida" mientras se arrastra: un poquito más grande,
    con sombra, borde morado y apenas inclinada."""

    def __init__(self, pixmap: QPixmap, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._pix = pixmap
        self._lift = 0.0
        m = 16
        self.resize(pixmap.width() + 2 * m, pixmap.height() + 2 * m)
        self._m = m
        a = QVariantAnimation(self)
        a.setDuration(140)
        a.setStartValue(0.0)
        a.setEndValue(1.0)
        a.valueChanged.connect(self._set_lift)
        self._anim = a
        a.start()
        self.show()
        self.raise_()

    def _set_lift(self, v):
        self._lift = float(v)
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.SmoothPixmapTransform, True)
        w, h = self._pix.width(), self._pix.height()
        p.translate(self.width() / 2, self.height() / 2)
        p.rotate(-1.4 * self._lift)
        s = 1.0 + 0.04 * self._lift
        p.scale(s, s)
        r = QRectF(-w / 2, -h / 2, w, h)
        for k, a in ((10, 18), (6, 26), (3, 34)):        # sombra
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(0, 0, 0, int(a * self._lift)))
            p.drawRoundedRect(r.adjusted(-k, -k + 4, k, k + 4), 12 + k, 12 + k)
        path = QPainterPath()
        path.addRoundedRect(r, 11, 11)
        p.fillPath(path, QColor(32, 28, 44, 245))
        p.setClipPath(path)
        p.drawPixmap(r.topLeft(), self._pix)
        p.setClipping(False)
        p.setPen(QPen(QColor(170, 140, 255, int(220 * self._lift)), 1.4))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        p.end()


class QueueList(QWidget):
    play = Signal(int)          # uid: ponerla ya
    prepare = Signal(int)       # uid: prepararla
    remove = Signal(int)        # uid: quitarla
    move = Signal(int, int)     # uid, nuevo lugar (dentro de las listas)

    def __init__(self, make_row, art_cache, scroll_area=None, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self._make_row = make_row
        self._art = art_cache
        self._scroll = scroll_area
        self._rows = {}            # uid -> (fila, clave)
        self._now = None           # (fila, clave)
        self._drag = None          # lo que se está arrastrando
        self._deferred = None      # datos que llegaron durante el arrastre
        self._optimistic = None    # (uid, lugar, hasta) tras soltar, mientras llega el servidor

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self._now_box = QVBoxLayout()
        self._now_box.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(self._now_box)

        # --- grupo de listas (fondo morado suave) ---
        self.ready_box = QWidget()
        self.ready_box.setObjectName("readygroup")
        self.ready_box.setAttribute(Qt.WA_StyledBackground, True)
        self.ready_box.setStyleSheet(
            "QWidget#readygroup { background: rgba(142,108,242,0.13); border: 1px solid rgba(142,108,242,0.30);"
            " border-radius: 14px; }"
        )
        rb = QVBoxLayout(self.ready_box)
        rb.setContentsMargins(4, 6, 4, 4)
        rb.setSpacing(0)
        self.ready_head = QLabel("")
        self.ready_head.setStyleSheet(
            "color: rgba(200,185,255,0.85); font-size: 9.5px; font-weight: 800; letter-spacing: 1px;"
            " background: transparent; padding: 0 0 4px 8px;"
        )
        rb.addWidget(self.ready_head)
        self._ready_lay = QVBoxLayout()
        self._ready_lay.setSpacing(2)
        self._ready_lay.setContentsMargins(0, 0, 0, 0)
        rb.addLayout(self._ready_lay)
        lay.addWidget(self.ready_box)

        # --- separador gris + sin preparar ---
        self.sep = QWidget()
        sl = QHBoxLayout(self.sep)
        sl.setContentsMargins(6, 8, 6, 2)
        sl.setSpacing(8)
        line_l = QWidget()
        line_l.setFixedHeight(1)
        line_l.setStyleSheet("background: rgba(255,255,255,0.16);")
        self.sep_label = QLabel("")
        self.sep_label.setStyleSheet(
            f"color:{theme.GLASS_TEXT_MUTE2}; font-size: 9.5px; font-weight: 800; letter-spacing: 1px;"
            " background: transparent;"
        )
        line_r = QWidget()
        line_r.setFixedHeight(1)
        line_r.setStyleSheet("background: rgba(255,255,255,0.16);")
        sl.addWidget(line_l, 1)
        sl.addWidget(self.sep_label)
        sl.addWidget(line_r, 1)
        lay.addWidget(self.sep)
        self._pend_lay = QVBoxLayout()
        self._pend_lay.setSpacing(2)
        self._pend_lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(self._pend_lay)
        lay.addStretch(1)

    # ------------------------------------------------------------------ datos
    def set_data(self, now_playing, queue, flashing):
        if self._drag is not None:
            self._deferred = (now_playing, queue, flashing)
            return
        queue = list(queue or [])
        # tras soltar: si el servidor todavía no confirmó, se respeta lo soltado
        if self._optimistic and time.monotonic() < self._optimistic[2]:
            uid, to, _ = self._optimistic
            idx = next((i for i, t in enumerate(queue) if t.get("uid") == uid), None)
            if idx is not None and idx != to:
                item = queue.pop(idx)
                queue.insert(min(to, len(queue)), item)
            elif idx == to:
                self._optimistic = None
        self.setUpdatesEnabled(False)
        try:
            self._set_now(now_playing)
            ready, pend = [], []
            for t in queue:
                prepared = t.get("prepared", t.get("ready", True))
                (ready if prepared else pend).append(t)
            keep = set()
            ready_rows = [self._row_for(t, "ready", flashing) for t in ready]
            pend_rows = [self._row_for(t, "pending", flashing) for t in pend]
            keep.update(t.get("uid") for t in queue)
            for uid in list(self._rows):
                if uid not in keep:
                    row, _ = self._rows.pop(uid)
                    row.setParent(None)
                    row.deleteLater()
            self._fill(self._ready_lay, ready_rows)
            self._fill(self._pend_lay, pend_rows)
            n_r, n_p = len(ready), len(pend)
            self.ready_box.setVisible(n_r > 0)
            self.ready_head.setText(
                f"LISTAS PARA SONAR · {n_r}" + ("   ·   arrastra para ordenar" if n_r > 1 else ""))
            self.sep.setVisible(n_p > 0)
            self.sep_label.setText(f"SIN PREPARAR · {n_p}")
        finally:
            self.setUpdatesEnabled(True)

    def _set_now(self, np):
        key = None
        if np:
            key = (np.get("title"), np.get("uploader"), bool(self._art.get(np.get("art_url"))))
        if self._now and self._now[1] == key:
            return
        if self._now:
            self._now[0].setParent(None)
            self._now[0].deleteLater()
            self._now = None
        if np:
            row = self._make_row(np, "now", False)
            self._now_box.addWidget(row)
            self._now = (row, key)

    def _row_for(self, t, section, flashing):
        uid = t.get("uid")
        status = "ready" if section == "ready" else ("loading" if t.get("loading") else "pending")
        art = self._art.get(t.get("art_url")) if section == "ready" else None
        if section == "ready":
            self._art.request(t.get("art_url"))
        key = (t.get("title"), t.get("uploader"), t.get("duration"), status, bool(art), uid in flashing)
        old = self._rows.get(uid)
        if old and old[1] == key:
            return old[0]
        if old:
            old[0].setParent(None)
            old[0].deleteLater()
        row = self._make_row(t, status, uid in flashing)
        row.setProperty("uid", uid)
        if status == "ready":
            row.clicked.connect(lambda u=uid: self.play.emit(u))
            row.drag_started.connect(lambda gp, r=row: self._drag_start(r, gp))
            row.drag_moved.connect(self._drag_move)
            row.drag_ended.connect(self._drag_end)
        elif status == "pending":
            row.clicked.connect(lambda u=uid: self.prepare.emit(u))
        row.remove_clicked.connect(lambda u=uid: self.remove.emit(u))
        self._rows[uid] = (row, key)
        return row

    @staticmethod
    def _fill(lay, rows):
        current = [lay.itemAt(i).widget() for i in range(lay.count())]
        if current == rows:
            return
        while lay.count():
            lay.takeAt(0)
        for r in rows:
            lay.addWidget(r)
            r.show()

    # ------------------------------------------------------------------ arrastrar
    # La fila agarrada NO se esconde (si se esconde, Windows deja de avisarle
    # que soltaste el mouse y el arrastre queda colgado): se convierte en el
    # hueco punteado y se va moviendo. Además, mientras dura el arrastre se
    # escucha el mouse en toda la app: soltar en cualquier lado (o perder el
    # foco, o Esc) siempre lo termina.
    PH_STYLE = ("QWidget#trackrow { background: rgba(142,108,242,0.12);"
                " border: 1px dashed rgba(170,140,255,0.75); border-radius: 10px; }")

    def _drag_start(self, row, gpos):
        if self._drag is not None:
            return
        idx = self._ready_lay.indexOf(row)
        if idx < 0 or self._ready_lay.count() < 2:
            return
        win = self.window()
        pix = row.grab()
        top_left = row.mapTo(win, QPoint(0, 0))
        hidden = [c for c in row.findChildren(QWidget) if c.isVisible()]
        for c in hidden:
            c.hide()
        style = row.styleSheet()
        row.setStyleSheet(self.PH_STYLE)
        ghost = _Ghost(pix, win)
        grab_off = win.mapFromGlobal(gpos) - top_left
        self._drag = {"row": row, "from": idx, "ghost": ghost, "hidden": hidden, "style": style,
                      "off": grab_off + QPoint(ghost._m, ghost._m)}
        ghost.move(win.mapFromGlobal(gpos) - self._drag["off"])
        QApplication.setOverrideCursor(Qt.ClosedHandCursor)
        QApplication.instance().installEventFilter(self)
        if not hasattr(self, "_scroll_timer"):
            self._scroll_timer = QTimer(self)
            self._scroll_timer.setInterval(40)
            self._scroll_timer.timeout.connect(self._autoscroll)
        self._scroll_timer.start()

    def eventFilter(self, obj, ev):
        d = self._drag
        if d is not None:
            t = ev.type()
            if t == QEvent.MouseMove:
                try:
                    self._drag_move(ev.globalPosition().toPoint())
                except Exception:
                    self._drag_move(QCursor.pos())
            elif t == QEvent.MouseButtonRelease:
                QTimer.singleShot(0, lambda: self._drag_end(QCursor.pos()))
            elif t == QEvent.ApplicationDeactivate or (t == QEvent.KeyPress and ev.key() == Qt.Key_Escape):
                QTimer.singleShot(0, lambda: self._drag_end(QCursor.pos(), cancel=True))
        return False

    def _drag_move(self, gpos):
        d = self._drag
        if d is None:
            return
        win = self.window()
        d["ghost"].move(win.mapFromGlobal(gpos) - d["off"])
        row = d["row"]
        lay = self._ready_lay
        # dónde caería: según el centro de cada una de las otras filas
        y = self.ready_box.mapFromGlobal(gpos).y()
        others = [lay.itemAt(i).widget() for i in range(lay.count()) if lay.itemAt(i).widget() is not row]
        target = sum(1 for w in others if y > w.mapTo(self.ready_box, QPoint(0, w.height() // 2)).y())
        if lay.indexOf(row) != target:
            lay.removeWidget(row)
            lay.insertWidget(target, row)

    def _autoscroll(self):
        """Si la canción agarrada está pegada al borde de arriba o de abajo
        de la lista (y DENTRO de ella), la lista se desplaza sola, de a
        poquito. Va con su propio reloj, no con cada movimiento del mouse."""
        d = self._drag
        if d is None or self._scroll is None:
            return
        vp = self._scroll.viewport()
        pt = vp.mapFromGlobal(QCursor.pos())
        if not (0 <= pt.x() <= vp.width()) or not (-20 <= pt.y() <= vp.height() + 20):
            return
        bar = self._scroll.verticalScrollBar()
        step = 0
        if pt.y() < 24:
            step = -8
        elif pt.y() > vp.height() - 24:
            step = 8
        if step and bar.minimum() <= bar.value() + step <= bar.maximum():
            bar.setValue(bar.value() + step)
            self._drag_move(QCursor.pos())

    def _drag_end(self, gpos=None, cancel=False):
        d = self._drag
        if d is None:
            return
        self._drag = None
        if hasattr(self, "_scroll_timer"):
            self._scroll_timer.stop()
        QApplication.instance().removeEventFilter(self)
        while QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()
        row = d["row"]
        lay = self._ready_lay
        if cancel and lay.indexOf(row) != d["from"]:
            lay.removeWidget(row)
            lay.insertWidget(d["from"], row)
        to = lay.indexOf(row)
        try:
            row.setStyleSheet(d["style"])
            for c in d["hidden"]:
                c.show()
            row._press = None
            row._dragging = False
        except RuntimeError:
            pass  # la fila ya no existe
        d["ghost"].deleteLater()
        uid = row.property("uid")
        if not cancel and to != d["from"] and uid is not None:
            self._optimistic = (uid, to, time.monotonic() + 2.5)
            self.move.emit(uid, to)
        if self._deferred is not None:
            data, self._deferred = self._deferred, None
            QTimer.singleShot(0, lambda: self.set_data(*data))
