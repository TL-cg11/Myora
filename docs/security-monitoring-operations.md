# Security monitoring operations v1

## Retention and cleanup

초기 운영 기준이며 실제 트래픽과 보안 보존 요구에 따라 조정한다.

| Data | Retention | Cleanup |
|---|---:|---|
| `security_event` | 365일 | 탐지·조치 이력과 함께 batch 삭제 |
| `security_event_detection` | 365일 | 부모 이벤트와 같은 기준으로 삭제 |
| `security_event_action` | 365일 | append-only 기간 종료 후 부모 이벤트와 함께 삭제 |
| `kafka_consumption` | 14일 | 메시지별 기록이므로 최우선 정리 대상 |
| `consumer_failure` | 90일 | DLQ 처리 완료 행부터 정리 |
| `notification_log` | 90일 | `SENT`, `SUPPRESSED` 완료 행부터 정리 |
| Loki logs | 30일 | Loki retention 설정 |
| Prometheus metrics | 30일 | Prometheus retention 설정 |

초기 버전은 FK와 운영 복잡도를 고려해 DB partition을 사용하지 않고 인덱스 기반 batch 삭제를 사용한다. 정리 worker는 정책별 한 batch당 최대 10,000개의 기준 행을 잠그며, `security_event` 계열은 365일이 지난 이벤트의 탐지·조치 이력을 같은 transaction에서 자식→부모 순서로 삭제한다. 진행 중인 알림이 있는 이벤트와 미완료 consumer failure는 삭제하지 않는다. `kafka_consumption`은 `(consumer_group, topic_name, partition_number, message_offset)` 중복 방지 목적의 짧은 보존 데이터이므로 14일 이후 동일한 batch 방식으로 삭제한다.

## Initial performance targets

부하 테스트 전 사용할 v1 합격 기준이다.

| Metric | Target |
|---|---:|
| Sink sustained throughput | consumer당 초당 100건 이상 |
| Burst throughput | consumer당 60초 동안 초당 300건 |
| DB sink processing latency | p95 2초 이하 |
| Loki sink processing latency | p95 5초 이하 |
| End-to-end event visibility | p95 10초 이하 |
| Normal consumer lag | 1,000 messages 미만 |
| Lag warning | 1,000 messages 이상 5분 지속 |
| Lag critical | 5,000 messages 이상 또는 oldest message 60초 초과 |

측정값은 메시지 수신 시각부터 DB/Loki 저장 성공 시각까지 계산한다. 실제 운영 수치가 목표를 초과하면 partition 수, consumer 수, DB batch size, Loki buffer를 조정하고 기준을 개정한다.

### Verification commands

외부 I/O를 제외한 계약 검증·메시지 처리 core의 회귀 성능은 아래 명령으로 60초씩 측정한다. 이 결과는 코드 자체의 병목을 찾는 기준이며 실제 DB·Loki latency 또는 Kafka lag 측정값으로 대체할 수 없다.

```bash
python scripts/benchmark_security_sink_core.py --duration 60
```

서버에서 수집한 실제 측정값은 아래 판정기에 입력한다. 종료 코드 0은 모든 목표 통과, 1은 하나 이상의 목표 미달을 뜻한다.

```bash
python scripts/verify_security_sink_targets.py \
  --sustained-throughput 100 --burst-throughput 300 \
  --db-p95-seconds 2 --loki-p95-seconds 5 \
  --end-to-end-p95-seconds 10 --consumer-lag 999 \
  --oldest-message-seconds 60
```

단위 테스트는 DB/Loki 오류, 중복 offset/event, Kafka commit 직전 재시작, broker poll 장애 후 복구, filesystem buffer 재전송과 목표 경계 판정을 검증한다.

```bash
python -m unittest discover -s tests -v
```

실제 서버 합격 판정은 Kafka broker, MariaDB, Loki가 연결된 상태에서 같은 목표를 60초 이상 측정해야 한다. server I/O가 포함되지 않은 local core 결과만으로 Part 6-18의 운영 합격을 선언하지 않는다.

## Loki masking and retention verification

