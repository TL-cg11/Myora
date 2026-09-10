# Security monitoring database schema v1

The executable v1 migration and its server-side verification script live in
`luck-mariadb` at `sql/migrate/2026-09-07_security_monitoring.sql` and
`scripts/test-security-monitoring-migration.sh`. Run them only on the MariaDB
server; `luck-nginx` retains the contract and design documentation.

이 문서는 `security_monitoring` database의 migration 원본 명세다. Part 5-7~5-12에서는 설계만 확정하고 실제 DB 생성·변경은 Part 5-15에서 수행한다. 테이블명은 단수형으로 통일한다.

## Common rules

- 모든 이벤트 시각은 UTC `DATETIME(3)`으로 저장한다.
- 모든 내부 PK는 `BIGINT UNSIGNED AUTO_INCREMENT`를 사용한다.
- `event_id`, `detection_id`는 producer가 생성하며 각각 UNIQUE로 관리한다.
- 원문 payload와 민감정보는 저장하지 않는다. `masked_excerpt`, `safe_metadata`, `error_message`는 마스킹 검사를 통과한 값만 허용한다.
- `security_event_action`은 INSERT만 허용하는 append-only 감사 이력이다.

## Tables

### `security_event`

| Column | Type | Null | Key / rule | Description |
|---|---|---:|---|---|
| `id` | BIGINT UNSIGNED | N | PK, auto increment | 내부 식별자 |
| `event_id` | VARCHAR(64) | N | UNIQUE | 보안 이벤트 ID |
| `source_event_id` | VARCHAR(64) | N | INDEX | 원본 로그 ID |
| `request_id` | VARCHAR(64) | Y | INDEX | 요청 추적 ID |
| `schema_version` | VARCHAR(16) | N |  | 메시지 계약 버전 |
| `occurred_at` | DATETIME(3) | N | INDEX | 원본 발생 시각 |
| `detected_at` | DATETIME(3) | N | INDEX | 탐지 시각 |
| `environment` | VARCHAR(32) | N |  | 실행 환경 |
| `source_service` | VARCHAR(64) | N | INDEX | 원천 서비스 |
| `source_type` | VARCHAR(64) | N |  | 로그·요청 유형 |
| `event_name` | VARCHAR(128) | Y |  | 이벤트 이름 |
| `risk_level` | ENUM('LOW','MEDIUM','HIGH','CRITICAL') | N | INDEX | 최종 위험등급 |
| `risk_score` | TINYINT UNSIGNED | N | CHECK 0~100 | 위험 점수 |
| `detector_version` | VARCHAR(32) | N |  | 탐지 프로그램 버전 |
| `masking_policy_version` | VARCHAR(32) | N |  | 마스킹 정책 버전 |
| `masked_excerpt` | VARCHAR(1000) | Y |  | 마스킹된 일부 내용 |
| `body_hash` | VARCHAR(80) | Y |  | 원문 SHA-256 지문 |
| `status` | ENUM('OPEN','INVESTIGATING','RESOLVED','FALSE_POSITIVE') | N | DEFAULT OPEN | 처리 상태 |
| `assigned_to` | VARCHAR(128) | Y | INDEX | 담당자 식별자 |
| `resolution_reason` | TEXT | Y |  | 처리·오탐 사유 |
| `resolved_at` | DATETIME(3) | Y |  | 처리 완료 시각 |
| `safe_metadata` | JSON | Y |  | 안전한 메타데이터 |
| `created_at` | DATETIME(3) | N | DEFAULT current timestamp | DB 생성 시각 |
| `updated_at` | DATETIME(3) | N | 자동 갱신 | 마지막 변경 시각 |

### `security_event_detection`

