#!/usr/bin/env bash
# Install the two Kafka sink workers as native systemd services.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_DIR="$ROOT_DIR/.venv-security-sink"
ENV_FILE=/etc/luck-security-sink.env
INSTALL_USER=$(id -un)
INSTALL_GROUP=$(id -gn)
BUFFER_DIR=/var/lib/luck-security-sink/masked-log-buffer

if [[ ! -f "$ENV_FILE" ]]; then
  echo "Create $ENV_FILE from security_sink.env.example with mode 0600." >&2
  exit 1
fi

if [[ "$(stat -c '%a' "$ENV_FILE")" != '600' ]]; then
  echo "$ENV_FILE must have mode 0600." >&2
  exit 1
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install --quiet -r "$ROOT_DIR/requirements-security-sink.txt"

sudo install -d -m 0700 -o "$INSTALL_USER" -g "$INSTALL_GROUP" "$BUFFER_DIR"

install_unit() {
  local service_name=$1
  local module_name=$2
  local unit_file
  unit_file=$(mktemp)
  cat > "$unit_file" <<EOF
[Unit]
Description=Luck ${service_name}
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$INSTALL_USER
Group=$INSTALL_GROUP
WorkingDirectory=$ROOT_DIR
EnvironmentFile=$ENV_FILE
Environment=PYTHONUNBUFFERED=1
ExecStart=$VENV_DIR/bin/python -m $module_name
Restart=always
RestartSec=3
UMask=0077

[Install]
WantedBy=multi-user.target
EOF
  sudo install -m 0644 "$unit_file" "/etc/systemd/system/$service_name.service"
  rm -f "$unit_file"
}

install_unit luck-security-event-sink security_sink.worker
install_unit luck-masked-log-sink security_sink.masked_worker

sudo systemctl daemon-reload
sudo systemctl enable --now luck-security-event-sink.service luck-masked-log-sink.service
sudo systemctl is-active --quiet luck-security-event-sink.service
sudo systemctl is-active --quiet luck-masked-log-sink.service

echo "Security sink services are active."
echo "Logs: sudo journalctl -u luck-security-event-sink -u luck-masked-log-sink -n 50 --no-pager"