보안 마스킹 로그에는 `pipeline=security-masked-logs`, `data_class=masked` 고정 label을
부여한다. sink는 메시지 전체를 검사해 주민번호·전화·이메일·카드번호·API key·JWT·
Authorization과 사설·Tailscale·내부 서비스 URL이 남아 있으면 Loki push 전에 거부한다.
`safe_metadata`, `masked_excerpt`, `error_message`에도 같은 검사를 적용한다.

실제 마스킹 메시지를 넣은 뒤 최근 1시간의 완료 로그와 Loki 30일 retention을 함께 검증한다.

```bash
python3 scripts/verify_loki_security.py \
  --loki-url http://127.0.0.1:3100 --lookback-hours 1
```

성공 출력의 `masked_log_count`는 1 이상, `retention_hours`는 720이어야 한다. 로그 생성 전
연결·설정만 확인할 때는 `--allow-empty`를 사용할 수 있지만 실제 적재 합격 판정으로는
인정하지 않는다. `scripts/observability-test.sh`도 read-only 방식으로 ready 상태와 runtime
retention 설정을 확인한다.

## Retention verification

아래 read-only 검사는 정리 기준을 넘긴 행 수를 반환한다. `kafka_consumption`은 14일,
`consumer_failure`와 완료 알림은 90일, security event는 365일 기준이며 한 건이라도
기한 초과 행이 있으면 종료 코드 1을 반환한다.

```bash
python3 scripts/verify_security_retention.py
```

실제 삭제 전에는 기본 dry-run으로 대상 수를 확인한다. `--execute`를 명시한 경우에만
삭제를 commit하며, 한 번의 실행량은 batch 크기와 최대 반복 횟수로 제한된다.

```bash
python3 scripts/run_security_retention.py --batch-size 1000 --max-batches 1
python3 scripts/run_security_retention.py --execute --batch-size 1000 --max-batches 10
python3 scripts/verify_security_retention.py
```

운영 서버에서는 `/etc/luck-security-retention.env`에 전용 DB 계정을 설정하고 권한을
`0600`으로 제한한 뒤 daily systemd timer를 설치한다. 설치 스크립트는 실수로 삭제가
시작되지 않도록 timer를 enable만 한다. dry-run 결과를 확인한 뒤 직접 시작한다.

```bash
sudo install -m 0600 security_retention.env.example /etc/luck-security-retention.env
sudo vi /etc/luck-security-retention.env
sudo bash scripts/security-retention-install.sh
sudo bash -c 'set -a; source /etc/luck-security-retention.env; set +a; exec /home/nginx/luck-nginx/.venv-security-sink/bin/python /home/nginx/luck-nginx/scripts/run_security_retention.py --batch-size 1000 --max-batches 1'
sudo systemctl start security-retention.timer
systemctl list-timers security-retention.timer --no-pager
```

## Sink metrics and scrape scope

두 sink worker는 별도 dependency 없이 Prometheus text format의 `/metrics`를 제공한다.
기본 포트는 security-event sink 9108, masked-log sink 9109이며 WAS Tailscale 주소에만
bind한다.

| Metric | Meaning |
|---|---|
| `luck_sink_messages_total` | 성공·중복·DLQ 결과별 누적 처리량 |
| `luck_sink_failures_total` | 단계별 실패 수 |
| `luck_sink_retries_total` | 단계별 재시도 수 |
| `luck_sink_dlq_total` | 단계별 DLQ 수 |
| `luck_sink_processing_duration_seconds` | 처리 지연 histogram |
| `luck_sink_commit_duration_seconds` | 동기 Kafka offset commit 지연 histogram |
| `luck_sink_end_to_end_duration_seconds` | source 발생부터 sink 완료까지 지연 histogram |
| `luck_consumer_lag_messages` | group/topic/partition별 high watermark lag |
| `luck_consumer_oldest_message_age_seconds` | backlog 처리 중인 가장 오래된 메시지 나이; lag 0이면 0 |

