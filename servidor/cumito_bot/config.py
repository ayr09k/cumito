"""
Configuración persistente del servidor: el token del bot y el servidor/
canal de Discord. Vive en config.json, al lado de run.py (no escondido en
una carpeta de usuario) para que sea fácil de encontrar y editar a mano
por SSH si hace falta."""
import json
from pathlib import Path

CFG_PATH = Path(__file__).resolve().parent.parent / "config.json"

DEFAULTS = {
    "token": "",
    "guild_id": "",
    "channel_id": "",
    "host_display_name": "",
}


def load():
    if CFG_PATH.exists():
        try:
            data = json.loads(CFG_PATH.read_text(encoding="utf-8"))
            return {**DEFAULTS, **data}
        except Exception:
            pass
    return dict(DEFAULTS)


def save(data):
    CFG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def is_complete(cfg):
    # el canal de voz es opcional: el bot entra donde esté la gente
    return bool(cfg.get("token") and cfg.get("guild_id"))
