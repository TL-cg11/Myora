# WAS JSON 로그 스키마 v1

`was-log-v1.schema.json`은 WAS가 Kafka topic `myohan.was.app`으로 발행하는 로그의
1차 계약이다. 사주·타로·관상 로그를 topic 하나에 모으고 최상위 `service` 값
(`saju`, `tarot`, `face`)으로 구분한다. Kafka 메시지 하나가 JSON 객체 하나에 해당한다.
기존 Nginx topic `myohan.nginx.access`의 flat 로그는 변경하지 않는다.

현재는 스키마만 정의한 상태다. WAS Kafka Producer가 아직 없으므로 `myohan.was.app`으로
실제로 발행되지는 않는다. Producer 구현 시 이 topic 하나만 사용한다.

## 이벤트

| event_type | 용도 | 추가 필수 필드 |
| --- | --- | --- |
| `api_request` | 클라이언트가 WAS API를 호출한 결과 | `method`, `uri`, `status`, `client_ip`, `processing_time` |
| `ai_request` | WAS가 DeepSeek에 요청을 보내기 직전 | `ai` |
| `ai_response` | WAS가 DeepSeek 응답을 받은 직후 | `ai` |
| `error` | 처리 중 오류 | `error` |

`service`와 `event_type`은 서로 다른 축이다. `service`는 어느 기능인지 나타내고,
`event_type`은 그 기능 안에서 무엇이 발생했는지를 나타낸다. 예를 들어 타로 상담의
DeepSeek 요청은 `service: "tarot"`, `event_type: "ai_request"`다.

`api_request`는 일반 기능만을 뜻하지 않고 WAS가 받은 HTTP 요청 전체를 뜻한다. 따라서
일반 사주·타로·관상 요청은 `api_request` 한 건이 생긴다. 상담 AI API 호출은 같은
`request_id`로 다음 흐름이 생긴다.

1. 상담 API가 요청을 받으면 `api_request`
2. WAS가 DeepSeek를 호출하기 직전에 `ai_request`
3. 응답을 받으면 `ai_response`, 실패하면 `error`

이렇게 해야 외부 AI를 호출하기 전의 HTTP 거부·검증 실패와 전체 응답 시간도 빠지지 않는다.
`request_id`는 Nginx에서 받은 값을 WAS와 외부 AI 호출까지 그대로 사용한다.
`timestamp`는 UTC RFC 3339,
`processing_time`과 `ai.latency`는 초 단위다. `uri`에는 query string을 넣지 않는다.
`user_id`는 서버가 인증한 값만 쓰며 현재는 로그인 기능이 없으므로 `null`이다.
현재 요청 소유자는 `guest_key`로 연결한다.

## PII 및 탐지 정책

여기서 공통은 로그인 회원의 계정 정보를 뜻하지 않는다. 여러 서비스에서 공통으로 나타날
수 있는 로그 입력 필드라는 뜻이다. 현재 DB와 API에 실제로 존재하는 값만 v1에 포함한다.
`input` 전체를 무조건 PII 탐지하지 않고 `was-log-masking-policy-v1.json`의 필드 경로별
정책을 적용한다.

| 필드 | PII | 처리 방식 | 내용 기반 탐지 |
| --- | --- | --- | --- |
| `user_id` | 예 | 가명처리 | 불필요 |
| `guest_key` | 예 | 가명처리 | 불필요 |
| `client_ip` | 예 | IP 마스킹 | 불필요 |
| `input.name` | 예 | 이름 마스킹 | 불필요 |
| `input.birth_date` | 예 | 날짜 마스킹 | 불필요 |
| `input.birth_time` | 예 | 시각 마스킹 | 불필요 |
| `input.question` | 예 | 탐지된 문자열 마스킹 | email, phone, name, birth date, address, credential 탐지 |
| `input.prompt` | 예 | 탐지된 문자열 마스킹 | email, phone, name, birth date, address, credential 탐지 |
| `input.topic` | 아니요 | 그대로 통과 | 하지 않음 |
| `input.gender` | 아니요 | 그대로 통과 | 하지 않음 |

`name`, `birth_date`, `birth_time`, `client_ip`처럼 필드 의미만으로 개인정보임을 알 수 있는
값은 탐지기를 돌리지 않고 필드별 마스킹을 바로 적용한다. `question`과 `prompt`는 자유
텍스트이므로 여러 PII 탐지기를 실행하고 탐지된 부분만 마스킹한다. 두 필드에는 Prompt
Injection 탐지도 함께 실행한다. `topic`과 `gender`는 값의 의미가 이미 정해져 있어 PII
내용 검사를 하지 않는다.

`input`에 정책이 없는 새 필드가 들어오면 임의로 통과시키지 않고 거부한다. 새 `input`
필드를 스키마에 추가할 때 마스킹 정책도 함께 지정해야 한다.

현재 `luck_db`에는 로그인 대비용 빈 `app_user` 테이블이 있고 `email`, `nickname`,
`password_hash`를 정의한다. `phone`과 `address` 컬럼은 없다. 로그인 기능이 아직 없으므로
이 계정값들은 현재 WAS 요청 로그에 들어오지 않는다. `email`은 로그인 구현 시에도 무조건
공통 로그에 싣지 않고, 이메일을 처리하는 보안 이벤트에서 탐지 목적이 명확할 때만 스키마
버전을 갱신해 추가한다.

현재 관상 기능은 사진 파일을 WAS에 업로드하거나 DB에 저장하지 않는다. 브라우저가 계산한
얼굴 비율만 전송하고 DB도 측정값만 저장하므로 `image_id`는 v1에서 제외한다. 향후 사진
저장 기능이 생기면 이미지/base64 대신 서버가 발급한 `image_id`만 새 필드로 추가한다.

## 생성 단계에서 제외할 값

아래 값은 사후 마스킹에 맡기지 않고 WAS 로그 생성 단계에서 제외한다.
`additionalProperties: false`로 정의되지 않은 필드도 거부한다.

- password, access token, refresh token
- Authorization 헤더, API key, secret key
- Cookie, Set-Cookie, session cookie 원문
- 전체 요청·응답 body와 얼굴 이미지/base64
- DB 연결 문자열과 SQL parameter

선택 필드 추가는 `1.x`, 기존 필드 삭제·타입·의미 변경은 새 major 버전으로 관리한다.
Producer 구현 시 발행 직전에 스키마를 검증하고 실패 메시지는 Kafka로 보내지 않는다.
