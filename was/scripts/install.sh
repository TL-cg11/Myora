#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
PROJECT_DIR=$(pwd)
INSTALL_USER=$(id -un)
INSTALL_GROUP=$(id -gn)

sudo apt-get update
sudo apt-get install -y python3 python3-venv python3-pip curl

python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
fi

if [ ! -f .env.deepseek.face ]; then
  cp .env.deepseek.face.example .env.deepseek.face
fi

UNIT_FILE=$(mktemp)
trap 'rm -f "$UNIT_FILE"' EXIT

cat > "$UNIT_FILE" <<EOF
[Unit]
Description=Luck FastAPI Service
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$INSTALL_USER
Group=$INSTALL_GROUP
WorkingDirectory=$PROJECT_DIR
EnvironmentFile=$PROJECT_DIR/.env
ExecStart=$PROJECT_DIR/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=3
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo install -m 0644 "$UNIT_FILE" /etc/systemd/system/luck-was.service
sudo systemctl daemon-reload
sudo systemctl enable luck-was.service
sudo systemctl restart luck-was.service

for _ in {1..20}; do
  if curl --fail --silent --show-error http://127.0.0.1:8000/api/health; then
    exit 0
  fi
  sleep 1
done

sudo journalctl -u luck-was.service -n 30 --no-pager
exit 1
