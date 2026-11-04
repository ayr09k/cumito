"""
Estado del servidor (Opciones -> Estado del servidor): la salud de la VM en
vivo. Se actualiza cada 2 segundos SOLO mientras esta pantalla está abierta.

  - un aviso arriba: "Todo bien" / "Un poco cargado" / "Con problemas"
  - tres anillos: procesador, memoria y disco
  - el procesador de los últimos 3 minutos (y si Oracle está limitando la VM)
  - tarjetitas: Discord, canal de voz, apps conectadas, lista, encendido...
  - el registro: los últimos avisos y errores del servidor
"""
from __future__ import annotations

import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from . import theme

GREEN, AMBER, RED = QColor("#3DDC84"), QColor("#F2B23A"), QColor("#FF5A5F")
LILAC = QColor("#C9B4F8")


def _lvl_color(pct):
    if pct is None:
        return QColor(255, 255, 255, 90)
    return GREEN if pct < 60 else (AMBER if pct < 85 else RED)


def _bytes(n):
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB", "MB") else f"{n:.1f} {unit}"
        n /= 1024


def _dur(s):
    s = int(s or 0)
    d, s = divmod(s, 86400)
    h, s = divmod(s, 3600)
    m = s // 60
    if d:
        return f"{d} d {h} h"
    if h:
        return f"{h} h {m} min"
    return f"{m} min"


class Ring(QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setFixedSize(96, 112)
        self._title = title
        self._pct = None
        self._sub = ""

    def set_value(self, pct, sub=""):
        self._pct, self._sub = pct, sub
        self.update()

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(14, 6, 68, 68)
        p.setPen(QPen(QColor(255, 255, 255, 30), 7, Qt.SolidLine, Qt.RoundCap))
        p.drawArc(r, 0, 360 * 16)
        if self._pct is not None:
            col = _lvl_color(self._pct)
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, col.lighter(125))
            g.setColorAt(1, col)
            p.setPen(QPen(g, 7, Qt.SolidLine, Qt.RoundCap))
            p.drawArc(r, 90 * 16, -int(360 * 16 * max(0.0, min(1.0, self._pct / 100))))
        f = QFont(theme.GLASS_FONT_FAMILY)
        f.setPixelSize(16)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor("#FFFFFF"))
        p.drawText(r, Qt.AlignCenter, "–" if self._pct is None else f"{round(self._pct)}%")
        f.setPixelSize(10)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 200))
        p.drawText(QRectF(0, 80, self.width(), 14), Qt.AlignCenter, self._title)
        f.setBold(False)
        f.setPixelSize(9)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 120))
        p.drawText(QRectF(0, 95, self.width(), 14), Qt.AlignCenter, self._sub)
        p.end()


