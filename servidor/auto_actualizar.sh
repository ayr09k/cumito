#!/usr/bin/env bash
# Lo corre la VM sola cada 10 minutos (cumito-actualizar.timer).
# Trae lo último de GitHub (carpeta servidor/) y, SOLO si algo cambió,
# lo copia encima y reinicia Cumito. Nunca toca config.json, cookies.txt,
# history.json ni el .venv: eso vive solo en la VM.
# Además, una vez al día pone al día yt-dlp (YouTube cambia seguido).
set -euo pipefail
CARPETA="${CUMITO_CARPETA:?}"
DUENO="${CUMITO_DUENO:?}"
REPO_DIR="/home/$DUENO/.cumito-repo"
URL="${CUMITO_URL:-https://github.com/ayr09k/cumito.git}"
como() { runuser -u "$DUENO" -- "$@"; }

if [ ! -d "$REPO_DIR/.git" ]; then
  como git clone -q --depth 1 "$URL" "$REPO_DIR"
fi
como git -C "$REPO_DIR" fetch -q --depth 1 origin main
como git -C "$REPO_DIR" reset -q --hard origin/main

REQ_ANTES="$(md5sum "$CARPETA/requirements.txt" 2>/dev/null | cut -d' ' -f1 || true)"
# copia solo los archivos que cambiaron (imprime cuáles)
CAMBIOS="$(como python3 - "$REPO_DIR/servidor" "$CARPETA" <<'PY'
import filecmp, os, shutil, sys
src, dst = sys.argv[1], sys.argv[2]
NUNCA = {"config.json", "cookies.txt", "history.json", "session.json", "activity.json", "ffmpeg.log", ".ytdlp_dia"}
for root, dirs, files in os.walk(src):
    dirs[:] = [d for d in dirs if d not in (".venv", "__pycache__")]
    rel = os.path.relpath(root, src)
    for f in files:
        if f in NUNCA or f.endswith(".pyc"):
            continue
        a = os.path.join(root, f)
        b = os.path.normpath(os.path.join(dst, rel, f))
        if os.path.exists(b) and filecmp.cmp(a, b, shallow=False):
            continue
        os.makedirs(os.path.dirname(b), exist_ok=True)
        shutil.copy2(a, b)
        print(os.path.relpath(b, dst))
PY
)"
REQ_DESPUES="$(md5sum "$CARPETA/requirements.txt" | cut -d' ' -f1)"
chmod +x "$CARPETA"/*.sh 2>/dev/null || true

REINICIAR=0
if [ "$REQ_ANTES" != "$REQ_DESPUES" ]; then
  como "$CARPETA/.venv/bin/pip" install -q -r "$CARPETA/requirements.txt"
  REINICIAR=1
fi
[ -n "$CAMBIOS" ] && REINICIAR=1

# yt-dlp una vez al día
MARCA="$CARPETA/.ytdlp_dia"
HOY="$(date +%F)"
if [ "$(cat "$MARCA" 2>/dev/null || true)" != "$HOY" ]; then
  ANTES="$(como "$CARPETA/.venv/bin/pip" show yt-dlp 2>/dev/null | grep -i '^version' || true)"
  como "$CARPETA/.venv/bin/pip" install -q --upgrade "yt-dlp[default,deno]" || true
  DESPUES="$(como "$CARPETA/.venv/bin/pip" show yt-dlp 2>/dev/null | grep -i '^version' || true)"
  [ "$ANTES" != "$DESPUES" ] && REINICIAR=1
  echo "$HOY" | como tee "$MARCA" >/dev/null
fi

# este mismo script también se mantiene al día
NUEVO="$REPO_DIR/servidor/auto_actualizar.sh"
if [ -f "$NUEVO" ] && ! cmp -s "$NUEVO" "$0"; then
  install -m 755 "$NUEVO" "$0" || true
fi

if [ "$REINICIAR" = 1 ]; then
  echo "Cumito actualizado:"; echo "$CAMBIOS"
  systemctl restart cumito
else
  echo "Sin cambios."
fi
