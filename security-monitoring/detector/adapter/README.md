# Kafka 마스킹 어댑터

<!-- 문서 역할: 원본 로그 topic과 결과 topic을 잇는 실행 방법과 필드 매핑을 설명한다. -->

A가 수집한 원본 로그를 읽어 `schemas/was-log-masking-policy-v1.json` 정책대로 마스킹한 뒤
C가 소비하는 결과 topic으로 다시 발행한다. 탐지·마스킹 자체는 `app/` 엔진이 하고,
이 패키지는 정책 적용, 스키마 변환, Kafka 연결만 담당한다.

```text
myohan.was.app      ┐                                  ┌ myohan.masked-logs    → Loki
                    ├→ adapter → app.process_log →─────┤ myohan.security-events → MariaDB
myohan.nginx.access ┘                                  └ myohan.dead-letter     → 재처리 도구
```

## Topic

| 구분 | Topic | 설명 |
|---|---|---|
| 입력 | `myohan.was.app` | WAS가 직접 보내는 `was-log-v1` JSON 로그 |
| 입력 | `myohan.nginx.access` | Fluent Bit이 보내는 Nginx access 로그 |
| 출력 | `myohan.masked-logs` | 마스킹 로그. `contracts/consumer`의 계약을 따른다 |
| 출력 | `myohan.security-events` | 탐지가 있는 로그의 보안 이벤트 |
| 출력 | `myohan.dead-letter` | 원문 없는 실패 메타데이터 |

message key는 `request_id`(없으면 `event_id`)를 사용해 같은 요청의 결과가 같은 partition에
순서대로 쌓이게 한다. Consumer group 기본값은 `myohan-security-masking`이며 A의 두 확인용
Consumer와 group이 겹치지 않는다.

## C 담당이 가져가는 곳

결과 topic의 소비자는 `luck-nginx` 저장소의 sink 두 개다.

| 소비 프로세스 | 구독해야 할 Topic | Consumer group | 저장 위치 |
|---|---|---|---|
| `python -m security_sink.masked_worker` | `myohan.masked-logs` | `masked-log-sink` | Loki (`LOKI_URL`, 기본 `http://127.0.0.1:3100`) |
| `python -m security_sink.worker` | `myohan.security-events` | `security-event-sink` | MariaDB `security_monitoring` |

- Loki에는 `pipeline=security-masked-logs`, `data_class=masked`, `environment`,
  `source_service`, `source_type` 라벨이 붙고 `event_id`, `request_id`,
  `masking_policy_version`, `masked_message`, `body_hash`, `safe_metadata`가 로그 줄에 들어간다.
- MariaDB에는 보안 이벤트가 `security_event`, `detections[]`가 `security_event_detection`,
  Kafka 처리 이력이 `kafka_consumption`에 들어간다. `security_event.event_id`가 UNIQUE라
  같은 메시지를 다시 받아도 사건이 중복 생성되지 않는다.
- Grafana는 Loki datasource(`uid: loki`)와 MariaDB datasource
  (`uid: security-monitoring-mysql`, database `security_monitoring`)로 두 저장소를 함께 본다.

### C 쪽에서 함께 바꿔야 하는 것

sink는 topic 이름을 계약 문서의 `luck.*`로 코드에 고정하고 있다. 운영 topic 이름을
`myohan.*`로 정했으므로 아래 다섯 곳을 함께 바꿔야 연결된다. 메시지 본문(계약 v1)은
바뀌지 않으므로 스키마와 DB 스키마는 그대로 둔다.

| 파일 | 위치 | 바꿀 값 |
|---|---|---|
| `security_sink/masked_logs.py` | `TOPIC` | `myohan.masked-logs` |
| `security_sink/masked_worker.py` | `consumer.subscribe([...])`와 metric 라벨 | `myohan.masked-logs` |
| `security_sink/security_events.py` | `TOPIC` | `myohan.security-events` |
| `security_sink/worker.py` | `consumer.subscribe([...])`와 metric 라벨 | `myohan.security-events` |
| `security_sink/resilience.py` | `DLQ_TOPICS` 키 | `myohan.*`(값은 `myohan.*.sink-dlq`) |

`masked_logs.py`와 `security_events.py`는 받은 메시지의 topic이 `TOPIC`과 다르면 거절하고,
`resilience.DLQ_TOPICS`는 topic 이름으로 사전을 찾으므로 이 다섯 곳 중 하나라도 빠지면
메시지를 못 받거나 DLQ 발행에서 KeyError가 난다. `scripts/mock_security_producer.py`의
`TOPICS`도 같은 이름을 쓰면 mock 검증 도구를 그대로 쓸 수 있다.

