#!/bin/bash
# WAS(uvicorn)와 Kafka 마스킹 어댑터를 한 컨테이너에서 함께 띄운다.
#
# 어댑터의 표시용 마스킹 API(127.0.0.1:8765)는 loopback 전용이라 WAS 와 같은 네트워크 네임스페이스에
# 있어야 한다. 별도 컨테이너에 network_mode: service:was 로 붙이면 WAS 컨테이너를 재빌드할 때
# 어댑터가 사라진 네임스페이스에 남아 Kafka/DNS 를 잃는 문제가 있어(compose 가 자동으로 따라
# 재생성하지 않는다) 같은 컨테이너의 두 프로세스로 둔다. 둘 중 하나가 죽으면 컨테이너가 종료되고
# restart 정책이 둘을 함께 다시 올린다. 운영 서버의 luck-was.service + luck-masking-adapter.service 에 해당한다.
set -euo pipefail

ADAPTER_ENABLED=${ADAPTER_ENABLED:-true}
pids=()

if [ "$ADAPTER_ENABLED" = "true" ]; then
  ( cd /app/security-monitoring/detector && exec python -m adapter ) 2>&1 | sed -u 's/^/[masking-adapter] /' &
  pids+=($!)
fi
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" &
pids+=($!)

term() { kill -TERM "${pids[@]}" 2>/dev/null || true; }
trap term TERM INT

# 하나라도 끝나면 나머지도 내리고 그 종료 코드로 나간다.
status=0
wait -n "${pids[@]}" || status=$?
term
wait "${pids[@]}" 2>/dev/null || true
exit "$status"
