# Security monitoring contracts

이 디렉터리는 보안 저장 파트가 소비하는 Kafka 메시지 계약 v1을 관리한다.

| Topic | Schema | Producer | Consumer destination |
|---|---|---|---|
| `luck.security-events` | `luck.security-events.v1.schema.json` | 보안 탐지·마스킹 담당(B) | `security_monitoring` DB |
| `luck.masked-logs` | `luck.masked-logs.v1.schema.json` | 보안 탐지·마스킹 담당(B) | Loki |

`source_event_id`는 원본 로그 수집 담당(A)이 만든 ID를 B가 보안 이벤트에 전달한다. `event_id`와 `detection_id`는 B가 생성하며 각각 보안 이벤트와 개별 탐지에서 전역적으로 중복되지 않아야 한다. 시간 필드는 UTC ISO 8601(`Z`)을 사용하고 현재 지원 버전은 `schema_version=1.0`이다.

DB의 내부 PK, 처리 상태, 담당자, 해결 사유와 생성·수정 시각은 메시지에 포함하지 않고 sink 또는 API가 관리한다. 계약의 필드 삭제·타입 변경·필수 여부 강화는 호환되지 않는 변경이므로 새 major schema version과 새 계약 파일로 배포한다.

`safe_metadata`, `masked_excerpt`, `masked_message`에는 주민번호, 전화번호, 이메일, 카드번호, API Key, JWT, Authorization 값과 내부 URL 원문을 포함하면 안 된다. JSON Schema 통과 여부는 민감정보 제거를 보장하지 않으므로 sink에서도 별도의 안전성 검사를 수행한다.

## Local mock producer

Kafka 없이 계약 메시지를 확인하려면 저장소 루트에서 실행한다.

```bash
python scripts/mock_security_producer.py --topic luck.security-events --fixture fixtures/luck.security-events.normal.json
python scripts/mock_security_producer.py --topic luck.security-events --fixture fixtures/luck.security-events.duplicate.json --repeat 2
python scripts/mock_security_producer.py --topic luck.masked-logs --fixture fixtures/luck.masked-logs.normal.json --output tmp/masked-logs.jsonl
```

기본 동작은 topic의 JSON Schema 파일을 읽어 현재 계약이 사용하는 type, required, additionalProperties, const, enum, 길이, 정규식, 범위, 배열, 로컬 `$ref`, UTC date-time 규칙을 검증한 뒤 JSONL envelope를 출력하는 것이다. 의도적인 오류 fixture는 `--no-validate`를 붙여 DLQ 테스트 입력으로 생성한다.

```bash
python -m unittest discover -s tests -v
```

DB 컬럼·키·보존·처리량 기준은 [`docs/security-monitoring-schema.md`](../docs/security-monitoring-schema.md)와 [`docs/security-monitoring-operations.md`](../docs/security-monitoring-operations.md)를 기준으로 한다.
