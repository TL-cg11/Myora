# A·B·C 연동 계약 v1 — B 구현 기준 초안

<!-- 문서 역할: A 입력, B 출력, C DB 매핑과 ID/시각/오류 규칙을 함께 설명한다. -->

이 파일과 `../contracts/v1/*.schema.json`은 B의 작업용 계약이다.
A·C가 이미 승인했다는 의미는 아니다. A 관리 공용 contracts로 옮길 때 검토한다.

## 입력

`NormalizedLog`는 schema_version, event_id, request_id, timestamp, environment,
service, source_type, event_name, severity, body, attributes를 모두 가진다.
request_id와 event_name은 null 가능하다. attributes가 없으면 A가 `{}`를 명시한다.
추가 최상위 필드는 거절하므로 확장 데이터는 attributes에 넣는다.

- timestamp: 시간대가 있는 ISO 8601. C 사건 시각은 UTC로 변환한다.
- identity/서비스/이벤트 필드: ASCII 영숫자로 시작하고 영숫자 및 `_.:/-`만 허용한다.
  민감정보 패턴이 탐지되면 해당 메시지를 거절한다. 이 필드에 사용자 데이터를 넣지 않는다.
- body: 문자열, 최대 100,000자. null은 거절한다.
- attributes: JSON object. 최대 깊이 12, 노드 5,000개.
- 전체 JSON 직렬화 크기: ASCII 이스케이프 기준 1,000,000자 이하.
- CLI 한 행: UTF-8 1,000,000바이트 이하. 중복 JSON 키와 NaN/Infinity는 거절한다.
- JSON object/array로 시작하는 문자열은 내부를 파싱해 구조화 민감 필드도 검사한다.
  해당 문자열이 잘못된 JSON이면 원문을 내보내지 않고 실패 처리한다.

## 출력 및 C DB 매핑

| B 출력 | C 저장 |
|---|---|
| MaskedLog 전체 | Loki. MariaDB에 원문 로그를 복사하지 않음 |
| SecurityEvent의 대표 필드 | `security_event` |
| `detections[]` 각 항목 | `security_event_detection` |
| `detections[].locations` | `security_event_detection.locations_json` |
| C에서 생성하는 사건 내부 PK | 자식 테이블의 `security_event_id` FK |
| 최초 생성 상태와 시각 | C가 `OPEN`, `created_at`, `updated_at` 설정 |
| 생성·상태변경 작업자/사유 | C가 `security_event_action`에 추가 |
| topic/partition/offset/group | Kafka 연결 후 C가 메시지 envelope에서 수집 |

MaskedLog.event_id는 A의 원본 ID를 그대로 유지한다.
SecurityEvent.source_event_id도 A의 원본 ID다. SecurityEvent.event_id는
`environment + service + 원본 event_id + detector_version + masking_policy_version`로
만든 UUID v5다. 동일 입력을 재처리하면 같은 사건 ID와 detection_id가 나온다.
A는 같은 원본 ID에 다른 payload를 재사용하지 않아야 한다.
탐지/정책 버전이 바뀌면 새 사건 ID가 생긴다. C가 다른 offset에서 같은 event_id를
받아도 기존 사건의 status/담당자/감사 이력을 덮어쓰지 말고 중복으로 처리한다.

한 로그에서 같은 규칙이 여러 번 탐지되면 한 detection으로 묶고 match_count와
locations에 담는다. 서로 다른 규칙은 별도 detection이다. AUTHORIZATION/JWT처럼
한 영역에서 두 규칙이 맞을 수 있으므로 규칙별 count 합은 개인정보 개수와 같지 않다.
DB URL 내부의 이메일처럼 문맥상 명백한 오탐은 상위 규칙으로 분류한다.

locations의 offset은 UTF-8 바이트가 아닌 Python Unicode 문자 인덱스이며 end는 제외한다.
경로 `@0`은 객체의 첫 번째 항목, `/0`은 배열의 첫 번째 항목이다.
`/json`은 문자열 내부 JSON 파싱 후의 값이다. 필드명 자체 유출을 막기 위해 객체 키를
경로에 복사하지 않는다. 구조화 비문자열 전체를 가린 경우 offset은 JSON 직렬화 값 기준이다.

safe_metadata는 초기 구현에서 `{}`로 고정한다. HTTP 경로 등을 복사할 때는 별도
허용 목록과 쿼리/동적 경로 마스킹 정책을 승인한 뒤 확장한다.

## 지문 정책

body_hash는 요청된 C 스키마에 맞춰 `sha256:` + hex 64자리다. SHA-256은 암호화나
익명화가 아니며 짧은 값은 사전 대입으로 추측할 수 있다. 접근 권한을 제한한다.

개별 evidence_fingerprint는 기본 null이다. 프로세스 환경변수
`DETECTOR_FINGERPRINT_KEY`에 UTF-8 기준 32바이트 이상의 비밀값을 주면
`hmac-sha256:` + hex 64자리(총 76자)를 기록하여 C의 VARCHAR(80)에 들어간다.
실제 키는 Git/fixture에 넣지 않는다. 한 규칙이 여러 번 탐지되면 대표 지문은 null이다.
HMAC 값 역시 연결 가능한 데이터이며 키 교체 전후 지문은 같지 않다.

## 실패와 재처리

실패 출력에는 schema_version, error_code, failure_stage, retryable,
detector_version과 CLI에서 붙이는 line_number만 남긴다. 원문 ID조차 오류 데이터에서
복사하지 않는다. 원본 payload, 원문 예외 메시지는 남기지 않는다.

- 잘못된 입력/지원하지 않는 버전/제한 초과: retryable=false. 원인을 수정한 뒤 재입력한다.
- 처리 중 예상치 못한 예외: PROCESSING_ERROR, retryable=true. 코드 문제 해결 후 재입력한다.
- 파일 기반 실패 출력 자체에는 원문이 없어 단독 replay할 수 없다.
  합성 입력 파일의 해당 행 또는 추후 접근 제한된 raw topic의 위치로 재처리한다.
- Kafka 연결 시 실제 위치 정보를 어댑터가 추가한다. 모든 결과의 발행 성공을 확인한 뒤
  원본 offset을 확정한다. 부분 발행·재처리 중복은 C의 event_id 멱등 저장으로 처리한다.
- C의 `kafka_consumption`에서 FAILED만 존재하는 것을 성공으로 취급하면 안 된다.
  같은 event_id의 다른 offset 중복도 정상 처리로 기록하되 사건 생성 이력은 한 번만 만든다.

## 검증 해석

평가는 로그별 규칙 존재 유무를 기준으로 TP/FP/FN을 계산한다. span 정확도나
개인정보 개별 개수 기준 NER 평가는 아니다. 계산할 분모가 0이면 metric은 null이다.
정답 마스킹 문자열/attributes도 별도로 정확히 비교한다. 현재 fixture는 개발 회귀
테스트이므로 F1=1.0이어도 운영 정확도 100%를 의미하지 않는다.
