#!/usr/bin/env bash
set -euo pipefail

# Read-only health and datasource check for the systemd-based stack.
if [[ ${EUID} -ne 0 ]]; then
  echo 'Run as root: sudo bash scripts/observability-test.sh' >&2
  exit 1
fi

for service_name in loki prometheus grafana-server; do
  systemctl is-active --quiet "$service_name"
done

curl --fail --silent --show-error http://127.0.0.1:3100/ready >/dev/null
curl --fail --silent --show-error http://127.0.0.1:9090/-/ready >/dev/null
curl --fail --silent --show-error http://127.0.0.1:3000/api/health >/dev/null

set -a
source /etc/luck-observability.env
set +a
datasources=$(curl --fail --silent --show-error --user "${GF_SECURITY_ADMIN_USER}:${GF_SECURITY_ADMIN_PASSWORD}" \
  http://127.0.0.1:3000/api/datasources)
grep -q '"name":"Prometheus"' <<<"$datasources"
grep -q '"name":"Loki"' <<<"$datasources"

echo 'Loki, Prometheus, Grafana, and both provisioned datasources are ready.'
