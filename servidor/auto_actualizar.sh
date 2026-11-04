#!/usr/bin/env bash
# Lo corre la VM sola cada 10 minutos (cumito-actualizar.timer).
#
# Trae lo último de GitHub (carpeta servidor/). Si hay algo nuevo:
#   - si está sonando música (o hay una canción en pausa), NO toca nada:
#     espera a que se termine, para no cortarle la música a nadie;
#   - si no suena nada, lo copia encima y reinicia Cumito (solo si cambió
#     algo del bot de verdad).
# Si alguien tuviera música sonando más de 24 horas seguidas, se actualiza
# igual: Cumito anota en qué segundo iba y lo retoma solo tras reiniciar.
#
# Nunca toca config.json, cookies.txt, history.json, session.json,
# activity.json ni el .venv: eso vive solo en la VM.
# Una vez al día también pone al día yt-dlp (con la misma regla de no cortar).
set -euo pipefail
CARPETA="${CUMITO_CARPETA:?}"
DUENO="${CUMITO_DUENO:?}"
REPO_DIR="/home/$DUENO/.cumito-repo"
URL="${CUMITO_URL:-https://github.com/ayr09k/cumito.git}"
ESPERA_MAX_S=$((24 * 60 * 60))
PENDIENTE="$CARPETA/.actualizacion_pendiente"
como() { runuser -u "$DUENO" -- "$@"; }

if [ ! -d "$REPO_DIR/.git" ]; then
  como git clone -q --depth 1 "$URL" "$REPO_DIR"
fi
como git -C "$REPO_DIR" fetch -q --depth 1 origin main
como git -C "$REPO_DIR" reset -q --hard origin/main

# 1) este mismo script se mantiene al día (y sigue con la versión nueva)
NUEVO="$REPO_DIR/servidor/auto_actualizar.sh"
if [ -z "${CUMITO_YA_NUEVO:-}" ] && [ -f "$NUEVO" ] && ! cmp -s "$NUEVO" "$0"; then
  install -m 755 "$NUEVO" "$0"
  CUMITO_YA_NUEVO=1 exec "$0"
fi

# 2) ¿qué cambió? (sin copiar nada todavía)
sincronizar() {  # $1 = "ver" (solo listar) o "copiar"
  como python3 - "$REPO_DIR/servidor" "$CARPETA" "$1" <<'PY'
import filecmp, os, shutil, sys
src, dst, modo = sys.argv[1], sys.argv[2], sys.argv[3]
NUNCA = {"config.json", "cookies.txt", "history.json", "session.json", "activity.json",
         "ffmpeg.log", ".ytdlp_dia", ".actualizacion_pendiente"}
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
        if modo == "copiar":
            os.makedirs(os.path.dirname(b), exist_ok=True)
            shutil.copy2(a, b)
        print(os.path.relpath(b, dst))
PY
}
CAMBIOS="$(sincronizar ver)"
MARCA="$CARPETA/.ytdlp_dia"
HOY="$(date +%F)"
TOCA_YTDLP=0
[ "$(cat "$MARCA" 2>/dev/null || true)" != "$HOY" ] && TOCA_YTDLP=1

if [ -z "$CAMBIOS" ] && [ "$TOCA_YTDLP" = 0 ]; then
  rm -f "$PENDIENTE"
  echo "Sin cambios."
  exit 0
fi

# 3) ¿está sonando algo? (Cumito lo anota en session.json)
SONANDO="$(como python3 - "$CARPETA/session.json" <<'PY'
import json, sys
try:
    print(1 if json.load(open(sys.argv[1], encoding="utf-8")).get("current") else 0)
except Exception:
    print(0)
PY
)"
if [ "$SONANDO" = 1 ] && systemctl is-active -q cumito; then
  [ -f "$PENDIENTE" ] || date +%s | como tee "$PENDIENTE" >/dev/null
  DESDE="$(cat "$PENDIENTE" 2>/dev/null || date +%s)"
  if [ $(( $(date +%s) - DESDE )) -lt "$ESPERA_MAX_S" ]; then
    echo "Hay música sonando: la actualización espera a que termine."
    exit 0
  fi
  echo "Lleva más de 24 h esperando: se actualiza igual (Cumito retoma la canción solo)."
fi

# 4) actualizar
REINICIAR=0
REQ_ANTES="$(md5sum "$CARPETA/requirements.txt" 2>/dev/null | cut -d' ' -f1 || true)"
COPIADOS="$(sincronizar copiar)"
chmod +x "$CARPETA"/*.sh 2>/dev/null || true
REQ_DESPUES="$(md5sum "$CARPETA/requirements.txt" | cut -d' ' -f1)"
if [ "$REQ_ANTES" != "$REQ_DESPUES" ]; then
  como "$CARPETA/.venv/bin/pip" install -q -r "$CARPETA/requirements.txt"
  REINICIAR=1
fi
# solo se reinicia si cambió algo del bot (no por un LEEME o un script)
if printf '%s\n' "$COPIADOS" | grep -qE '^(cumito_bot/|run\.py$)'; then
  REINICIAR=1
fi
if [ "$TOCA_YTDLP" = 1 ]; then
  ANTES="$(como "$CARPETA/.venv/bin/pip" show yt-dlp 2>/dev/null | grep -i '^version' || true)"
  como "$CARPETA/.venv/bin/pip" install -q --upgrade "yt-dlp[default,deno]" || true
  DESPUES="$(como "$CARPETA/.venv/bin/pip" show yt-dlp 2>/dev/null | grep -i '^version' || true)"
  [ "$ANTES" != "$DESPUES" ] && REINICIAR=1
  echo "$HOY" | como tee "$MARCA" >/dev/null
fi
rm -f "$PENDIENTE"

if [ "$REINICIAR" = 1 ]; then
  echo "Cumito actualizado:"; printf '%s\n' "$COPIADOS"
  systemctl restart cumito
else
  echo "Archivos al día (sin reiniciar):"; printf '%s\n' "$COPIADOS"
fi
