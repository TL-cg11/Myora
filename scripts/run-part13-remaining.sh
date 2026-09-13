#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

if [[ ${1:-} != '--execute' ]]; then
  printf '%s\n' '{"status":"dry-run","parts":["13-11","13-12","13-13","13-14"],"actions":["configuration backup rehearsal","service recovery check","guarded performance test","result collection"],"requires_execute":true}'
  exit 0
fi
if [[ ${EUID} -ne 0 ]]; then
  printf '%s\n' '{"status":"error","stage":"preflight","error":"run with sudo"}' >&2
  exit 2
fi

snapshot_dir=$(mktemp -d)
trap 'rm -rf "$snapshot_dir"' EXIT
files=(
  /etc/luck-security-sink.env
  /etc/luck-observability.env
  /etc/systemd/system/luck-security-event-sink.service
  /etc/systemd/system/luck-masked-log-sink.service
  /etc/systemd/system/loki.service
  /etc/systemd/system/prometheus.service
  /etc/loki/config.yml
  /etc/prometheus/prometheus.yml
)

for path in "${files[@]}"; do
  if [[ ! -f "$path" ]]; then
    printf '{"status":"error","stage":"rollback-preflight","missing":"%s"}\n' "$path" >&2
    exit 2
  fi
  target="$snapshot_dir/${path#/}"
  mkdir -p "$(dirname "$target")"
  cp -p "$path" "$target"
  cmp -s "$path" "$target"
done
for env_file in /etc/luck-security-sink.env /etc/luck-observability.env; do
  if [[ $(stat -c '%a' "$env_file") != 600 ]]; then
    printf '{"status":"error","stage":"rollback-preflight","permissions":"%s"}\n' "$env_file" >&2
    exit 2
  fi
done
for unit in luck-security-event-sink luck-masked-log-sink loki prometheus grafana-server; do
  if [[ $(systemctl is-active "$unit") != active ]]; then
    printf '{"status":"error","stage":"service-preflight","unit":"%s"}\n' "$unit" >&2
    exit 2
  fi
done

printf '%s\n' '{"status":"ok","part":"13-12","configuration_snapshot":"verified","secret_permissions":"600","services":"active","production_configuration_modified":false}'
set +e
bash "$ROOT_DIR/scripts/run-part13-11.sh" --execute
performance_status=$?
set -e
printf '{"status":"%s","parts":["13-11","13-12","13-13","13-14"],"performance_exit_code":%s,"configuration_snapshot":"verified","next":"run MariaDB rollback rehearsal and capture both outputs"}\n' \
  "$([[ $performance_status -eq 0 ]] && printf ok || printf incomplete)" "$performance_status"
exit "$performance_status"
