# Security monitoring foundation

## Database boundary

운영 단순성과 보안 경계를 함께 유지하기 위해 기존 MariaDB 인스턴스를 공유하되 애플리케이션 DB와 분리된 `security_monitoring` database를 사용한다. 애플리케이션 서비스 계정에는 기본적으로 접근 권한을 부여하지 않는다.

계정은 다음 책임으로 분리한다.

| Account role | Permission |
|---|---|
| migration | `security_monitoring`의 DDL 및 migration 수행 |
| sink | 이벤트·탐지·소비·실패·시스템 감사 행의 `SELECT`, `INSERT`와 필요한 제한적 `UPDATE` |
| API | 위험 이벤트 조회·상태 변경 및 감사 행 `INSERT` |
| readonly | 대시보드와 운영 조회를 위한 `SELECT` |

비밀번호와 접속 문자열은 저장소에 커밋하지 않고 서버의 환경 변수 또는 secret 파일로 주입한다. 실제 계정명과 GRANT 문은 Part 5의 테이블 설계 및 migration 단계에서 확정한다.

## Worker accounts

The notifier and retention jobs are separate processes, so neither reuses the
DDL-capable migration account. These roles extend the account boundary above.

| Account role | Permission |
|---|---|
| notifier | `notification_log` `SELECT`, `UPDATE`; `security_event` `SELECT` only for message composition |
| retention | `SELECT`, `DELETE` only on `security_event_detection`, `security_event_action`, `security_event`, `kafka_consumption`, `consumer_failure`, and `notification_log` |

The retention worker deletes `security_event_detection` and
`security_event_action` before `security_event`, in bounded batches. It has no
DDL, INSERT, or UPDATE privilege. The notifier has no event INSERT, DELETE, or
UPDATE privilege.

## Validation and failure policy

sink는 메시지를 처리하기 전에 topic에 대응하는 JSON Schema와 `schema_version`을 검증한다.

| Failure | Retry | Destination | Offset commit |
|---|---:|---|---:|
| JSON 파싱 실패 | 없음 | sink DLQ | DLQ 발행 성공 후 |
| 미지원 schema version | 없음 | sink DLQ | DLQ 발행 성공 후 |
| 필수 필드·타입·범위 오류 | 없음 | sink DLQ | DLQ 발행 성공 후 |
| 민감정보 안전성 검사 실패 | 없음 | sink DLQ | DLQ 발행 성공 후 |
| DB·Loki·Kafka 일시 장애 | 지수 백오프로 최대 5회 | 재시도 소진 후 sink DLQ | 성공 또는 DLQ 발행 후 |
| 중복 `event_id` 또는 처리 offset | 없음 | 멱등 성공 처리 | 수행 |

재시도 대기 시간은 1초부터 시작해 최대 30초로 제한한다. DLQ 메시지에는 원문 대신 원본 topic·partition·offset, message key, payload hash, schema version, 오류 코드와 마스킹된 오류 설명만 기록한다.

`luck.masked-logs`의 일시 장애가 재시도를 소진하면 schema와 마스킹 안전성 검사를 통과한 payload를 권한 0600의 filesystem buffer에 원자 저장한 뒤 sink DLQ로 보낸다. buffer는 주기적으로 Loki에 재전송하고 성공한 파일만 삭제하며, 제한 용량을 넘으면 source offset을 commit하지 않아 유실 대신 backpressure를 선택한다.

Loki push와 DB·Kafka offset commit은 하나의 transaction이 될 수 없으므로 masked-log sink는 at-least-once를 보장한다. Loki 성공 후 프로세스가 중단되면 같은 로그가 재전송될 수 있으며, 운영 조회에서는 log line의 `event_id`로 중복을 식별한다.

## DLQ ownership

저장 파트(C)는 아래 sink 전용 DLQ의 메시지 형식, 발행 코드, 재처리 정책을 소유한다. Kafka 토픽 생성·TLS/SASL·ACL은 Kafka 담당(A)에게 요청한다.

| Source | Sink DLQ | Owner |
|---|---|---|
| `luck.security-events` | `luck.security-events.sink-dlq` | C |
| `luck.masked-logs` | `luck.masked-logs.sink-dlq` | C |

B의 탐지·마스킹 처리 중 발생한 실패는 B의 retry/DLQ 범위이며 sink DLQ와 섞지 않는다. C의 consumer group은 `security-event-sink`와 `masked-log-sink`를 사용하고 각 그룹에는 source topic consume 및 해당 sink DLQ produce 권한만 부여한다.
