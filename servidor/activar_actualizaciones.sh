#!/usr/bin/env bash
# Se corre UNA sola vez en la VM. Deja a Cumito actualizándose solo desde
# GitHub cada 10 minutos. Uso (una línea, dentro de la VM):
#   curl -fsSL https://raw.githubusercontent.com/ayr09k/cumito/main/servidor/activar_actualizaciones.sh | bash
set -euo pipefail
DUENO="$(id -un)"
CARPETA="$(systemctl show -p WorkingDirectory --value cumito 2>/dev/null || true)"
[ -n "$CARPETA" ] && [ -d "$CARPETA" ] || CARPETA="$HOME/CumitoServidor"
if [ ! -f "$CARPETA/run.py" ]; then
  echo "No encontré Cumito en $CARPETA. ¿Ya corriste instalar.sh?"; exit 1
fi
echo "Cumito está en: $CARPETA"

sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq git >/dev/null

# el script que corre cada 10 min (vive fuera de la carpeta, para poder
# actualizar la carpeta sin pisarse a sí mismo)
curl -fsSL https://raw.githubusercontent.com/ayr09k/cumito/main/servidor/auto_actualizar.sh \
  | sudo tee /usr/local/bin/cumito-auto-actualizar >/dev/null
sudo chmod +x /usr/local/bin/cumito-auto-actualizar

sudo tee /etc/systemd/system/cumito-actualizar.service >/dev/null <<UNIT
[Unit]
Description=Cumito - traer actualizaciones de GitHub
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
Environment=CUMITO_CARPETA=$CARPETA
Environment=CUMITO_DUENO=$DUENO
ExecStart=/usr/local/bin/cumito-auto-actualizar
UNIT

sudo tee /etc/systemd/system/cumito-actualizar.timer >/dev/null <<UNIT
[Unit]
Description=Cumito - revisar actualizaciones cada 10 minutos

[Timer]
OnBootSec=2min
OnUnitActiveSec=10min
Persistent=true

[Install]
WantedBy=timers.target
UNIT

sudo systemctl daemon-reload
sudo systemctl enable --now cumito-actualizar.timer >/dev/null
echo "Primera revisión..."
sudo systemctl start cumito-actualizar.service || true
sudo journalctl -u cumito-actualizar -n 6 --no-pager -o cat || true
echo
echo "LISTO. Cumito se actualiza solo desde GitHub cada 10 minutos."
