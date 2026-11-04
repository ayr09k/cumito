"""
Lo que hace el instalador por dentro, sin nada de ventanas (así se puede
probar solo): sacar la app del paquete, crear accesos directos y cerrar
Cumito si estaba abierto.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path

APP_EXE = "Cumito.exe"
APP_NAME = "Cumito"
CREATE_NO_WINDOW = 0x08000000  # que ningún comando abra una ventana negra


def payload_path() -> Path:
    """El paquete con la app, metido adentro del instalador."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / "payload" / "cumito_app.zip"


def _run_hidden(args):
    kw = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
    if os.name == "nt":
        kw["creationflags"] = CREATE_NO_WINDOW
    try:
        return subprocess.run(args, timeout=30, **kw).returncode
    except Exception:
        return -1


def close_running_app():
    """Si Cumito está abierto, sus archivos están en uso y no se pueden
    reemplazar: se cierra antes de instalar."""
    if os.name == "nt":
        _run_hidden(["taskkill", "/F", "/IM", APP_EXE])
        time.sleep(0.6)


def remove_previous(target: Path, log):
    """Quita la versión anterior de la app (no toca la configuración del
    usuario, que vive en su carpeta personal, no aquí)."""
    for name in (APP_EXE, "archivos"):
        p = target / name
        if p.is_dir():
            log(f"Quitando la versión anterior: {name}\\")
            shutil.rmtree(p, ignore_errors=True)
        elif p.exists():
            log(f"Quitando la versión anterior: {name}")
            try:
                p.unlink()
            except Exception:
                pass


def extract(zip_path: Path, target: Path, progress, log):
    """Saca todos los archivos, avisando el avance real (archivo por archivo,
    ponderado por tamaño para que la barra no se trabe en los grandes)."""
    target.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as z:
        members = [m for m in z.infolist() if not m.is_dir()]
        total = sum(max(1, m.file_size) for m in members) or 1
        done = 0
        last_log = 0.0
        root = target.resolve()
        for i, m in enumerate(members, 1):
            dest = (target / m.filename).resolve()
            if root not in dest.parents and dest != root:
                continue  # nada fuera de la carpeta de instalación
            dest.parent.mkdir(parents=True, exist_ok=True)
            with z.open(m) as src, open(dest, "wb") as out:
                shutil.copyfileobj(src, out, 1024 * 256)
            done += max(1, m.file_size)
            progress(done / total)
            now = time.monotonic()
            # no se anota cada uno (son miles): unos pocos por segundo
            if now - last_log > 0.12 or i == len(members):
                log(f"Copiando {m.filename}")
                last_log = now
        return len(members)


def _ps_quote(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def create_shortcut(lnk_path: Path, target_exe: Path) -> bool:
    """Crea un acceso directo de Windows (.lnk) sin ventanas negras."""
    if os.name != "nt":
        return False
    lnk_path.parent.mkdir(parents=True, exist_ok=True)
    script = (
        f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut({_ps_quote(lnk_path)});"
        f"$s.TargetPath={_ps_quote(target_exe)};"
        f"$s.WorkingDirectory={_ps_quote(target_exe.parent)};"
        f"$s.IconLocation={_ps_quote(str(target_exe) + ',0')};"
        f"$s.Description='Cumito';"
        "$s.Save()"
    )
    return _run_hidden(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                        "-Command", script]) == 0


def start_menu_dir() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs"


def launch(target_exe: Path):
    kw = {"cwd": str(target_exe.parent)}
    if os.name == "nt":
        kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | NEW_PROCESS_GROUP
    subprocess.Popen([str(target_exe)], **kw)
