#!/usr/bin/env bash
# Instala el panel de la sucursal como servicio systemd en Ubuntu/Debian.
# Uso (desde la raíz del repo):  sudo ./deploy/linux/install.sh [usuario]
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "Ejecutar con sudo." >&2
  exit 1
fi

SERVICE_USER="${1:-${SUDO_USER:-}}"
if [[ -z "$SERVICE_USER" || "$SERVICE_USER" == "root" ]]; then
  echo "Indica el usuario que ejecutará el servicio: sudo $0 <usuario>" >&2
  exit 1
fi

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
UNIT=/etc/systemd/system/santander-panel.service

echo "== Paquetes del sistema"
apt-get update -y
apt-get install -y python3 python3-venv python3-pip
if ! command -v npm >/dev/null 2>&1; then
  apt-get install -y nodejs npm
fi

echo "== Acceso al puerto serie RS-485 (grupo dialout)"
usermod -aG dialout "$SERVICE_USER"

echo "== Entorno Python"
sudo -u "$SERVICE_USER" python3 -m venv "$REPO/backend/.venv"
sudo -u "$SERVICE_USER" "$REPO/backend/.venv/bin/pip" install --upgrade pip
sudo -u "$SERVICE_USER" "$REPO/backend/.venv/bin/pip" install -r "$REPO/backend/requirements.txt"

echo "== Build del panel web"
sudo -u "$SERVICE_USER" bash -c "cd '$REPO/frontend' && npm ci && npm run build"

if [[ ! -f "$REPO/backend/.env" ]]; then
  sudo -u "$SERVICE_USER" cp "$REPO/backend/.env.example" "$REPO/backend/.env"
  echo "!! Creado backend/.env desde .env.example: revisa MODBUS_SERIAL_PORT, secretos JWT, COCE_*, CSIP_*, PANPHONE_WEB_*"
fi

echo "== Servicio systemd"
sed -e "s#__USER__#$SERVICE_USER#g" -e "s#__REPO__#$REPO#g" \
  "$REPO/deploy/linux/santander-panel.service" > "$UNIT"
systemctl daemon-reload
systemctl enable santander-panel.service
systemctl restart santander-panel.service

if command -v ufw >/dev/null 2>&1 && ufw status | grep -q "Status: active"; then
  ufw allow 8000/tcp
  ufw allow 8443/tcp
fi

echo
echo "Listo. Estado:  systemctl status santander-panel"
echo "Logs:           journalctl -u santander-panel -f"