sink는 자체 재시도 후 실패한 메시지를 `<topic>.sink-dlq`로 보낸다. 어댑터의
`myohan.dead-letter`와는 다른 topic이며 어댑터 쪽은 마스킹 이전 단계의 실패,
sink 쪽은 저장 단계의 실패를 뜻한다.

발행하는 메시지는 C의 sink가 실제로 쓰는 검증기
(`scripts.mock_security_producer.validate`, `security_sink.common.validate_masking_safety`)를
그대로 통과한다. 계약 사본과 검증은 `tests/test_adapter_contract.py`에 있다.

## 실행

```bash
cd ~/luck-was/security-monitoring/detector
../../.venv/bin/python -m adapter
```

`confluent-kafka`는 `luck-was/requirements.txt`에 있다. 엔진과 테스트는 표준 라이브러리만
사용하므로 어댑터를 실행할 때만 이 의존성이 필요하다.

```powershell
python -m unittest discover -s tests -v
```

## 마스킹 결과 확인

어댑터는 이 프로세스가 떠 있을 때만 동작한다. 실행하지 않으면 원본 topic만 쌓이고
결과 topic에는 아무것도 들어가지 않는다. 확인 순서는 아래와 같다.

### 1. Kafka 없이 (--dry-run)

원본 로그 JSON을 한 줄에 하나씩 넣으면 발행할 메시지를 그대로 출력한다.

```bash
echo '{"timestamp":"2026-09-09T04:57:50+00:00","source":"nginx","request_id":"9974759eee4d477ea40fcc3251e41e54","client_ip":"127.0.0.1","method":"GET","uri":"/api/tarot/spreads","status":200,"bytes_sent":1083,"request_time":0.016,"referer":"","user_agent":"curl/8.5.0"}' \
  | MASKING_PSEUDONYM_KEY=$MASKING_PSEUDONYM_KEY python -m adapter --dry-run - --dry-run-topic myohan.nginx.access
```

WAS 로그는 `--dry-run-topic myohan.was.app`(기본값)을 사용한다. 파일을 넘겨도 된다.

### 2. 결과 topic에서

어댑터를 띄운 뒤 다른 터미널에서 결과 topic을 직접 읽는다.

```bash
kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic myohan.masked-logs --from-beginning
kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic myohan.security-events --from-beginning
kafka-console-consumer.sh --bootstrap-server localhost:9092 --topic myohan.dead-letter --from-beginning
```

세 topic이 없으면 먼저 만든다.

```bash
for topic in myohan.masked-logs myohan.security-events myohan.dead-letter; do
  kafka-topics.sh --bootstrap-server localhost:9092 --create --if-not-exists --topic "$topic" --partitions 3 --replication-factor 1
done
```

### 3. 처리 상태에서

어댑터 로그에 읽은 건수, 마스킹 건수, 보안 이벤트 건수, 실패 건수가 남는다.

```bash
sudo journalctl -u luck-masking-adapter -f
kafka-consumer-groups.sh --bootstrap-server localhost:9092 --describe --group myohan-security-masking
```

`LAG`가 계속 늘면 어댑터가 멈췄거나 발행에 실패하고 있다는 뜻이다.

### 4. Grafana에서

`myohan.masked-logs`는 C의 sink가 Loki로 넣고 `myohan.security-events`는 MariaDB에 저장한다.
Grafana 화면에서 보이는 시점은 C의 sink가 함께 떠 있을 때다.

## 환경변수

`luck-was/.env`를 그대로 읽는다. `python-dotenv`가 없으면 프로세스 환경변수만 사용한다.

