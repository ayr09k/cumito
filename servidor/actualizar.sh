#!/usr/bin/env bash
# Actualiza yt-dlp (lo que saca la música de YouTube/SoundCloud) y reinicia
# Cumito. YouTube cambia seguido y yt-dlp saca arreglos casi cada semana:
# si de repente muchas canciones fallan, corre esto primero.
#     bash actualizar.sh
set -e
cd "$(dirname "$0")"
.venv/bin/pip install --upgrade "yt-dlp[default,deno]"
sudo systemctl restart cumito
sleep 6
sudo journalctl -u cumito -n 8 --no-pager
