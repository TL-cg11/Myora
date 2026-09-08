# Security monitoring operations v1

## Retention and cleanup

초기 운영 기준이며 실제 트래픽과 보안 보존 요구에 따라 조정한다.

| Data | Retention | Cleanup |
|---|---:|---|
| `security_event` | 365일 | 감사 이력과 함께 아카이브 후 batch 삭제 |
| `security_event_detection` | 365일 | 부모 이벤트와 같은 기준으로 삭제 |
| `security_event_action` | 365일 | append-only 보존 후 부모 이벤트와 함께 아카이브 |
| `kafka_consumption` | 14일 | 메시지별 기록이므로 최우선 정리 대상 |
| `consumer_failure` | 90일 | DLQ 처리 완료 행부터 정리 |
| `notification_log` | 90일 | `SENT`, `SUPPRESSED` 완료 행부터 정리 |
| Loki logs | 30일 | Loki retention 설정 |
| Prometheus metrics | 30일 | Prometheus retention 설정 |

초기 버전은 FK와 운영 복잡도를 고려해 DB partition을 사용하지 않고 인덱스 기반 batch 삭제를 사용한다. 정리 worker는 한 transaction당 최대 10,000행을 처리하며, `security_event` 계열은 365일이 지난 이벤트·탐지·감사 이력을 함께 아카이브한 뒤 자식에서 부모 순서로 삭제한다. `kafka_consumption`은 `(consumer_group, topic_name, partition_number, message_offset)` 중복 방지 목적의 짧은 보존 데이터이므로 14일 이후 동일한 batch 방식으로 삭제한다.

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

## Scheduled work

알림과 정리 작업은 별도 worker 또는 cron이 주기적으로 실행한다.

- `notification_log.status=PENDING` 발송
- `FAILED` 알림의 `next_retry_at` 재시도
- 장기 미처리 `security_event` 알림
- retention 대상 DB 행 정리

초기 구현은 1분 주기 worker polling을 기본으로 한다. 알림 대기 행은 이벤트 저장 transaction과 함께 `notification_log`에 `PENDING`으로 기록하고, worker가 발송 성공 후 `SENT`로 변경한다. 발송 실패 시 `retry_count`, `next_retry_at`, 마스킹된 `last_error`를 갱신한다.
