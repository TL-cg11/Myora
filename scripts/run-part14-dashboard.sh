#!/usr/bin/env bash
set -euo pipefail

# One guarded Nginx-host batch for Part 14. MariaDB role assignment belongs on
# the MariaDB host and is intentionally not performed by this script.
ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
MODE=${1:---dry-run}

if [[ "$MODE" != '--dry-run' && "$MODE" != '--execute' ]]; then
  echo 'Usage: bash scripts/run-part14-dashboard.sh [--dry-run|--execute]' >&2
  exit 2
fi

cat <<'PLAN'
Part 14 server batch:
  1. install Grafana subpath/auth-proxy configuration
  2. install Nginx dashboard/Grafana auth_request proxy configuration
  3. validate and restart Grafana and Nginx
  4. verify loopback-only Grafana listener and protected route responses
PLAN

if [[ "$MODE" == '--dry-run' ]]; then
  echo 'Dry run only. Re-run with --execute after setting Grafana installer environment values.'
  exit 0
fi

if [[ ${EUID} -ne 0 ]]; then
  echo 'Run as root: sudo bash scripts/run-part14-dashboard.sh --execute' >&2
  exit 1
fi

install -m 0644 "$ROOT_DIR/nginx.conf" /etc/nginx/nginx.conf
install -m 0644 "$ROOT_DIR/conf.d/luck.conf" /etc/nginx/conf.d/luck.conf
install -o root -g grafana -m 0640 "$ROOT_DIR/observability/grafana/grafana.ini" /etc/grafana/grafana.ini
install -d -o grafana -g grafana -m 0755 /var/lib/grafana/dashboards/security-monitoring
install -m 0644 "$ROOT_DIR/observability/grafana/dashboards/"*.json /var/lib/grafana/dashboards/security-monitoring/
chown grafana:grafana /var/lib/grafana/dashboards/security-monitoring/*.json
nginx -t
systemctl restart grafana-server nginx
systemctl is-active --quiet grafana-server
systemctl is-active --quiet nginx
ss -ltn | grep -Eq '127\.0\.0\.1:3000' || { echo 'Grafana is not loopback-bound.' >&2; exit 1; }
if ss -ltn | grep -Eq '(^|[[:space:]])(0\.0\.0\.0|\[::\]):3000'; then
  echo 'Grafana must not listen publicly on port 3000.' >&2
  exit 1
fi
curl -fsS -o /dev/null -w 'dashboard unauthenticated=%{http_code}\n' http://127.0.0.1/dashboard || true
curl -fsS -o /dev/null -w 'grafana unauthenticated=%{http_code}\n' http://127.0.0.1/grafana/ || true
echo 'Part 14 server configuration applied. Perform the browser role/cookie/iframe checks next.'