class Spark(QWidget):
    """El procesador de los últimos minutos (y lo que Oracle "roba", en rojo)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(112)
        self._cpu, self._steal = [], []

    def set_data(self, cpu, steal):
        self._cpu, self._steal = list(cpu or []), list(steal or [])
        self.update()

    def _path(self, vals, r, n):
        path = QPainterPath()
        for i, v in enumerate(vals):
            x = r.left() + r.width() * (i + (n - len(vals))) / max(1, n - 1)
            y = r.bottom() - r.height() * max(0.0, min(100.0, v)) / 100
            path.moveTo(x, y) if i == 0 else path.lineTo(x, y)
        return path

    def paintEvent(self, ev):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        card = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        bg = QPainterPath()
        bg.addRoundedRect(card, 14, 14)
        p.fillPath(bg, QColor(255, 255, 255, 14))
        p.setPen(QPen(QColor(255, 255, 255, 22), 1))
        p.drawPath(bg)
        f = QFont(theme.GLASS_FONT_FAMILY)
        f.setPixelSize(10)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 170))
        p.drawText(QRectF(14, 8, 220, 16), Qt.AlignLeft | Qt.AlignVCenter, "PROCESADOR · ÚLTIMOS 3 MIN")
        steal_now = self._steal[-1] if self._steal else 0
        if steal_now >= 5:
            p.setPen(RED)
            p.drawText(QRectF(card.right() - 150, 8, 136, 16), Qt.AlignRight | Qt.AlignVCenter,
                       f"Oracle limitando {round(steal_now)}%")
        r = QRectF(14, 30, card.width() - 26, card.height() - 40)
        p.setPen(QPen(QColor(255, 255, 255, 18), 1, Qt.DashLine))
        for frac in (0.0, 0.5, 1.0):
            y = r.top() + r.height() * frac
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
        n = 90
        if len(self._cpu) >= 2:
            line = self._path(self._cpu, r, n)
            area = QPainterPath(line)
            area.lineTo(r.right(), r.bottom())
            first_x = r.left() + r.width() * (n - len(self._cpu)) / (n - 1)
            area.lineTo(first_x, r.bottom())
            area.closeSubpath()
            g = QLinearGradient(0, r.top(), 0, r.bottom())
            g.setColorAt(0, QColor(142, 108, 242, 110))
            g.setColorAt(1, QColor(142, 108, 242, 0))
            p.fillPath(area, g)
            p.setPen(QPen(LILAC, 1.8))
            p.drawPath(line)
            if any(v >= 2 for v in self._steal):
                p.setPen(QPen(QColor(255, 90, 95, 200), 1.3, Qt.DashLine))
                p.drawPath(self._path(self._steal, r, n))
            last = self._cpu[-1]
            lx = r.right()
            ly = r.bottom() - r.height() * last / 100
            p.setPen(Qt.NoPen)
            p.setBrush(LILAC)
            p.drawEllipse(QPointF(lx, ly), 3.2, 3.2)
        else:
            p.setPen(QColor(255, 255, 255, 110))
            p.drawText(r, Qt.AlignCenter, "Juntando datos…")
        p.end()


class Tile(QWidget):
    def __init__(self, label, parent=None):
        super().__init__(parent)
        self.setObjectName("stile")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("QWidget#stile { background: rgba(255,255,255,0.055); border: 1px solid"
                           " rgba(255,255,255,0.08); border-radius: 12px; }")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(11, 8, 11, 9)
        lay.setSpacing(1)
        self.l = QLabel(label.upper())
        self.l.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE2}; font-size:9px; font-weight:800; letter-spacing:0.8px;"
                             " background:transparent; border:none;")
        self.v = QLabel("–")
        self.v.setStyleSheet("color:#fff; font-size:14px; font-weight:800; background:transparent; border:none;")
        self.s = QLabel("")
        self.s.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE}; font-size:10px; background:transparent; border:none;")
        for w in (self.l, self.v, self.s):
            lay.addWidget(w)

    def set(self, value, sub="", color=None):
        self.v.setText(value)
        self.s.setText(sub)
        self.s.setVisible(bool(sub))
        col = color.name() if isinstance(color, QColor) else (color or "#fff")
        self.v.setStyleSheet(f"color:{col}; font-size:14px; font-weight:800; background:transparent; border:none;")


class StatusView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(2, 2, 8, 16)
        lay.setSpacing(10)

        # aviso general
        self.banner = QWidget()
        self.banner.setObjectName("sbanner")
        self.banner.setAttribute(Qt.WA_StyledBackground, True)
        bl = QHBoxLayout(self.banner)
        bl.setContentsMargins(12, 10, 12, 10)
        bl.setSpacing(10)
        self.dot = QLabel()
        self.dot.setFixedSize(12, 12)
        bl.addWidget(self.dot, 0, Qt.AlignTop)
        bt = QVBoxLayout()
        bt.setSpacing(1)
        self.b_title = QLabel("Conectando con el servidor…")
        self.b_title.setStyleSheet("color:#fff; font-size:14px; font-weight:800; background:transparent;")
        self.b_sub = QLabel("")
        self.b_sub.setWordWrap(True)
        self.b_sub.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE}; font-size:10.5px; background:transparent;")
        bt.addWidget(self.b_title)
        bt.addWidget(self.b_sub)
        bl.addLayout(bt, 1)
        lay.addWidget(self.banner)
        self._paint_banner(QColor(255, 255, 255, 120))

        rings = QHBoxLayout()
        rings.setSpacing(0)
        self.r_cpu, self.r_mem, self.r_disk = Ring("Procesador"), Ring("Memoria"), Ring("Disco")
        for r in (self.r_cpu, self.r_mem, self.r_disk):
            rings.addWidget(r, 1, Qt.AlignHCenter)
        lay.addLayout(rings)

        self.spark = Spark()
        lay.addWidget(self.spark)

        grid = QGridLayout()
        grid.setSpacing(8)
        names = ["Discord", "Canal de voz", "Apps conectadas", "Lista", "Cumito encendido", "Memoria de Cumito",
                 "Swap", "Carga", "Versión del servidor", "yt-dlp"]
        self.t = {n: Tile(n) for n in names}
        for i, n in enumerate(names):
            grid.addWidget(self.t[n], i // 2, i % 2)
        lay.addLayout(grid)

        self.update_note = QLabel("")
        self.update_note.setWordWrap(True)
        self.update_note.setStyleSheet(
            "color:#F2D18A; font-size:11px; background: rgba(242,178,58,0.12); border:1px solid"
            " rgba(242,178,58,0.35); border-radius:10px; padding:8px 10px;")
        self.update_note.hide()
        lay.addWidget(self.update_note)

        head = QLabel("REGISTRO")
        head.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE}; font-size:10px; font-weight:800; letter-spacing:1px;"
                           " background:transparent; padding-top:4px;")
        lay.addWidget(head)
        self.logs = QVBoxLayout()
        self.logs.setSpacing(4)
        lay.addLayout(self.logs)
        lay.addStretch(1)
        self._log_sig = None

    def _paint_banner(self, col: QColor):
        self.banner.setStyleSheet(
            f"QWidget#sbanner {{ background: rgba({col.red()},{col.green()},{col.blue()},0.13);"
            f" border: 1px solid rgba({col.red()},{col.green()},{col.blue()},0.45); border-radius: 14px; }}")
        self.dot.setStyleSheet(f"background:{col.name()}; border-radius:6px;")

    def set_waiting(self, long=False):
        self._paint_banner(QColor(255, 255, 255, 120))
        self.b_title.setText("Esperando al servidor…")
        self.b_sub.setText("Si no responde, puede que el servidor todavía no tenga esta pantalla: se activa "
                           "cuando se actualice." if long else "")

    # ------------------------------------------------------------------
    def set_data(self, d):
        cpu = d.get("cpu")
        hist = d.get("cpu_hist") or []
        steal_hist = d.get("steal_hist") or []
        mem, disk, swap = d.get("mem") or {}, d.get("disk") or {}, d.get("swap") or {}
        mem_pct = 100 * mem.get("used", 0) / mem["total"] if mem.get("total") else None
        disk_pct = 100 * disk.get("used", 0) / disk["total"] if disk.get("total") else None
        self.r_cpu.set_value(cpu, f"{d.get('cores') or '?'} núcleo(s)")
        self.r_mem.set_value(mem_pct, f"{_bytes(mem.get('used'))} de {_bytes(mem.get('total'))}")
        self.r_disk.set_value(disk_pct, f"{_bytes(disk.get('used'))} de {_bytes(disk.get('total'))}")
        self.spark.set_data(hist, steal_hist)

        dc = d.get("discord") or {}
        if dc.get("ready"):
            ping = dc.get("ping")
            self.t["Discord"].set("Conectado", f"ping {ping} ms" if ping is not None else "",
                                  GREEN if (ping or 0) < 250 else AMBER)
        else:
            self.t["Discord"].set("Desconectado", "reconectando…", RED)
        self.t["Canal de voz"].set(dc.get("voice") or "Fuera del canal", d.get("playing") or "nada sonando")
        n = d.get("listeners") or 0
        self.t["Apps conectadas"].set(str(n), "persona" if n == 1 else "personas")
        q = d.get("queue") or {}
        sub = f"{q.get('prepared', 0)} listas"
        if q.get("loading"):
            sub += f" · {q['loading']} preparando"
        if q.get("failed"):
            sub += f" · {q['failed']} con error"
        self.t["Lista"].set(f"{q.get('total', 0)} canciones", sub, AMBER if q.get("failed") else None)
        self.t["Cumito encendido"].set(_dur(d.get("uptime_bot")), f"VM: {_dur(d.get('uptime_vm'))}")
        h = d.get("helpers") or {}
        self.t["Memoria de Cumito"].set(_bytes((d.get("bot_rss") or 0) + (h.get("rss") or 0)),
                                         f"{h.get('n', 0)} ayudante(s) preparando canciones")
        if swap.get("total"):
            sp = 100 * swap.get("used", 0) / swap["total"]
            self.t["Swap"].set(f"{_bytes(swap.get('used'))}", f"de {_bytes(swap.get('total'))}",
                               AMBER if sp > 60 else None)
        else:
            self.t["Swap"].set("Sin swap")
        load = d.get("load") or [0, 0, 0]
        cores = d.get("cores") or 1
        self.t["Carga"].set(f"{load[0]:.2f}", f"5 min {load[1]:.2f} · 15 min {load[2]:.2f}",
                            AMBER if load[0] > cores * 1.5 else None)
        v = d.get("versions") or {}
        self.t["Versión del servidor"].set(v.get("server") or "?")
        self.t["yt-dlp"].set(v.get("yt_dlp") or "?")
        self.update_note.setVisible(bool(d.get("update_pending")))
        self.update_note.setText("Hay una actualización del servidor esperando a que pare la música.")

        # resumen
        problems, warnings = [], []
        if not dc.get("ready"):
            problems.append("Cumito no está conectado a Discord.")
        if mem_pct is not None and mem_pct > 92:
            problems.append("La memoria está casi llena.")
        recent = hist[-15:]
        if recent and sum(recent) / len(recent) > 90:
            warnings.append("El procesador está al máximo.")
        st = steal_hist[-15:]
        if st and sum(st) / len(st) > 25:
            warnings.append("Oracle está limitando la VM (es gratis y tiene un tope).")
        if q.get("failed"):
            warnings.append("Algunas canciones no se pudieron preparar.")
        now = d.get("time") or time.time()
        if any(x.get("lvl") == "ERROR" and now - x.get("t", 0) < 300 for x in d.get("logs") or []):
            warnings.append("Hubo errores en los últimos 5 minutos (mira el registro).")
        if problems:
            self._paint_banner(RED)
            self.b_title.setText("Con problemas")
            self.b_sub.setText(" ".join(problems + warnings))
        elif warnings:
            self._paint_banner(AMBER)
            self.b_title.setText("Un poco cargado")
            self.b_sub.setText(" ".join(warnings))
        else:
            self._paint_banner(GREEN)
            self.b_title.setText("Todo bien")
            self.b_sub.setText("La VM responde normal.")

        self._set_logs(d.get("logs") or [])

    def _set_logs(self, logs):
        sig = tuple((x.get("t"), x.get("msg")) for x in logs[-25:])
        if sig == self._log_sig:
            return
        self._log_sig = sig
        while self.logs.count():
            it = self.logs.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if not logs:
            empty = QLabel("Sin avisos por ahora.")
            empty.setStyleSheet(f"color:{theme.GLASS_TEXT_MUTE2}; font-size:11px; background:transparent;")
            self.logs.addWidget(empty)
            return
        colors = {"ERROR": "#FF5A5F", "CRITICAL": "#FF5A5F", "WARNING": "#F2B23A", "INFO": "#9A97A6"}
        names = {"ERROR": "ERROR", "CRITICAL": "ERROR", "WARNING": "AVISO", "INFO": "INFO"}
        for x in reversed(logs[-25:]):
            row = QWidget()
            row.setStyleSheet("background:transparent;")
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(7)
            t = QLabel(time.strftime("%H:%M:%S", time.localtime(x.get("t", 0))))
            t.setStyleSheet("color: rgba(255,255,255,0.45); font-family: Consolas, monospace; font-size:10px;"
                            " background:transparent;")
            h.addWidget(t, 0, Qt.AlignTop)
            c = colors.get(x.get("lvl"), "#9A97A6")
            pill = QLabel(names.get(x.get("lvl"), x.get("lvl", "")))
            pill.setStyleSheet(f"color:{c}; border:1px solid {c}; border-radius:6px; font-size:8.5px;"
                               " font-weight:800; padding:0 4px; background:transparent;")
            h.addWidget(pill, 0, Qt.AlignTop)
            m = QLabel(x.get("msg", ""))
            m.setWordWrap(True)
            m.setStyleSheet("color: rgba(255,255,255,0.82); font-size:10.5px; background:transparent;")
            h.addWidget(m, 1)
            self.logs.addWidget(row)