| Column | Type | Null | Key / rule | Description |
|---|---|---:|---|---|
| `id` | BIGINT UNSIGNED | N | PK, auto increment | 내부 식별자 |
| `security_event_id` | BIGINT UNSIGNED | N | FK, INDEX | `security_event.id` |
| `detection_id` | VARCHAR(64) | N | UNIQUE | 개별 탐지 ID |
| `rule_id` | VARCHAR(64) | N | INDEX | 탐지 규칙 ID |
| `rule_version` | VARCHAR(32) | N |  | 탐지 규칙 버전 |
| `category` | VARCHAR(32) | N | INDEX | PII·SECRET·BEHAVIOR |
| `entity_type` | VARCHAR(64) | N | INDEX | 탐지 정보 종류 |
| `risk_level` | ENUM('LOW','MEDIUM','HIGH','CRITICAL') | N |  | 개별 탐지 위험등급 |
| `confidence` | DECIMAL(5,4) | N | CHECK 0~1 | 탐지 신뢰도 |
| `match_count` | SMALLINT UNSIGNED | N | DEFAULT 1 | 탐지 횟수 |
| `evidence_fingerprint` | VARCHAR(80) | Y |  | 탐지원문 SHA-256 지문 |
| `locations_json` | JSON | Y |  | 필드·시작·종료 위치 |
| `created_at` | DATETIME(3) | N | INDEX, DEFAULT current timestamp | 저장 시각 |

### `security_event_action`

| Column | Type | Null | Key / rule | Description |
|---|---|---:|---|---|
| `id` | BIGINT UNSIGNED | N | PK, auto increment | 감사 이력 ID |
| `security_event_id` | BIGINT UNSIGNED | N | FK, INDEX | 대상 이벤트 |
| `action_type` | ENUM('CREATED','ASSIGNED','STATUS_CHANGED','COMMENTED','RESOLVED','MARKED_FALSE_POSITIVE','REOPENED') | N |  | 수행 작업 |
| `actor_type` | ENUM('SYSTEM','USER') | N |  | 시스템·사용자 |
| `actor_id` | VARCHAR(128) | N | INDEX | 수행자 식별자 |
| `previous_status` | VARCHAR(32) | Y |  | 변경 전 상태 |
| `new_status` | VARCHAR(32) | Y |  | 변경 후 상태 |
| `previous_assignee` | VARCHAR(128) | Y |  | 이전 담당자 |
| `new_assignee` | VARCHAR(128) | Y |  | 새 담당자 |
| `reason` | TEXT | Y |  | 작업 사유 |
| `acted_at` | DATETIME(3) | N | INDEX, DEFAULT current timestamp | 작업 시각 |

### `kafka_consumption`

메시지마다 1행을 저장한다. 파티션별 현재 위치를 저장하는 테이블이 아니다.

| Column | Type | Null | Key / rule | Description |
|---|---|---:|---|---|
| `id` | BIGINT UNSIGNED | N | PK, auto increment | 처리 기록 ID |
| `consumer_group` | VARCHAR(128) | N | 복합 UNIQUE | Consumer Group |
| `topic_name` | VARCHAR(128) | N | 복합 UNIQUE | 수신 Topic |
| `partition_number` | INT UNSIGNED | N | 복합 UNIQUE | Partition 번호 |
| `message_offset` | BIGINT UNSIGNED | N | 복합 UNIQUE | Kafka offset |
| `message_key` | VARCHAR(128) | Y |  | Kafka key |
| `payload_hash` | VARCHAR(80) | Y |  | Payload SHA-256 지문 |
| `event_id` | VARCHAR(64) | Y | INDEX | 연결 이벤트 ID |
| `processing_status` | ENUM('PROCESSED','FAILED','DLQ') | N |  | 처리 결과 |
| `processed_at` | DATETIME(3) | N | INDEX, DEFAULT current timestamp | 처리 시각 |

복합 UNIQUE 키는 `(consumer_group, topic_name, partition_number, message_offset)`로 한다.

### `consumer_failure`

| Column | Type | Null | Key / rule | Description |
|---|---|---:|---|---|
| `id` | BIGINT UNSIGNED | N | PK, auto increment | 실패 기록 ID |
| `consumer_group` | VARCHAR(128) | N | 복합 UNIQUE | Consumer Group |
| `source_topic` | VARCHAR(128) | N | 복합 UNIQUE | 실패 Topic |
| `partition_number` | INT UNSIGNED | N | 복합 UNIQUE | Partition 번호 |
| `message_offset` | BIGINT UNSIGNED | N | 복합 UNIQUE | Kafka offset |
| `event_id` | VARCHAR(64) | Y | INDEX | 관련 이벤트 ID |
| `payload_hash` | VARCHAR(80) | Y |  | Payload 지문 |
| `failure_stage` | VARCHAR(64) | N |  | 실패 단계 |
| `error_code` | VARCHAR(64) | Y |  | 오류 코드 |
| `error_message` | VARCHAR(1000) | N |  | 마스킹된 오류 내용 |
| `retry_count` | INT UNSIGNED | N | DEFAULT 0 | 재시도 횟수 |
| `retry_status` | ENUM('PENDING','RETRYING','RECOVERED','DLQ','DISCARDED') | N | DEFAULT PENDING | 재처리 상태 |
| `first_failed_at` | DATETIME(3) | N | DEFAULT current timestamp | 최초 실패 |
| `last_failed_at` | DATETIME(3) | N | INDEX, DEFAULT current timestamp | 최근 실패 |
| `recovered_at` | DATETIME(3) | Y |  | 복구 완료 |

