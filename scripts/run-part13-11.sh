#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE=/etc/luck-security-sink.env

if [[ ${1:-} != '--execute' ]]; then
  printf '%s\n' '{"status":"dry-run","part":"13-11","actions":["restart security sinks","verify commit metric","run guarded Kafka performance test"],"requires_execute":true}'
  exit 0
fi

if [[ ${EUID} -ne 0 ]]; then
  printf '%s\n' '{"status":"error","stage":"preflight","error":"run with sudo"}' >&2
  exit 2
fi
if [[ ! -f "$ENV_FILE" || ! -x "$ROOT_DIR/.venv-security-sink/bin/python" ]]; then
  printf '%s\n' '{"status":"error","stage":"preflight","error":"environment file or security sink virtualenv is missing"}' >&2
  exit 2
fi

systemctl restart luck-security-event-sink luck-masked-log-sink
for unit in luck-security-event-sink luck-masked-log-sink; do
  if [[ $(systemctl is-active "$unit") != active ]]; then
    printf '{"status":"error","stage":"service-restart","unit":"%s"}\n' "$unit" >&2
    exit 2
  fi
done

sleep 3
for port in 9108 9109; do
  metrics=$(curl -fsS "http://100.117.253.9:${port}/metrics")
  if ! grep -q 'luck_sink_commit_duration_seconds' <<<"$metrics" \
     || ! grep -q 'luck_sink_end_to_end_duration_seconds' <<<"$metrics"; then
    printf '{"status":"error","stage":"metric-preflight","port":%s}\n' "$port" >&2
    exit 2
  fi
done

set -a
source "$ENV_FILE"
set +a
exec "$ROOT_DIR/.venv-security-sink/bin/python" \
  "$ROOT_DIR/scripts/run_part13_performance.py" --execute
