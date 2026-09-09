#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
SOURCE_DIR="$PWD/security-monitoring"
INSTALL_DIR=/opt/luck-security-monitoring

if [ ! -d "$SOURCE_DIR" ]; then
  printf '%s\n' "Missing $SOURCE_DIR" >&2
  exit 1
fi

sudo apt-get update
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y suricata jq python3 logrotate

CAPTURE_INTERFACE=tailscale0
if ! ip link show "$CAPTURE_INTERFACE" >/dev/null 2>&1; then
  CAPTURE_INTERFACE=$(ip -o route show default | awk '{print $5; exit}')
fi
if [ -z "$CAPTURE_INTERFACE" ]; then
  printf '%s\n' 'Unable to determine a capture interface.' >&2
  exit 1
fi

MONITORED_IP=$(ip -4 -o addr show dev "$CAPTURE_INTERFACE" scope global | awk '{split($4,a,"/"); print a[1]; exit}')
if [ -z "$MONITORED_IP" ]; then
  printf '%s\n' "No IPv4 address found on $CAPTURE_INTERFACE." >&2
  exit 1
fi

sudo install -d -m 0755 "$INSTALL_DIR"
sudo cp -a "$SOURCE_DIR/." "$INSTALL_DIR/"

sudo install -d -m 0755 /etc/suricata/luck-rules
sed "s/@MONITORED_IP@/$MONITORED_IP/g" "$SOURCE_DIR/suricata/luck-ddos.rules.template" \
  | sudo tee /etc/suricata/luck-rules/luck-ddos.rules >/dev/null
sudo chmod 0644 /etc/suricata/luck-rules/luck-ddos.rules

if [ ! -f /etc/suricata/suricata.yaml.luck-backup ]; then
  sudo cp /etc/suricata/suricata.yaml /etc/suricata/suricata.yaml.luck-backup
fi
sudo sed -i -E \
  "s|^([[:space:]]*HOME_NET:).*|\\1 \"[$MONITORED_IP/32,127.0.0.0/8]\"|" \
  /etc/suricata/suricata.yaml

# suricata-update's default source is the Emerging Threats Open community ruleset.
sudo suricata-update --local /etc/suricata/luck-rules

sudo install -d -m 0755 /etc/systemd/system/suricata.service.d
sudo tee /etc/systemd/system/suricata.service.d/10-luck-interface.conf >/dev/null <<EOF
[Service]
ExecStart=
ExecStart=/usr/bin/suricata -D --af-packet=${CAPTURE_INTERFACE} -c /etc/suricata/suricata.yaml --pidfile /run/suricata.pid
EOF

sudo tee /etc/systemd/system/luck-suricata-update.service >/dev/null <<'EOF'
[Unit]
Description=Update Suricata ET Open and LUCK local rules
After=network-online.target

[Service]
Type=oneshot
ExecStart=/usr/bin/suricata-update --local /etc/suricata/luck-rules
ExecStartPost=/bin/systemctl reload suricata.service
EOF

sudo tee /etc/systemd/system/luck-suricata-update.timer >/dev/null <<'EOF'
[Unit]
Description=Daily Suricata community rule update

[Timer]
OnCalendar=daily
RandomizedDelaySec=30m
Persistent=true

[Install]
WantedBy=timers.target
EOF

sudo install -d -m 0755 /usr/local/lib/luck-security
sudo install -m 0755 "$SOURCE_DIR/classifier/ids_classifier.py" /usr/local/lib/luck-security/ids_classifier.py
sudo install -m 0644 "$SOURCE_DIR/classifier/luck-ids-classifier.service" /etc/systemd/system/luck-ids-classifier.service
sudo install -m 0644 "$SOURCE_DIR/classifier/luck-security.logrotate" /etc/logrotate.d/luck-security
sudo install -d -o root -g adm -m 0750 /var/log/luck-security
sudo install -d -o root -g root -m 0750 /var/lib/luck-security
sudo touch /var/log/luck-security/ids-events.jsonl
sudo chown root:adm /var/log/luck-security/ids-events.jsonl
sudo chmod 0640 /var/log/luck-security/ids-events.jsonl

sudo systemctl daemon-reload
sudo systemctl enable --now suricata
sudo systemctl enable --now luck-suricata-update.timer
sudo systemctl enable --now luck-ids-classifier

printf 'Capture interface: %s (%s)\n' "$CAPTURE_INTERFACE" "$MONITORED_IP"
printf 'Raw EVE log: /var/log/suricata/eve.json\n'
printf 'Classified alert log: /var/log/luck-security/ids-events.jsonl\n'

bash scripts/test-security-monitoring.sh
