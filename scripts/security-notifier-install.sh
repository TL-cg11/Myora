#!/usr/bin/env bash
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo 'Run as root: sudo bash scripts/security-notifier-install.sh' >&2
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
if [[ ! -f /etc/luck-security-notifier.env ]]; then
  echo 'Create /etc/luck-security-notifier.env with mode 0600 from security_notifier.env.example.' >&2
  exit 1
fi
if [[ "$(stat -c '%a' /etc/luck-security-notifier.env)" != '600' ]]; then
  echo '/etc/luck-security-notifier.env must have mode 0600.' >&2
  exit 1
fi

install -m 0644 "$ROOT_DIR/observability/systemd/security-notifier.service" \
  /etc/systemd/system/security-notifier.service
systemctl daemon-reload
systemctl enable --now security-notifier
systemctl is-active --quiet security-notifier
echo 'security-notifier is active.'