Prometheus는 `kafka-consumer-targets.yml`의 file discovery로 두 sink를 수집한다. 현재
책임 범위는 `security-event-sink`, `masked-log-sink` 두 consumer 전체다. 다른 팀 consumer도
동일 공통 metric을 제공하거나 Kafka exporter를 배치한 뒤 이 target 파일에 추가해야 전체
프로젝트 consumer 범위로 확장된다.

```bash
python3 scripts/verify_security_metrics.py \
  --prometheus-url http://127.0.0.1:9090 \
  --metrics-target http://100.117.253.9:9108 \
  --metrics-target http://100.117.253.9:9109
```

검증기는 두 `/metrics`의 필수 metric, Prometheus의 두 target `up=1`, metric 30일 retention을
함께 확인한다. 포트는 인터넷에 공개하지 않고 Nginx 서버에서 WAS Tailscale 경로로만 scrape한다.

## Scheduled work

알림과 정리 작업은 별도 worker 또는 cron이 주기적으로 실행한다.

- `notification_log.status=PENDING` 발송
- `FAILED` 알림의 `next_retry_at` 재시도
- 장기 미처리 `security_event` 알림
- retention 대상 DB 행 정리

초기 구현은 1분 주기 worker polling을 기본으로 한다. 알림 대기 행은 이벤트 저장 transaction과 함께 `notification_log`에 `PENDING`으로 기록하고, worker가 발송 성공 후 `SENT`로 변경한다. 발송 실패 시 `retry_count`, `next_retry_at`, 마스킹된 `last_error`를 갱신한다.

## Deployment, rollback, and recovery runbook

배포 전에는 저장소 revision, 설치된 systemd unit·Loki·Prometheus·Grafana provisioning
설정, `/etc/luck-*.env`의 존재 여부와 권한을 기록한다. secret 파일은 내용이 아니라 경로,
소유자, mode만 기록하며 백업본도 mode 0600을 유지한다. 배포 순서는 MariaDB migration →
Kafka·detector → sink·notifier·retention → Loki·Prometheus·Grafana → read-only health check다.

코드 rollback은 강제 reset이나 DB down migration 대신 검증된 이전 release commit을 새
revert commit으로 반영한 뒤 설치 스크립트를 재실행한다. 설정 rollback은 배포 직전 백업한
명시적 파일만 원래 경로로 복원하고 `systemctl daemon-reload` 후 의존 순서대로 재시작한다.
MariaDB migration은 운영 데이터가 존재하면 table을 drop하지 않는다. schema-only dump를
임시 database에 복원해 복구 가능성을 검증하고, 실제 장애 때는 승인된 전체 backup을 새
database에 복원·검증한 뒤 접속 대상을 전환한다.

rollback 중단 기준은 backup checksum 불일치, secret mode 0600 위반, schema/table 수
불일치, 서비스 inactive, Kafka lag 증가 지속, DB·Loki health 실패다. 복구 후에는 Kafka
lag 0, buffer 0, sink와 notifier active, MariaDB 정합성, Loki ready, Prometheus targets,
Grafana datasource·alert 상태를 순서대로 확인한다.

Part 13의 남은 운영 검증은 서버별 한 번의 진입점으로 수행한다. 두 명령 모두 기본값은
dry-run이며 `--execute`를 명시해야만 낮은 부하 시험 또는 임시 database 복원을 수행한다.

```bash
# Nginx/observability server
sudo bash scripts/run-part13-remaining.sh --execute

# MariaDB server: production data를 복사하거나 변경하지 않는 schema-only 임시 복원
sudo bash scripts/run-part13-rollback-rehearsal.sh --execute --cleanup-performance
```

Nginx 서버 명령의 성능 결과를 먼저 저장한 후 MariaDB 서버 명령을 실행한다. MariaDB 명령은
schema-only 복원 리허설이 성공한 경우에만 `p13perf-` 성능 fixture를 정리한다.

성능 시험이 목표에 미달해도 대량 본 시험은 실행되지 않는다. 최종 JSON과 MariaDB 복원
JSON을 함께 보존하고, 성능 목표·rollback 기준·서비스 상태가 모두 확인된 뒤에만 실제
서버 적용 결과를 완료로 기록한다.
