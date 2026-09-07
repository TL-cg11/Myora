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

## Scheduled work

알림과 정리 작업은 별도 worker 또는 cron이 주기적으로 실행한다.

- `notification_log.status=PENDING` 발송
- `FAILED` 알림의 `next_retry_at` 재시도
- 장기 미처리 `security_event` 알림
- retention 대상 DB 행 정리

초기 구현은 1분 주기 worker polling을 기본으로 한다. 알림 대기 행은 이벤트 저장 transaction과 함께 `notification_log`에 `PENDING`으로 기록하고, worker가 발송 성공 후 `SENT`로 변경한다. 발송 실패 시 `retry_count`, `next_retry_at`, 마스킹된 `last_error`를 갱신한다.
