# luck-nginx

Ubuntu Server 24.04에서 Tailscale HTTPS 요청을 받고 별도 FastAPI 서버로 전달하는 구성입니다. 브라우저가 신뢰하는 `*.ts.net` 인증서를 Tailscale Serve가 자동으로 관리합니다.

## 구성

- HTTPS 진입점: `https://<nginx-MagicDNS-name>.ts.net:443`
- Tailscale 서버: `100.117.253.9`
- 로컬 Nginx 백엔드: `127.0.0.1:8080` (외부 접근 불가)
- FastAPI 업스트림: `100.66.77.55:8000`
- `GET /nginx-health`: Nginx 자체 상태 확인
- `GET /health`: FastAPI와 MariaDB까지 포함한 전체 상태 확인
- 그 밖의 요청: FastAPI로 프록시

## 설치 및 갱신

먼저 Tailscale 관리자 콘솔의 [DNS 설정](https://login.tailscale.com/admin/dns)에서 다음 두 항목을 활성화해야 합니다.

1. MagicDNS
2. HTTPS Certificates

인증서 도메인은 Certificate Transparency 공개 로그에 기록되므로 서버 이름에 민감한 정보를 사용하지 마세요.

```bash
git clone https://github.com/TL-cg11/luck-nginx.git ~/luck-nginx
cd ~/luck-nginx
bash scripts/install.sh
```

이미 clone한 서버에서는 다음과 같이 갱신합니다.

```bash
cd ~/luck-nginx
git pull --ff-only
bash scripts/install.sh
```

설치 스크립트는 다음 흐름을 자동으로 구성합니다.

```text
브라우저 HTTPS :443 → Tailscale Serve → Nginx 127.0.0.1:8080 → FastAPI
```

Tailscale Serve는 `--bg` 모드로 재부팅 후에도 유지되며 TLS 인증서를 자동으로 갱신합니다.

## 확인

```bash
curl http://127.0.0.1:8080/nginx-health
sudo tailscale serve status
bash scripts/test.sh
```

`tailscale serve status`에 표시되는 `https://<machine>.<tailnet>.ts.net` 주소로 접속해야 합니다. Tailscale IP를 사용한 `http://100.117.253.9` 접속은 더 이상 제공하지 않습니다.

카메라는 HTTPS 주소에서만 정상적으로 권한을 요청합니다. 사이트 권한에서 카메라를 허용한 뒤 `/face` 페이지를 사용하세요.

## 보안 모니터링 계약

저장·감사·관측 파트의 Kafka 메시지 계약은 [`contracts/`](contracts/README.md), DB 분리·검증·재시도·DLQ 정책은 [`docs/security-monitoring-foundation.md`](docs/security-monitoring-foundation.md)에서 관리합니다.

Loki·Prometheus·Grafana의 로컬 실행과 health check는 [`docs/observability.md`](docs/observability.md)를 참고합니다.

## Security event sink

`security_sink.worker`는 `myohan.security-events`를 계약 v1으로 검증한 뒤 하나의 MariaDB transaction 안에서 `security_event`, 메시지의 각 `security_event_detection`, `CREATED` action과 처리 offset을 저장합니다. 최초 action의 actor는 `SYSTEM` / `security-event-sink`로 고정됩니다.

`security_sink.masked_worker`는 `myohan.masked-logs`의 처리 offset을 먼저 확인하고, 신규 메시지만 Loki에 적재한 뒤 처리 offset을 DB에 저장합니다. 두 worker 모두 Kafka 자동 commit을 끄고 sink 처리가 성공한 뒤 동기식으로 offset을 commit합니다.

```bash
python3 -m venv .venv-security-sink
.venv-security-sink/bin/pip install -r requirements-security-sink.txt
cp security_sink.env.example security_sink.env
set -a
. ./security_sink.env
set +a
.venv-security-sink/bin/python -m security_sink.worker
# 별도 shell/service에서 실행
.venv-security-sink/bin/python -m security_sink.masked_worker
```

`security_sink.env`에는 실제 DB/Kafka/Loki 접속정보를 넣고 Git에 추가하지 않습니다. DB에는 `luck-mariadb`의 security monitoring migration과 sink 계정 구성이 먼저 적용되어 있어야 합니다. 처리 offset과 이벤트 ID 기반 멱등 처리, retry·filesystem buffer·sink DLQ 및 실패 이력을 포함합니다.

Nginx 서버에 native systemd 서비스로 적용할 때는 `/etc/luck-security-sink.env`를 mode 0600으로 준비한 뒤 설치 스크립트를 실행합니다. 현재 Kafka broker는 WAS의 `100.66.77.55:9092`를 사용합니다.

```bash
sudo install -m 0600 security_sink.env.example /etc/luck-security-sink.env
sudoedit /etc/luck-security-sink.env
bash scripts/security-sink-install.sh
```

설치 후 `luck-security-event-sink`, `luck-masked-log-sink` 두 서비스가 각각 `myohan.security-events`, `myohan.masked-logs`를 소비합니다.

### 실패 처리와 전달 보장

두 sink는 DB·Loki 등 일시적 실패를 1·2·4·8·16초 간격으로 최대 5회 재시도합니다. 계약·JSON·UTF-8·마스킹 안전성 오류는 재시도하지 않고 즉시 sink 전용 DLQ로 보내며, DLQ에는 원문 없이 source 위치, key, payload SHA-256, schema version과 일반화된 오류 정보만 기록합니다. 실패와 재시도 상태는 `consumer_failure`에 메시지별로 upsert하고 복구 시 `RECOVERED`로 변경합니다.

`myohan.masked-logs`는 Loki 장애로 재시도를 소진하면 검증을 통과한 마스킹 payload를 `MASKED_LOG_BUFFER_DIR`에 mode 0600 파일로 원자 저장합니다. 기본 최대 크기는 1 GiB이고 60초마다 재전송하며, 최대 크기를 넘으면 Kafka offset을 commit하지 않아 upstream에 backpressure를 적용합니다.

Loki 전송은 at-least-once입니다. Loki push 성공 후 `kafka_consumption` 기록 또는 Kafka offset commit 전에 프로세스가 중단되면 동일 로그가 다시 push될 수 있습니다. 손실 방지를 우선하며 조회·집계에서 JSON log line의 `event_id`로 중복을 식별합니다. DB security event는 `event_id` UNIQUE 키로 중복 행 생성을 차단합니다.

로컬 단위 테스트는 외부 Kafka/MariaDB 없이 실행할 수 있습니다.

```bash
python -m unittest discover -s tests -v
python scripts/benchmark_security_sink_core.py --duration 60
```

## Security notifications

`security_sink.notifier_worker` sends HIGH/CRITICAL, repeated-behavior, and
long-unresolved event notifications through the durable `notification_log`
queue. Discord Webhook, grouping, retry, deduplication, and native systemd setup are
documented in [`docs/security-notifications.md`](docs/security-notifications.md).

benchmark는 network I/O를 제외한 local core 회귀 검사입니다. 실제 DB·Loki latency, Kafka lag와 60초 운영 처리량은 서버 적용 후 별도로 검증해야 합니다.

## Suricata IDS / DDoS 모니터링

별도 탐지 전용 파이프라인은
[`security-monitoring/README.md`](security-monitoring/README.md)를 참고하세요. Suricata
커뮤니티 룰과 로컬 DDoS 임계치 룰을 사용하며, 분류 로그를 로컬 JSONL에 보존합니다.
`/suricata`에서는 Tailscale HTTPS로 보호되는 EveBox 웹 콘솔로 이동합니다.
