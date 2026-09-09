#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
EVEBOX_VERSION=0.28.0
INSTALLER=$(mktemp)
trap 'rm -f "$INSTALLER"' EXIT

# The official installer verifies the downloaded release checksum.
curl --fail --silent --show-error https://evebox.org/install.sh -o "$INSTALLER"
sudo sh "$INSTALLER" --version "$EVEBOX_VERSION" --bin-dir /usr/local/bin --yes

if ! getent passwd evebox >/dev/null; then
  sudo useradd --system --home-dir /var/lib/evebox --shell /usr/sbin/nologin evebox
fi
sudo install -d -o evebox -g evebox -m 0750 /var/lib/evebox
sudo install -m 0644 security-monitoring/evebox/luck-evebox.service /etc/systemd/system/luck-evebox.service

sudo systemctl daemon-reload
sudo systemctl enable --now luck-evebox

for _ in $(seq 1 20); do
  if curl --fail --silent --show-error http://127.0.0.1:5636/ >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl --fail --silent --show-error http://127.0.0.1:5636/ >/dev/null

# Add only a path handler to the existing Tailscale HTTPS service. Its root
# handler continues to proxy to Nginx on 127.0.0.1:8080 unchanged.
sudo tailscale serve --bg --yes --set-path=/suricata http://127.0.0.1:5636

DNS_NAME=$(tailscale status --self --json \
  | sed -n 's/.*"DNSName":[[:space:]]*"\([^"]*\)".*/\1/p' \
  | head -n 1 \
  | sed 's/\.$//')

curl --fail --silent --show-error "https://$DNS_NAME/suricata/" >/dev/null
sudo nginx -t
sudo systemctl is-active --quiet nginx

printf 'EveBox URL: https://%s/suricata/\n' "$DNS_NAME"
printf '%s\n' 'Initial credentials: sudo journalctl -u luck-evebox | grep "Created administrator"'
