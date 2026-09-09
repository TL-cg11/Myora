#!/usr/bin/env bash
# Kafka 마스킹 어댑터를 systemd 서비스로 설치한다.
# 실행: bash security-monitoring/detector/scripts/install-adapter.sh
set -euo pipefail

DETECTOR_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PROJECT_DIR="$(cd "$DETECTOR_DIR/../.." && pwd)"
PYTHON="$PROJECT_DIR/.venv/bin/python"
ENV_FILE="$PROJECT_DIR/.env"
SERVICE_NAME='luck-masking-adapter'
INSTALL_USER=$(id -un)
INSTALL_GROUP=$(id -gn)

if [ ! -x "$PYTHON" ]; then
  echo "가상환경이 없습니다: $PYTHON" >&2
  echo "먼저 $PROJECT_DIR 에서 bash scripts/install.sh 를 실행하세요." >&2
  exit 1
fi

# 어댑터만 confluent-kafka를 사용한다. 없으면 WAS와 같은 requirements로 설치한다.
if ! "$PYTHON" -c 'import confluent_kafka' >/dev/null 2>&1; then
  echo '[1/5] confluent-kafka 설치'
  "$PYTHON" -m pip install --quiet -r "$PROJECT_DIR/requirements.txt"
else
  echo '[1/5] confluent-kafka 확인 완료'
fi

if [ ! -f "$ENV_FILE" ]; then
  cp "$PROJECT_DIR/.env.example" "$ENV_FILE"
  echo "[2/5] .env 생성: $ENV_FILE"
fi

# 가명화 키가 없으면 만들어 넣는다. 이미 있으면 절대 덮어쓰지 않는다.
if grep -qE '^MASKING_PSEUDONYM_KEY=.+' "$ENV_FILE"; then
  echo '[2/5] MASKING_PSEUDONYM_KEY 확인 완료 (기존 키 유지)'
else
  GENERATED_KEY=$("$PYTHON" -c 'import secrets; print(secrets.token_urlsafe(48))')
  # 값이 비어 있는 기존 줄은 지운다. 나머지 설정이 이미 있으면 키만 덧붙인다.
  sed -i '/^MASKING_PSEUDONYM_KEY=$/d' "$ENV_FILE"
  if grep -q '^ADAPTER_MASKED_LOGS_TOPIC=' "$ENV_FILE"; then
    printf 'MASKING_PSEUDONYM_KEY=%s\n' "$GENERATED_KEY" >> "$ENV_FILE"
  else
    cat >> "$ENV_FILE" <<EOF

# Kafka 마스킹 어댑터 (security-monitoring/detector, python -m adapter)
MASKING_PSEUDONYM_KEY=$GENERATED_KEY
ADAPTER_GROUP_ID=myohan-security-masking
ADAPTER_INPUT_TOPICS=myohan.was.app,myohan.nginx.access
ADAPTER_MASKED_LOGS_TOPIC=myohan.masked-logs
ADAPTER_SECURITY_EVENTS_TOPIC=myohan.security-events
ADAPTER_DEAD_LETTER_TOPIC=myohan.dead-letter
ADAPTER_DEFAULT_ENVIRONMENT=production
EOF
  fi
  echo '[2/5] MASKING_PSEUDONYM_KEY 생성 및 .env 기록'
  echo '      이 키를 잃으면 이전 가명 토큰과 연결이 끊깁니다. .env를 백업하세요.'
fi
chmod 600 "$ENV_FILE"

# Kafka에 연결하기 전에 마스킹 자체가 동작하는지 확인한다.
echo '[3/5] 마스킹 동작 확인 (Kafka 연결 없음)'
SAMPLE='{"timestamp":"2026-01-01T00:00:00Z","source":"nginx","request_id":"install-check","client_ip":"203.0.113.45","method":"GET","uri":"/api/health","status":200}'
CHECK=$(cd "$DETECTOR_DIR" && printf '%s\n' "$SAMPLE" \
  | "$PYTHON" -m adapter --dry-run - --dry-run-topic myohan.nginx.access)
if ! printf '%s' "$CHECK" | grep -q '203.0.113.0'; then
  echo '      IP 마스킹 확인에 실패했습니다. 설정을 점검하세요.' >&2
  printf '%s\n' "$CHECK" >&2
  exit 1
fi
echo '      client_ip 203.0.113.45 -> 203.0.113.0 확인'

echo '[4/5] systemd 서비스 등록'
UNIT_FILE=$(mktemp)
trap 'rm -f "$UNIT_FILE"' EXIT
cat > "$UNIT_FILE" <<EOF
[Unit]
Description=Luck Kafka Masking Adapter
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$INSTALL_USER
Group=$INSTALL_GROUP
WorkingDirectory=$DETECTOR_DIR
EnvironmentFile=$ENV_FILE
Environment=PYTHONUNBUFFERED=1
ExecStart=$PYTHON -m adapter
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

sudo install -m 0644 "$UNIT_FILE" "/etc/systemd/system/$SERVICE_NAME.service"
sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME.service"
sudo systemctl restart "$SERVICE_NAME.service"

echo '[5/5] 서비스 상태 확인'
for _ in $(seq 1 10); do
  if systemctl is-active --quiet "$SERVICE_NAME.service"; then
    sudo systemctl status "$SERVICE_NAME.service" --no-pager | head -n 5
    echo
    echo "설치 완료. 로그: sudo journalctl -u $SERVICE_NAME -f"
    exit 0
  fi
  sleep 1
done

echo '서비스가 실행 상태로 올라오지 않았습니다. 아래 로그를 확인하세요.' >&2
sudo journalctl -u "$SERVICE_NAME.service" -n 30 --no-pager
exit 1
