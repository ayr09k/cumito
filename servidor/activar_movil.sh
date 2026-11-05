#!/usr/bin/env bash
# Cumito en el celular (Android / iPhone): se corre UNA vez en la VM.
#   bash activar_movil.sh
#
# Deja la app del celular en una dirección https (gratis, con candado), por
# ejemplo https://1-2-3-4.sslip.io  (los números son la IP de la VM).
# Antes hay que abrir los puertos 80 y 443 en Oracle (ver el tutorial).
set -euo pipefail
DUENO="$(id -un)"
REPO_DIR="/home/$DUENO/.cumito-repo"
WEB=/var/www/cumito

IP="$(curl -s --max-time 10 https://api.ipify.org || true)"
if [ -z "$IP" ]; then echo "No pude saber la IP pública de la VM."; exit 1; fi
HOST="${IP//./-}.sslip.io"
echo "La app del celular va a quedar en: https://$HOST"

# 1) Caddy: sirve la app y saca el certificado https solo
if ! command -v caddy >/dev/null; then
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https curl gnupg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
  sudo apt-get update -qq
  sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq caddy
fi

# 2) los archivos de la app (y se mantienen al día solos con cada actualización)
if [ ! -d "$REPO_DIR/.git" ]; then
  git clone -q --depth 1 https://github.com/ayr09k/cumito.git "$REPO_DIR"
fi
sudo mkdir -p "$WEB/fonts"
sudo cp -rT "$REPO_DIR/app/assets" "$WEB"
for w in 500:Medium 600:SemiBold 700:Bold 800:ExtraBold; do
  sudo curl -s --max-time 30 -o "$WEB/fonts/Manrope-${w#*:}-latin.ttf" \
    "https://cdn.jsdelivr.net/fontsource/fonts/manrope@latest/latin-${w%%:*}-normal.ttf" || true
done
sudo chmod -R a+rX "$WEB"

# 3) la configuración: la app en / y la conexión con Cumito en /ws
sudo tee /etc/caddy/Caddyfile >/dev/null <<CADDY
$HOST {
	encode gzip
	@ws path /ws
	reverse_proxy @ws 127.0.0.1:8765
	redir / /web/ 302
	header /web/* Cache-Control "no-cache"
	root * $WEB
	file_server
}
CADDY

# 4) el firewall de la propia VM (las de Oracle bloquean todo por defecto)
for P in 80 443; do
  if ! sudo iptables -C INPUT -p tcp --dport $P -j ACCEPT 2>/dev/null; then
    sudo iptables -I INPUT 1 -p tcp --dport $P -j ACCEPT
  fi
done
sudo netfilter-persistent save >/dev/null 2>&1 || true

sudo systemctl enable caddy >/dev/null 2>&1 || true
sudo systemctl restart caddy
echo "Sacando el certificado (unos segundos)..."
for i in $(seq 1 30); do
  if curl -s --max-time 5 -o /dev/null "https://$HOST/web/"; then
    echo
    echo "LISTO. Abre esto en el celular:  https://$HOST"
    exit 0
  fi
  sleep 3
done
echo
echo "Caddy está corriendo, pero todavía no responde por https."
echo "Revisa que abriste los puertos 80 y 443 en Oracle y vuelve a correr este comando."
echo "Detalle: sudo journalctl -u caddy --no-pager | tail -20"
