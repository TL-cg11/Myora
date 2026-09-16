# WAS 로그 스키마 v1.0

`luck-was`에서 생성하는 WAS JSON 로그의 구조를 정의한다. 기준 문서는
`WAS_LOG_SCHEMA.md`이며 Kafka 메시지 하나가 JSON 객체 하나에 해당한다. WAS는
`confluent-kafka` Producer로 topic `myohan.was.app`에 직접 전송하고 message key에는
`request_id`를 사용한다.

## 로그 분류

| 필드 | 타입 | 필수 | 값 | 설명 |
| --- | --- | --- | --- | --- |
| `source` | string | 예 | `was` | 로그 출처 |
| `service` | string | 예 | `luck-was` | 로그를 생성한 실행 서비스 |
| `feature` | string | 예 | `saju`, `tarot`, `face` | WAS 내부 기능 |
| `event_type` | string | 예 | `api_request`, `ai_request`, `chat_request`, `chat_response` | 이벤트 종류 |

## 공통 필드

`schema_version`, `event_id`, `request_id`, `timestamp`, `environment`, `severity`,
`source`, `service`, `feature`, `event_type`, `user_id`, `guest_key`는 모든 이벤트에
포함한다. `user_id`와 `guest_key`는 키를 포함하되 값이 없으면 `null`을 사용한다.

- `event_id`: 로그 한 건의 UUID
- `request_id`: Nginx와 WAS 로그를 연결하는 요청 ID
- `timestamp`: `Z`로 끝나는 ISO 8601 UTC 시각
- `environment`: 실행 환경. 전체 허용 값은 아직 확정하지 않는다.
- `severity`: 로그 수준. 전체 허용 값은 아직 확정하지 않는다.

한 요청에서 API 요청 로그와 AI 요청 로그가 발생하면 `request_id`는 같고 `event_id`는
로그마다 다르다.

## chat_request / chat_response

사용자 질문과 확정된 답변은 각각 `chat_request`, `chat_response` 이벤트로 분리한다.
두 이벤트는 동일한 `request_id`와 Kafka message key를 사용해 서로 연결되며 `event_id`는
각각 다르다. `chat_request`에는 `input.question`만, `chat_response`에는
`output.answer`만 들어가므로 마스킹 후 Loki에도 요청과 응답이 별도 로그 줄로 저장된다.

배포 전에 Kafka에 들어간 `chat_exchange`는 backlog 호환을 위해 스키마에서 계속
허용하지만 새 이벤트로 생성하지 않는다.

## api_request

`api_request`는 요청 처리가 끝난 뒤 기록하며 다음 필드를 추가로 요구한다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `method` | string | HTTP 메서드 |
| `uri` | string | API URI |
| `status` | integer | HTTP 응답 상태 코드 |
| `client_ip` | string | 클라이언트 IP |
| `processing_time` | number | 초 단위 처리 시간 |
| `input` | object | 요청별 사용자 입력 |
| `metadata` | object | 요청 관련 부가 정보 |

현재 `input`에는 최신 타로 예시에서 확정된 `topic`, `question`만 정의한다.
`metadata`에는 `content_length`(바이트), `reading_id`만 정의한다.

## ai_request

`ai_request`는 WAS가 DeepSeek를 실제 호출하기 직전에 기록한다. API key가 없거나 타로가
규칙 기반 답변을 사용해 외부 호출을 시도하지 않으면 생성하지 않는다.

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `ai_call_id` | UUID string | 향후 AI 응답·오류 로그와 연결할 호출 ID |
| `ai.provider` | string | `deepseek` 고정 |
| `ai.model` | string | 실제 요청 모델 |
| `ai.timeout_seconds` | number | 해당 호출에 적용한 timeout |
| `input.question` | string | 사용자가 이번에 직접 입력한 질문 |
| `metadata.reading_id` | integer | 연결된 리딩이 있을 때 포함 |
| `metadata.question_sequence` | integer | 현재 사용자 질문 순번 |
| `metadata.message_count` | integer | AI 요청 메시지 개수 |
| `metadata.context_length` | integer | 상담 context 문자 수 |
| `metadata.prompt_length` | integer | 사용자 질문 문자 수 |

전체 system prompt, 상담 context 원문, 이전 대화 전문과 Authorization/API key는 로그에
넣지 않는다. `input.question`은 PII 마스킹 및 Prompt Injection 탐지를 위해 원문으로
Consumer에 전달한다.

## 마스킹 정책

`was-log-masking-policy-v1.json`은 현재 확정된 필드만 다룬다. `user_id`, `guest_key`,
`client_ip`는 필드 기준으로 처리하고, 자유 텍스트인 `input.question`은 내용 기반 PII 및
Prompt Injection 탐지 대상으로 둔다. 값이 정해진 `input.topic`은 그대로 통과시킨다.

새 `input` 필드는 로그 스키마와 마스킹 정책이 함께 확정되기 전까지 허용하지 않는다.

Producer, Consumer, 서버 테스트 및 systemd 운영 방법은
[Kafka 로깅과 Consumer 운영 가이드](../consumer/README.md)를 참고한다.
