import json
from pathlib import Path

CFG_PATH = Path.home() / ".cumito.json"

# El servidor del grupo (la VM de Oracle). Viene puesto de fábrica, así que
# nadie tiene que escribirlo. Si algún día cambia, cada quien lo puede
# cambiar desde Ajustes -> "Cambiar servidor", o se cambia aquí y se
# reconstruye la app.
from .build_info import SERVER as DEFAULT_SERVER  # viene de fábrica (lo pone GitHub al armar)

DEFAULTS = {
    "host_address": "",   # vacío = usar DEFAULT_SERVER
    "display_name": "",
    "recent_searches": [],
}


def load():
    data = dict(DEFAULTS)
    if CFG_PATH.exists():
        try:
            data.update(json.loads(CFG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
    if not data.get("host_address"):
        data["host_address"] = DEFAULT_SERVER
    return data


def save(data):
    data = dict(data)
    # el servidor de fábrica no se guarda: así, si algún día cambia y se
    # reconstruye la app, todos toman el nuevo solos.
    if data.get("host_address") == DEFAULT_SERVER:
        data["host_address"] = ""
    try:
        CFG_PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass
