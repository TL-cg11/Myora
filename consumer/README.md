# Kafka 로깅과 Consumer 운영 가이드

`luck-was`의 Kafka Producer와 Nginx/WAS Consumer 실행 방법을 정리한다. JSON 필드와
마스킹 규칙은 [WAS 로그 스키마](../schemas/README.md)를 참고한다.

## 전체 흐름

```text
Nginx access.log → Fluent Bit → myohan.nginx.access
                                      ↓
                         nginx_kafka_consumer.py

FastAPI → kafka_logging.py → myohan.was.app
                                  ↓
                       was_kafka_consumer.py
                                  ↓
                  PII 마스킹 → 탐지 → DB 저장
```

WAS는 `confluent-kafka` Producer로 JSON 로그를 직접 전송한다. `api_request`와
`ai_request`는 같은 topic을 사용하며 `feature`의 `saju`, `tarot`, `face` 값으로
기능을 구분한다. Kafka message key는 `request_id`다.

## 설정

루트 `.env`에 Kafka Broker 주소를 설정한다.

```env
KAFKA_BOOTSTRAP_SERVERS=localhost:9092
```

환경변수가 없으면 `localhost:9092`를 사용한다. 서버에서 의존성을 설치한다.

```bash
cd ~/luck-was
.venv/bin/python -m pip install -r requirements.txt
```

## Consumer 구분

| 프로세스 | Topic | Consumer group | Offset |
| --- | --- | --- | --- |
| `consumer.nginx_kafka_consumer` | `myohan.nginx.access` | `myohan-security-consumer` | `latest`, 라이브러리 기본 자동 commit |
| `consumer.was_kafka_consumer` | `myohan.was.app` | `myohan-security-was-consumer` | `latest`, handler 성공 후 수동 commit |

두 Consumer는 별도 프로세스로 실행한다.

```bash
.venv/bin/python -m consumer.nginx_kafka_consumer
.venv/bin/python -m consumer.was_kafka_consumer
```

`latest`는 해당 group에 저장된 offset이 없을 때 Consumer 구독 이후 들어온 메시지부터
읽는다는 뜻이다. 수신 테스트에서는 Consumer를 먼저 실행한 뒤 API 요청을 보낸다.

## WAS Consumer 처리 경계

WAS Consumer는 UTF-8 디코딩, JSON 파싱과 `schemas/was-log-v1.schema.json` 검증을
담당한다. 기본 `handle_was_log()`는 PII 원문을 출력하지 않고 요약만 보여준다.

```python
def handle_was_log(event: dict) -> bool:
    masked_event = mask_log(event)
    detect_attack(masked_event)
    save_log(masked_event)
    return True
```

- `True`: 마스킹·탐지·저장 완료 후 offset commit
- `False`: 후속 처리 미완료이므로 commit하지 않음
- 예외: 처리 실패로 기록하고 commit하지 않음

현재 기본 handler는 `False`를 반환한다. PII 처리와 DB 저장이 연결되기 전에는 Kafka
수신 확인 용도로만 실행하며, 상시 서비스로 활성화하지 않는다.

## 서버 수동 테스트

WAS Consumer를 먼저 실행한다.

```bash
cd ~/luck-was
KAFKA_BOOTSTRAP_SERVERS=localhost:9092 \
  .venv/bin/python -m consumer.was_kafka_consumer
```

다른 터미널에서 API를 호출한다.

```bash
curl -X POST http://127.0.0.1:8000/api/tarot/readings \
  -H 'Content-Type: application/json' \
  -H 'X-Request-ID: kafka-test-001' \
  -d '{
    "spread_code": "one-card",
    "topic": "love",
    "question": "제 연애운이 궁금해요",
    "guest_key": "3889ff5a-cadb-4c20-8759-083cac443121"
  }'
```

Consumer 요약에서 `request_id`, `feature`, `event_type`을 확인한다. 실제 Kafka 연결,
topic 존재 여부, listener, 방화벽과 권한은 WAS 서버에서 확인한다.

Nginx와 WAS 로그를 같은 `request_id`로 연결하려면 Nginx proxy 설정에 다음 항목이
필요하다.

```nginx
proxy_set_header X-Request-ID $request_id;
```

## systemd 등록

아래 예시의 `<SERVER_USER>`와 `<PROJECT_DIR>`를 서버의 `whoami`, `pwd` 결과로 바꾼다.

`/etc/systemd/system/luck-nginx-consumer.service`:

```ini
[Unit]
Description=Luck Nginx Kafka Consumer
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=<SERVER_USER>
Group=<SERVER_USER>
WorkingDirectory=<PROJECT_DIR>
EnvironmentFile=<PROJECT_DIR>/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=<PROJECT_DIR>/.venv/bin/python -m consumer.nginx_kafka_consumer
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

`/etc/systemd/system/luck-was-consumer.service`:

```ini
[Unit]
Description=Luck WAS Kafka Consumer
After=network-online.target luck-was.service
Wants=network-online.target

[Service]
Type=simple
User=<SERVER_USER>
Group=<SERVER_USER>
WorkingDirectory=<PROJECT_DIR>
EnvironmentFile=<PROJECT_DIR>/.env
Environment=PYTHONUNBUFFERED=1
ExecStart=<PROJECT_DIR>/.venv/bin/python -m consumer.was_kafka_consumer
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

unit 파일을 설치한 뒤 다음 명령으로 적용한다.

```bash
sudo systemctl daemon-reload
sudo systemctl start luck-nginx-consumer
sudo systemctl status luck-nginx-consumer --no-pager
sudo journalctl -u luck-nginx-consumer -f
```

정상 동작을 확인한 서비스만 부팅 자동 시작으로 등록한다.

```bash
sudo systemctl enable luck-nginx-consumer
```

PII handler와 DB 저장을 연결한 뒤 WAS Consumer도 같은 방식으로 시작하고 활성화한다.

```bash
sudo systemctl enable --now luck-was-consumer
sudo journalctl -u luck-was-consumer -f
```