| 이름 | 기본값 | 설명 |
|---|---|---|
| `KAFKA_BOOTSTRAP_SERVERS` | `localhost:9092` | Broker 주소 |
| `MASKING_PSEUDONYM_KEY` | 없음(필수) | `user_id`·`guest_key` 가명화 HMAC 키. UTF-8 32바이트 이상 |
| `DETECTOR_FINGERPRINT_KEY` | 없음 | 탐지 증거 지문 HMAC 키. 없으면 지문을 남기지 않는다 |
| `ADAPTER_GROUP_ID` | `myohan-security-masking` | 원본 topic consumer group |
| `ADAPTER_INPUT_TOPICS` | `myohan.was.app,myohan.nginx.access` | 소비할 원본 topic |
| `ADAPTER_WAS_TOPIC` / `ADAPTER_NGINX_TOPIC` | 위와 동일 | 어느 정규화기를 쓸지 판단하는 기준 |
| `ADAPTER_MASKED_LOGS_TOPIC` | `myohan.masked-logs` | 마스킹 로그 발행 topic |
| `ADAPTER_SECURITY_EVENTS_TOPIC` | `myohan.security-events` | 보안 이벤트 발행 topic |
| `ADAPTER_DEAD_LETTER_TOPIC` | `myohan.dead-letter` | 실패 메타데이터 발행 topic |
| `ADAPTER_DEFAULT_ENVIRONMENT` | `production` | 원본에 `environment`가 없을 때 사용할 값 |
| `KAFKA_AUTO_OFFSET_RESET` | `earliest` | 저장된 offset이 없을 때 시작 위치 |
| `ADAPTER_PUBLISH_ATTEMPTS` | `3` | 결과 발행 재시도 횟수 |
| `ADAPTER_POLL_TIMEOUT` / `ADAPTER_FLUSH_TIMEOUT` | `1.0` / `10.0` | poll·flush 대기 시간(초) |
| `DETECTOR_NER_ENABLED` | `false` | 자유 텍스트 인명·장소 NER 활성화 |
| `DETECTOR_NER_MODEL` | `Leo97/KoELECTRA-small-v3-modu-ner` | Hugging Face 모델 ID 또는 로컬 모델 경로 |
| `DETECTOR_NER_THRESHOLD` | `0.85` | NER 마스킹 최소 신뢰도(0~1) |
| `DETECTOR_NER_LOCAL_FILES_ONLY` | `false` | `true`이면 캐시에 있는 모델만 사용 |
| `DETECTOR_PII_CONTEXT_ENABLED` | `false` | 전화·이메일 정규식 후보의 한국어 문맥 재검증 활성화 |
| `DETECTOR_PII_CONTEXT_MODEL` | `Huffon/klue-roberta-base-nli` | Hugging Face 한국어 NLI 모델 또는 로컬 경로 |
| `DETECTOR_PII_CONTEXT_NON_PII_THRESHOLD` | `0.90` | 후보를 비개인정보로 승인할 최소 점수(0.5~1) |
| `DETECTOR_PII_CONTEXT_LOCAL_FILES_ONLY` | `false` | `true`이면 캐시에 있는 문맥 모델만 사용 |
| `KAFKA_SECURITY_PROTOCOL` 등 | 없음 | SASL/TLS 옵션. luck-nginx sink와 같은 이름을 쓴다 |

`MASKING_PSEUDONYM_KEY`가 없거나 짧으면 프로세스가 시작하지 않는다. 키 없이 만든 가명은
`user_id` 같은 좁은 값에서 사전 대입으로 원본을 되찾을 수 있기 때문이다. 키를 바꾸면 이전
가명과 연결되지 않는다.

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## 마스킹 정책 적용

`schemas/was-log-masking-policy-v1.json`을 그대로 읽어 필드마다 처리 방식을 정한다.
정책 파일에 없는 처리 방식이 들어 있으면 실행 전에 실패한다.

| 정책 action | 어댑터 동작 |
|---|---|
| `pseudonymize` | 필드 이름을 섞은 HMAC-SHA256 토큰(`user_id_…`)으로 바꾼다 |
| `mask_ip` | IPv4는 `/24`, IPv6는 `/48`만 남긴다. 형식이 아니면 `[REDACTED_IP]` |
| `detect_and_mask` | 본문으로 올려 `app/` 엔진의 내용 기반 탐지·마스킹을 적용한다 |
| `pass` | 값을 유지한다. 속성도 엔진이 다시 검사한다 |
| `drop` | 결과에서 제외한다 |
| `default.unknown_input_field_action` | 정책에 없는 `input` 하위 필드가 오면 메시지를 거절한다 |

`input.question`은 `prompt_injection_detection`이 켜져 있어 `adapter/prompt_injection.py`의
규칙도 함께 적용한다. Prompt Injection은 마스킹 대상이 아니라 탐지 전용이므로 본문은
그대로 두고 `PROMPT_INJECTION` 탐지만 보안 이벤트에 추가한다.

Nginx 전용 정책 파일은 아직 없다. 같은 정책의 필드 규칙을 이름이 같은 필드(`client_ip` 등)에
적용하고 나머지는 통과시킨다. 질의 문자열은 속성에서 떼어 본문에서 검사한다.
현재 확인한 access 로그 필드는 `timestamp`, `source`, `request_id`, `client_ip`, `method`,
`uri`, `status`, `bytes_sent`, `request_time`, `referer`, `user_agent`이며 `environment`가
없으므로 `ADAPTER_DEFAULT_ENVIRONMENT` 값을 사용한다.

