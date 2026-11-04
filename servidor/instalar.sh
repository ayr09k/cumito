#!/usr/bin/env bash
# Instala y deja corriendo Cumito-servidor en una VM Ubuntu (por ejemplo,
# una "Always Free" de Oracle Cloud). Se corre UNA sola vez, desde esta
# carpeta:   bash instalar.sh
#
# Hace todo esto solo:
#   1. Instala lo que hace falta (Python, ffmpeg, opus).
#   2. Abre el puerto 8765 en el firewall de la propia VM.
#   3. Te pregunta el token del bot y los IDs de Discord (una vez).
#   4. Lo deja corriendo 24/7 como servicio: arranca solo si la VM se
#      reinicia y se levanta solo si llegara a caerse.
set -e
cd "$(dirname "$0")"
CARPETA="$(pwd)"
USUARIO="$(whoami)"
PUERTO=8765

echo
echo "== [1/4] Instalando dependencias del sistema =="
sudo apt-get update -y
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y python3-pip python3-venv ffmpeg libopus0 iptables-persistent curl

# VM chiquitas (como la E2.1.Micro de Oracle, con 1 GB de RAM): se les da
# 2 GB de memoria extra en disco (swap) para que instalar y reproducir no
# se queden sin memoria. En VMs con más RAM esto no hace nada.
MEM_KB=$(grep MemTotal /proc/meminfo | awk '{print $2}')
if [ "$MEM_KB" -lt 2000000 ] && ! swapon --show | grep -q .; then
  echo "Poca memoria detectada: creando 2 GB de swap..."
  sudo fallocate -l 2G /swapfile || sudo dd if=/dev/zero of=/swapfile bs=1M count=2048
  sudo chmod 600 /swapfile
  sudo mkswap /swapfile
  sudo swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab >/dev/null
fi

python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements.txt

echo
echo "== [2/4] Abriendo el puerto $PUERTO en el firewall de la VM =="
# Las imágenes Ubuntu de Oracle usan iptables (no ufw) y bloquean todo lo
# que no sea SSH. Se agrega la regla al principio y se guarda para que
# sobreviva reinicios.
if ! sudo iptables -C INPUT -p tcp --dport $PUERTO -j ACCEPT 2>/dev/null; then
  sudo iptables -I INPUT 1 -p tcp --dport $PUERTO -j ACCEPT
fi
sudo netfilter-persistent save

echo
echo "== [3/4] Configuración de Discord =="
if [ -f config.json ] && .venv/bin/python3 -c "import json,sys; c=json.load(open('config.json')); sys.exit(0 if c.get('token') and c.get('guild_id') else 1)"; then
  echo "Ya estaba configurado (config.json). Si quieres cambiarlo: borra config.json y vuelve a correr este script."
else
  .venv/bin/python3 run.py --configurar
fi

echo
echo "== [4/4] Dejándolo corriendo 24/7 =="
sudo tee /etc/systemd/system/cumito.service >/dev/null <<EOF
[Unit]
Description=Cumito - bot de Discord + relay
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$USUARIO
WorkingDirectory=$CARPETA
ExecStart=$CARPETA/.venv/bin/python3 run.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl daemon-reload
sudo systemctl enable cumito >/dev/null
sudo systemctl restart cumito
sleep 6

echo
if systemctl is-active --quiet cumito; then
  IP="$(curl -s --max-time 5 https://api.ipify.org || echo TU_IP_PUBLICA)"
  echo "=========================================================="
  echo "  LISTO. Cumito-servidor está corriendo."
  echo
  echo "  Dirección para poner en la app Cumito:"
  echo "      $IP:$PUERTO"
  echo
  echo "  Ver qué está haciendo:   sudo journalctl -u cumito -f"
  echo "  Reiniciarlo:             sudo systemctl restart cumito"
  echo "=========================================================="
else
  echo "Algo salió mal al arrancar. Esto es lo último que dijo:"
  sudo journalctl -u cumito -n 30 --no-pager
fi
