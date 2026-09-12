# 테스트 데이터 해설

JSON과 JSONL에는 일반 코드처럼 `#` 또는 `//` 주석을 달 수 없다.
파서가 읽는 테스트 입력과 정답을 보존하기 위해 이 문서에서 설명한다.
실제 개인정보나 사용 중인 키로 합성 예시를 교체하지 않는다.

## cases.json

| 항목 | 의미 |
|---|---|
| dataset_version | 테스트 데이터셋 버전 |
| description | 합성 데이터임을 설명하는 안내 |
| cases | 43개 테스트 사례 배열 |
| cases[].name | 테스트 실패 시 구분할 사례 이름 |
| cases[].input | A가 보내는 NormalizedLog 형식의 입력 |
| cases[].expected.rules | 탐지되어야 하는 규칙 목록. 빈 배열은 정상 사례 |
| cases[].expected.masked_body | 최종 본문 정답. 공백과 개행까지 비교 |
| cases[].expected.masked_attributes | 있는 경우에만 추가 속성의 마스킹 결과 비교 |
| cases[].expected.risk_level / risk_score | 있는 경우에만 사건 위험등급과 점수 비교 |

normal은 정상 입력, phone/email/rrn/birth는 개인정보 패턴,
jwt/bearer/basic/password/secret/db/private는 비밀정보 패턴을 확인한다.
combined는 여러 정보가 동시에 있는 경우, already-masked는 재처리,
structured/nested/escaped/numeric/key는 구조화 데이터와 경계 사례다.
rrn-invalid-date처럼 형식상 숫자여도 탐지하면 안 되는 사례도 포함한다.

## raw-logs.jsonl

cases.json의 input만 같은 순서로 한 줄에 한 건씩 담은 파일이다.
CLI에서 사용하며 정답이나 설명 필드는 넣지 않는다. 새 사례 추가 시 두 파일을
함께 갱신해야 실행 시연과 단위 테스트가 같은 입력을 사용한다.

## 생성 결과 읽기

| 파일(탐지기 폴더 기준) | 해설 |
|---|---|
| output/demo/masked-logs.jsonl | 각 성공 입력의 마스킹 본문·속성. 정상 로그도 포함 |
| output/demo/security-events.jsonl | 탐지가 있는 입력만 기록. detections는 규칙별로 묶음 |
| output/demo/dead-letter.jsonl | 실패 코드·단계·행 번호. 성공 시 빈 파일인 것이 정상 |
| artifacts/evaluation.json | 규칙별 tp/fp/fn 및 precision/recall/f1, 정답 비교 통과 수 |

평가 보고서의 micro는 전체 규칙 집계, rules는 규칙별 집계다.
failed_case_numbers는 cases 배열에서 1부터 시작하는 실패 위치다.
현재 생성된 결과는 43건 처리, 32건 사건, 실패 0건이며 합성 회귀 데이터 결과다.
생성 파일에 설명 필드를 직접 추가하면 계약 또는 재실행 결과가 달라지므로 수정하지 않는다.