## 필드 매핑

| 원본(WAS) | NormalizedLog | 결과 계약 |
|---|---|---|
| `event_id` | `event_id` | `masked-logs.event_id`, `security-events.source_event_id` |
| `request_id` | `request_id` | `request_id` (허용 문자만 남기고 64자로 자름) |
| `timestamp` | `timestamp` | `occurred_at` (UTC `Z`) |
| `environment` | `environment` | `environment` (별칭을 계약 enum으로 맞춤) |
| `service` | `service` | `source_service` |
| `event_type` | `source_type` | `source_type` |
| `feature`+`event_type` | `event_name` | `security-events.event_name` |
| `input.question` | `body` | `masked_message`, `masked_excerpt` |
| 그 밖의 필드 | `attributes` | `safe_metadata.attributes` |

`safe_metadata`에는 마스킹된 속성과 함께 `severity`, `risk_level`, `risk_score`,
`detected_rules`, `source_kind`를 넣어 Grafana에서 바로 쓸 수 있게 한다.
`body_hash`와 `evidence_fingerprint`는 C 계약에 맞춰 접두사 없는 hex 64자리로 보낸다.

## 전달 보장

1. 원본 메시지를 처리한다.
2. 결과를 발행하고 전달 보고를 모두 확인한다.
3. 그다음에 원본 offset을 commit한다.

발행이 끝내 실패하면 commit하지 않고 프로세스를 종료한다. systemd가 다시 시작하면 마지막
commit 위치부터 다시 읽는다. 즉 at-least-once이며 같은 입력은 항상 같은 `event_id`와
`detection_id`를 만들므로 C가 중복 없이 저장할 수 있다.

실패한 메시지는 원문 없이 `source_topic`, `partition`, `offset`, `payload_hash`만 담아
`myohan.dead-letter`로 보낸다. 계약은 `contracts/v1/kafka-dead-letter.schema.json`이다.

발행 직전에 `adapter/safety.py`가 C의 sink와 같은 패턴으로 마스킹 누락을 한 번 더 확인한다.
걸리면 결과 topic 대신 `UNSAFE_OUTPUT` dead-letter로 보낸다.

## systemd 서비스 설치

서버에서 아래 한 줄이면 의존성 확인, 가명화 키 생성, 마스킹 자체 점검, 서비스 등록까지
끝난다. `luck-was` 저장소 루트에서 실행한다.

```bash
bash security-monitoring/detector/scripts/install-adapter.sh
```

스크립트가 하는 일은 다음과 같다.

1. `.venv`에 `confluent-kafka`가 없으면 `requirements.txt`로 설치하고, NER 또는 PII 문맥
   분류가 활성화되어 있으면 `requirements-ner.txt`의 Transformers/PyTorch도 설치한다.
2. `.env`에 `MASKING_PSEUDONYM_KEY`가 없으면 새로 만들어 넣고 mode 0600으로 바꾼다.
   **이미 키가 있으면 절대 덮어쓰지 않는다.**
3. Kafka에 연결하기 전에 `--dry-run`으로 IP 마스킹이 동작하는지 확인한다.
4. `/etc/systemd/system/luck-masking-adapter.service`를 설치하고 `enable --now` 한다.
5. 서비스가 active로 올라오지 않으면 journal 로그를 출력하고 1을 반환한다.

`sudo`가 필요한 단계는 unit 설치와 `systemctl`뿐이다. 실행 사용자와 저장소 경로는
스크립트가 실행 환경에서 그대로 읽으므로 서버마다 고칠 값이 없다.

## 서비스 관리

```bash
sudo systemctl status luck-masking-adapter --no-pager
sudo systemctl restart luck-masking-adapter
sudo systemctl stop luck-masking-adapter
sudo journalctl -u luck-masking-adapter -f
```

설정을 바꾸면(`.env` 수정, `git pull`) 재시작해야 반영된다. 재시작은 처리 중인 메시지를
마친 뒤 종료하므로 commit되지 않은 결과가 남지 않는다.

```bash
cd ~/luck-was && git pull --ff-only && sudo systemctl restart luck-masking-adapter
```

unit 파일 자체를 바꾼 경우에는 설치 스크립트를 다시 실행하거나
`sudo systemctl daemon-reload`를 먼저 실행한다.

## 남은 작업

- 실제 broker에서 재연결·리밸런스·중복 처리 확인
- Nginx access 로그 전용 마스킹 정책 파일 (필드는 확인했으나 정책은 WAS 것을 공유한다)
- lag·처리량·실패 건수 지표 노출
- dead-letter 선택 replay 도구
