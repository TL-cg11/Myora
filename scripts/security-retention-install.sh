#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo 'Run as root: sudo bash scripts/security-retention-install.sh' >&2
  exit 1
fi

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
if [[ "$ROOT_DIR" != '/home/nginx/luck-nginx' ]]; then
  echo 'This service definition expects the repository at /home/nginx/luck-nginx.' >&2
  exit 1
fi
if [[ ! -x "$ROOT_DIR/.venv-security-sink/bin/python" ]]; then
  echo 'Missing .venv-security-sink; install requirements-security-sink.txt first.' >&2
  exit 1
fi
if [[ ! -f /etc/luck-security-retention.env ]]; then
  echo 'Create /etc/luck-security-retention.env with mode 0600 from security_retention.env.example.' >&2
  exit 1
fi
if [[ "$(stat -c '%a' /etc/luck-security-retention.env)" != '600' ]]; then
  echo '/etc/luck-security-retention.env must have mode 0600.' >&2
  exit 1
fi

install -m 0644 "$ROOT_DIR/observability/systemd/security-retention.service" \
  /etc/systemd/system/security-retention.service
install -m 0644 "$ROOT_DIR/observability/systemd/security-retention.timer" \
  /etc/systemd/system/security-retention.timer
systemctl daemon-reload
systemctl enable security-retention.timer
echo 'security-retention.timer is enabled but not started.'
echo 'Run a dry-run, then start it with: systemctl start security-retention.timer'
