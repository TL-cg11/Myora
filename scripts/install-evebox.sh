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
sudo install -m 0644 conf.d/luck.conf /etc/nginx/conf.d/luck.conf

sudo systemctl daemon-reload
sudo systemctl enable --now luck-evebox

for _ in $(seq 1 20); do
  if curl --fail --silent --show-error http://127.0.0.1:5636/ >/dev/null 2>&1; then
    break
  fi
  sleep 1
done
curl --fail --silent --show-error http://127.0.0.1:5636/ >/dev/null

# Route EveBox through Nginx so the exact /suricata request can be redirected
# before the relative web assets are loaded. Tailscale keeps only its existing
# root proxy to Nginx.
sudo tailscale serve --yes --set-path=/suricata off || true
sudo tailscale serve --yes --set-path=/suricata/ off || true

DNS_NAME=$(tailscale status --self --json \
  | sed -n 's/.*"DNSName":[[:space:]]*"\([^"]*\)".*/\1/p' \
  | head -n 1 \
  | sed 's/\.$//')

sudo nginx -t
sudo systemctl reload nginx
sudo systemctl is-active --quiet nginx
test "$(curl --silent --output /dev/null --write-out '%{http_code}' "https://$DNS_NAME/suricata")" = 308
curl --fail --silent --show-error "https://$DNS_NAME/suricata/" >/dev/null

printf 'EveBox URL: https://%s/suricata/\n' "$DNS_NAME"
printf '%s\n' 'Initial credentials: sudo journalctl -u luck-evebox | grep "Created administrator"'
