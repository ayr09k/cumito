"""
Actualizaciones automáticas de Cumito.

Al abrir la app, se pregunta a GitHub cuál es la última versión publicada
(github.com/ayr09k/cumito/releases). Si es más nueva que esta, la ventana
muestra "Nueva versión · Actualizar". Al aceptar, se descarga el instalador
nuevo con su barrita de progreso y se ejecuta en modo "--actualizar": instala
encima, sin preguntar nada, y vuelve a abrir Cumito.

Todo corre en segundo plano; si no hay internet o GitHub no responde, la app
sigue normal sin avisar nada.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .build_info import VERSION

try:
    import requests
except ImportError:  # pragma: no cover
    requests = None

REPO = "ayr09k/cumito"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
ASSET_NAME = "Instalar-Cumito.exe"


def _parse(v: str):
    parts = []
    for x in str(v).lstrip("vV").split("-")[0].split("."):
        try:
            parts.append(int(x))
        except ValueError:
            parts.append(0)
    return tuple(parts + [0] * (3 - len(parts)))[:3]


def is_newer(remote: str, local: str = VERSION) -> bool:
    if local.endswith("-dev"):
        return False  # corriendo desde el código, no desde un instalador
    return _parse(remote) > _parse(local)


def install_dir() -> Path | None:
    """Dónde está instalado este Cumito (solo cuando corre como .exe)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return None


class Updater(QObject):
    available = Signal(str, str)          # (versión, url del instalador)
    progress = Signal(float)              # 0..1 mientras descarga
    failed = Signal(str)
    ready = Signal(str)                   # ruta del instalador descargado

    def check(self):
        if requests is None or install_dir() is None:
            return
        threading.Thread(target=self._check, daemon=True).start()

    def _check(self):
        try:
            r = requests.get(LATEST_URL, timeout=8, headers={"Accept": "application/vnd.github+json"})
            if r.status_code != 200:
                return
            data = r.json()
            version = (data.get("tag_name") or "").lstrip("vV")
            url = next((a.get("browser_download_url") for a in data.get("assets") or []
                        if a.get("name") == ASSET_NAME), None)
            if version and url and is_newer(version):
                self.available.emit(version, url)
        except Exception:
            pass  # sin internet / GitHub caído: no se molesta a nadie

    def download(self, url):
        threading.Thread(target=self._download, args=(url,), daemon=True).start()

    def _download(self, url):
        dest = Path(tempfile.gettempdir()) / "Cumito_actualizacion" / ASSET_NAME
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with requests.get(url, stream=True, timeout=30) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length") or 0)
                got = 0
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(1024 * 256):
                        if not chunk:
                            continue
                        f.write(chunk)
                        got += len(chunk)
                        if total:
                            self.progress.emit(got / total)
            self.ready.emit(str(dest))
        except Exception as e:
            self.failed.emit(str(e)[:120])


def run_installer_and_quit(installer_path: str):
    """Abre el instalador en modo actualización (instala aquí mismo y vuelve
    a abrir Cumito). La app se cierra para que sus archivos se puedan
    reemplazar."""
    target = install_dir()
    args = [installer_path, "--actualizar", str(target) if target else ""]
    kw = {}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    subprocess.Popen(args, **kw)
