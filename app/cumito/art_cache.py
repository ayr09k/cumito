"""
ArtCache: descarga la portada de cada canción (la miniatura que ya nos da
yt-dlp) en segundo plano y la cachea como QPixmap, para no volver a pedirla.

Nota de rendimiento: NO difuminamos nada aquí. El efecto "glass" de los
paneles (barra de título, bandeja de playlist, buscador) se logra con
transparencia simple (alpha), sin ningún desenfoque -- ni en vivo ni
precalculado. Eso ya evita por completo el único costo real de un efecto
"glassmorphism" de verdad, así que esto corre tranquilo hasta en un equipo
modesto: lo único que se hace por canción es bajar una imagen chiquita una
vez y guardarla.

Nota técnica: QPixmap no es seguro de crear/tocar fuera del hilo principal
(usa recursos gráficos de la plataforma). Por eso el hilo de descarga solo
arma un QImage (ese sí es seguro en cualquier hilo) y la conversión a
QPixmap pasa siempre por una señal, que Qt entrega en el hilo principal.
"""
from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QByteArray, Signal
from PySide6.QtGui import QImage, QPixmap

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None


class ArtCache(QObject):
    loaded = Signal(str, QPixmap)       # (url, pixmap) -- para quien usa la caché
    _raw_ready = Signal(str, QImage)    # interno: desde el hilo de descarga

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cache: dict[str, QPixmap] = {}
        self._pending: set[str] = set()
        self._raw_ready.connect(self._on_raw_ready)

    def get(self, url: str | None) -> QPixmap | None:
        if not url:
            return None
        return self._cache.get(url)

    def put(self, key: str, img: QImage):
        """Guardar una imagen que no vino de internet (p. ej. la portada de un
        Disco, que manda el servidor)."""
        pix = QPixmap.fromImage(img)
        if not pix.isNull():
            self._cache[key] = pix
            self.loaded.emit(key, pix)

    def request(self, url: str | None):
        """Pide que se cargue una portada. Si ya está en caché no hace nada
        (set_state puede llamarla cada vez que llega un estado nuevo, sin
        preocuparse por pedir de más)."""
        if (not url or url in self._cache or url in self._pending or requests is None
                or not url.startswith(("http://", "https://"))):
            return
        self._pending.add(url)
        threading.Thread(target=self._fetch, args=(url,), daemon=True).start()

    def _fetch(self, url: str):
        """Corre en un hilo aparte: solo descarga bytes y arma un QImage,
        nada de QPixmap acá."""
        try:
            resp = requests.get(url, timeout=8)
            resp.raise_for_status()
            img = QImage()
            if img.loadFromData(QByteArray(resp.content)) and not img.isNull():
                self._raw_ready.emit(url, img)
                return
        except Exception:
            pass
        self._pending.discard(url)

    def _on_raw_ready(self, url: str, img: QImage):
        """Esta sí corre en el hilo principal -- la señal cruza de hilo
        sola, Qt se encarga. Acá recién se crea el QPixmap."""
        self._pending.discard(url)
        pix = QPixmap.fromImage(img)
        if not pix.isNull():
            self._cache[url] = pix
            self.loaded.emit(url, pix)
