#!/bin/bash
# WAS(uvicorn)와 Kafka 마스킹 어댑터를 한 컨테이너에서 함께 띄운다.
#
# 어댑터의 표시용 마스킹 API(127.0.0.1:8765)는 loopback 전용이라 WAS 와 같은 네트워크 네임스페이스에
# 있어야 한다. 별도 컨테이너에 network_mode: service:was 로 붙이면 WAS 컨테이너를 재빌드할 때
# 어댑터가 사라진 네임스페이스에 남아 Kafka/DNS 를 잃는 문제가 있어(compose 가 자동으로 따라
# 재생성하지 않는다) 같은 컨테이너의 두 프로세스로 둔다.
#
# 운영 서버의 luck-was.service / luck-masking-adapter.service 가 각각 Restart=always 인 것과 같게,
# 어댑터는 죽으면 잠시 뒤 다시 올리고 WAS 는 어댑터 상태와 무관하게 계속 돈다 (어댑터가 없으면
# 채팅 화면 마스킹은 WAS 가 안전한 대체 문구로 처리한다).
set -uo pipefail

ADAPTER_ENABLED=${ADAPTER_ENABLED:-true}
ADAPTER_RESTART_SECONDS=${ADAPTER_RESTART_SECONDS:-10}

adapter_loop() {
  cd /app/security-monitoring/detector
  while true; do
    python -m adapter 2>&1 | sed -u 's/^/[masking-adapter] /'
    echo "[masking-adapter] 종료됨(exit=${PIPESTATUS[0]}). ${ADAPTER_RESTART_SECONDS}초 뒤 다시 시작합니다. 모델·Kafka 설정을 확인하세요."
    sleep "$ADAPTER_RESTART_SECONDS"
  done
}

if [ "$ADAPTER_ENABLED" = "true" ]; then
  adapter_loop &
fi

# uvicorn 을 PID 1 로 두어 docker stop 의 SIGTERM 을 그대로 받게 한다. 컨테이너가 끝나면 어댑터 루프도 함께 끝난다.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