### `notification_log`

알림 발송 대기열과 발송 이력을 겸한다. `dedup_key`는 동일 이벤트의 중복 발송을 막는 UNIQUE 키다.

| Column | Type | Null | Key / rule | Description |
|---|---|---:|---|---|
| `id` | BIGINT UNSIGNED | N | PK, auto increment | 알림 기록 ID |
| `dedup_key` | VARCHAR(255) | N | UNIQUE | `event_id+alert_type+channel` |
| `event_id` | VARCHAR(64) | Y | INDEX | 관련 이벤트 ID |
| `alert_type` | VARCHAR(64) | N |  | 알림 유형 |
| `channel` | ENUM('DISCORD','SLACK','EMAIL') | N |  | 신규 발송은 Discord만 사용하며 Slack·Email은 기존 이력 호환용 |
| `status` | ENUM('PENDING','SENDING','SENT','FAILED','SUPPRESSED') | N | DEFAULT PENDING | 발송 상태 |
| `retry_count` | INT UNSIGNED | N | DEFAULT 0 | 재시도 횟수 |
| `next_retry_at` | DATETIME(3) | Y | INDEX | 다음 재시도 시각 |
| `last_error` | VARCHAR(1000) | Y |  | 마스킹된 오류 |
| `scheduled_at` | DATETIME(3) | N | INDEX | 발송 예정 시각 |
| `sent_at` | DATETIME(3) | Y |  | 발송 완료 시각 |
| `created_at` | DATETIME(3) | N | DEFAULT current timestamp | 생성 시각 |
| `updated_at` | DATETIME(3) | N | 자동 갱신 | 변경 시각 |

### `security_user`

기존 인증 서비스의 사용자를 보안 권한에 연결하는 최소 모델이다. 토큰과 비밀번호는 저장하지 않는다. 이벤트의 `assigned_to`와 감사 이력의 `actor_id`는 기록 보존을 위해 문자열 식별자로 유지하고 이 테이블에 FK를 걸지 않는다.

| Column | Type | Null | Key / rule | Description |
|---|---|---:|---|---|
| `id` | BIGINT UNSIGNED | N | PK, auto increment | 내부 사용자 ID |
| `actor_id` | VARCHAR(128) | N | UNIQUE | 외부 인증 사용자 식별자 |
| `display_name` | VARCHAR(128) | N |  | 표시 이름 |
| `status` | ENUM('ACTIVE','DISABLED') | N | DEFAULT ACTIVE | 계정 상태 |
| `created_at` | DATETIME(3) | N | DEFAULT current timestamp | 생성 시각 |
| `updated_at` | DATETIME(3) | N | 자동 갱신 | 변경 시각 |

### `security_role`

| Column | Type | Null | Key / rule | Description |
|---|---|---:|---|---|
| `id` | SMALLINT UNSIGNED | N | PK, auto increment | 역할 ID |
| `role_code` | VARCHAR(32) | N | UNIQUE | VIEWER·EDITOR·ADMIN |
| `description` | VARCHAR(255) | Y |  | 역할 설명 |
| `created_at` | DATETIME(3) | N | DEFAULT current timestamp | 생성 시각 |

### `security_user_role`

| Column | Type | Null | Key / rule | Description |
|---|---|---:|---|---|
| `user_id` | BIGINT UNSIGNED | N | PK, FK | `security_user.id`, 사용자 삭제 시 CASCADE |
| `role_id` | SMALLINT UNSIGNED | N | PK, FK | `security_role.id`, 역할 삭제 시 RESTRICT |
| `created_at` | DATETIME(3) | N | DEFAULT current timestamp | 역할 부여 시각 |

복합 PK는 `(user_id, role_id)`로 하며 한 사용자에게 같은 역할을 중복 부여할 수 없다.
