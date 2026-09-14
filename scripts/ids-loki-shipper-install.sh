#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo 'Run as root: sudo bash scripts/ids-loki-shipper-install.sh' >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [[ "$ROOT_DIR" != '/home/nginx/luck-nginx' ]]; then
  echo 'This installer expects the repository at /home/nginx/luck-nginx.' >&2
  exit 1
fi
if [[ ! -f /etc/luck-ids-loki-shipper.env ]]; then
  echo 'Create /etc/luck-ids-loki-shipper.env from ids_loki_shipper.env.example with mode 0600.' >&2
  exit 1
fi
if [[ "$(stat -c '%a' /etc/luck-ids-loki-shipper.env)" != '600' ]]; then
  echo '/etc/luck-ids-loki-shipper.env must have mode 0600.' >&2
  exit 1
fi

install -d -o root -g adm -m 0750 /var/lib/luck-security/ids-loki /var/lib/luck-security/ids-loki/buffer
install -d -o root -g root -m 0755 /usr/local/lib/luck-security
install -m 0755 "$ROOT_DIR/security-monitoring/ids_shipper/ids_loki_shipper.py" \
  /usr/local/lib/luck-security/ids_loki_shipper.py
install -m 0644 "$ROOT_DIR/security-monitoring/ids_shipper/luck-ids-loki-shipper.service" \
  /etc/systemd/system/luck-ids-loki-shipper.service
systemctl daemon-reload
systemctl enable --now luck-ids-loki-shipper
systemctl is-active --quiet luck-ids-loki-shipper
echo 'luck-ids-loki-shipper is active.'
