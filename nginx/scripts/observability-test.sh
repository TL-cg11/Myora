#!/usr/bin/env bash
set -euo pipefail

# Read-only health and datasource check for the systemd-based stack.
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
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
grep -q '"uid":"security-monitoring-mysql"' <<<"$datasources"

curl --fail --silent --show-error \
  --user "${GF_SECURITY_ADMIN_USER}:${GF_SECURITY_ADMIN_PASSWORD}" \
  http://127.0.0.1:3000/api/datasources/uid/security-monitoring-mysql/health \
  | grep -q '"status":"OK"'

dashboards=$(curl --fail --silent --show-error \
  --user "${GF_SECURITY_ADMIN_USER}:${GF_SECURITY_ADMIN_PASSWORD}" \
  'http://127.0.0.1:3000/api/search?tag=security-monitoring')
grep -q '"uid":"luck-security-events"' <<<"$dashboards"
grep -q '"uid":"luck-security-consumers"' <<<"$dashboards"

alert_rules=$(curl --fail --silent --show-error \
  --user "${GF_SECURITY_ADMIN_USER}:${GF_SECURITY_ADMIN_PASSWORD}" \
  http://127.0.0.1:3000/api/v1/provisioning/alert-rules)
for rule_uid in luck-security-lag-high luck-security-lag-critical \
  luck-security-message-stale luck-security-dlq-detected luck-security-sink-down; do
  grep -q "\"uid\":\"${rule_uid}\"" <<<"$alert_rules"
done

contact_points=$(curl --fail --silent --show-error \
  --user "${GF_SECURITY_ADMIN_USER}:${GF_SECURITY_ADMIN_PASSWORD}" \
  http://127.0.0.1:3000/api/v1/provisioning/contact-points)
grep -q '"name":"Luck Security Operations"' <<<"$contact_points"
grep -q '"uid":"luck-security-discord"' <<<"$contact_points"
if grep -qE '"uid":"luck-security-(slack|email)"' <<<"$contact_points"; then
  echo 'Legacy Slack or email contact point is still provisioned.' >&2
  exit 1
fi

python3 "$ROOT_DIR/scripts/verify_loki_security.py" --allow-empty

echo 'Grafana datasources, security dashboards, alert rules, Loki, and Prometheus are ready.'
