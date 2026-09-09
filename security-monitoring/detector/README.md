# B 담당: Kafka 독립형 로그 보안 탐지기

<!-- 문서 역할: 새 팀원이 실행 방법과 각 구현 파일의 책임을 찾는 시작점. -->

코드에는 함수·모델·핵심 분기의 한국어 주석이 있다. JSON 스키마는 `$comment`로
필드를 설명하며, 테스트 데이터와 생성 파일의 설명은 [fixture 해설](tests/fixtures/README.md)을 참고한다.
현재 업무의 완료·부분 완료·미구현 상태와 항목별 코드는
[B 담당 업무 상세 문서](docs/tasks/README.md)에서 확인한다.

Python 3.11 이상에서 표준 라이브러리만으로 실행한다. A의 정규화 로그를 입력받아
마스킹 로그, C용 보안 이벤트, 원문 없는 실패 결과를 생성한다.

Kafka 연결은 `adapter/` 패키지가 담당한다. `myohan.was.app`과 `myohan.nginx.access`를
읽어 같은 엔진으로 마스킹한 뒤 `myohan.masked-logs`, `myohan.security-events`,
`myohan.dead-letter`로 발행한다. 실행 방법과 필드 매핑은
[Kafka 마스킹 어댑터](adapter/README.md)를 참고한다. 어댑터만 `confluent-kafka`를 사용하며
엔진과 테스트는 여전히 표준 라이브러리만 쓴다.

## 실행

PowerShell에서 `luck-was` 폴더를 기준으로 다음처럼 이동한다.

```powershell
cd security-monitoring/detector
```

```powershell
python -m unittest discover -s tests -v
python -m app --input tests/fixtures/raw-logs.jsonl --output-dir output/demo
python -m app.evaluation --report artifacts/evaluation.json
```

출력 디렉터리와 평가 보고서는 새 경로를 지정해야 한다. 이미 존재하면 덮어쓰지 않는다.
다시 실행하려면 `output/demo-2`, `artifacts/evaluation-2.json`처럼 새 이름을 사용한다.

| 결과 | 설명 |
|---|---|
| `masked-logs.jsonl` | 성공한 입력마다 마스킹 로그 한 건 |
| `security-events.jsonl` | 탐지가 있는 입력마다 보안 이벤트 한 건 |
| `dead-letter.jsonl` | 처리 실패 코드·단계·입력 행 번호. 원문과 예외 문자열 없음 |
| `artifacts/evaluation.json` | 규칙별 TP/FP/FN, Precision/Recall/F1 및 마스킹 정답 비교 |

CLI 종료 코드는 0=전체 처리 성공, 1=일부 메시지 실패, 2=경로/설정/입출력 실패다.
실패한 행 이후에도 계속 처리한다. 빈 행은 잘못된 JSON으로 기록한다. UTF-8 JSONL을 사용한다.

## Python에서 호출

```python
from app import process_log

result = process_log(normalized_log_dict)
if result.failure is not None:
    failure = result.to_dict()["failure"]
else:
    masked_log = result.to_dict()["masked_log"]
    security_event = result.to_dict()["security_event"]  # 탐지가 없으면 None
```

`NormalizedLog` dataclass 입력도 지원하며 항상 다시 검증한다. 입력 객체는 변경하지 않는다.
모델과 처리 함수는 Kafka, FastAPI, DB에 의존하지 않는다.

## 파일 구성

| 경로 | 역할 |
|---|---|
| `app/models.py` | 입력 검증 및 결과 모델 |
| `app/engine.py` | 재귀 탐지·마스킹·이벤트 생성 |
| `app/rules/pii.py` | 전화번호·이메일·주민번호 후보·문맥 생년월일 |
| `app/rules/secrets.py` | JWT·인증 헤더·API 키·비밀번호·DB URL·개인키 |
| `app/masking.py` | 겹친 구간 병합 및 치환 |
| `app/risk.py` | 위험등급과 점수 계산 |
| `app/hashing.py` | body SHA-256, 선택적 HMAC, 재현 가능한 ID |
| `app/__main__.py` | JSONL 파일 실행기 |
| `app/evaluation.py` | 합성 데이터 평가 실행기 |
| `adapter/policy.py` | 마스킹 정책 로딩, 가명화, IP 마스킹 |
| `adapter/normalize.py` | WAS·Nginx 원본 로그 → 엔진 입력 변환 |
| `adapter/prompt_injection.py` | 자유 텍스트의 Prompt Injection 탐지 |
| `adapter/outbound.py` | 엔진 결과 → C 계약 메시지 변환 |
| `adapter/pipeline.py` | 메시지 한 건의 순수 처리 경로 |
| `adapter/kafka_runner.py` | 소비·발행·offset commit 순서 |
| `adapter/__main__.py` | Kafka 어댑터 실행기 |
| `contracts/v1/` | B 구현 기준 JSON Schema 초안 |
| `contracts/consumer/` | C가 소비하는 계약 사본 |
| `tests/fixtures/` | 정답을 포함한 43건 합성 fixture와 JSONL 입력 |
| `docs/contract.md` | A·C 전달 계약, DB 매핑, 오류·재처리 규칙 |
| `docs/rules.md` | 규칙과 점수·마스킹 정책 |

## 구현 범위와 한계

정규식과 구조화 필드 기반 MVP다. 합성 fixture 통과는 운영 로그의 완전한 비식별화를
보장하지 않는다. 별도 검증 데이터로 규칙별 미탐·오탐을 평가한 뒤 실제 연결한다.
자유 문장의 이름/주소, 카드/계좌번호, 내부 URL 단독 탐지, 임의 인코딩 비밀정보,
공급자 형식이 없는 무문맥 키, 시간 윈도우 행동 탐지는 후속 범위다.
구조화 `name`, `birth_date` 등은 지금도 마스킹한다. 원본에 비밀정보를 일부러 기록하지 않는다.

Kafka Consumer/Producer와 dead-letter 발행은 `adapter/`로 연결했다. DB 저장과 Grafana는
C가 결과 topic을 소비해 처리한다. 어댑터는 결과 발행을 확인한 뒤 offset을 commit하는
at-least-once 방식이므로 재시작 시 같은 메시지가 다시 올 수 있다. 같은 입력은 같은
`event_id`와 `detection_id`를 만들어 C가 중복 없이 저장한다.

오프라인 출력 세 파일은 분산 트랜잭션이 아니다. 쓰기 중 프로세스가 종료되면 일부만
생성될 수 있으므로 새 출력 디렉터리로 입력을 재실행하고 C에서 ID 중복을 처리한다.

이 모듈은 `luck-was/security-monitoring/detector`에 있으며 WAS 저장소에서 관리한다.
FastAPI와 별도 프로세스로 실행한다. 폴더 배치만으로 서버에 배포되거나 자동 실행되지는 않는다.
