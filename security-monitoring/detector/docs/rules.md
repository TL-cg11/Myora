# 탐지·마스킹 정책 1 / detector 1.0.0

<!-- 문서 역할: pii.py, secrets.py, engine.py, risk.py의 정책을 사람이 검토하는 기준표. -->

| rule_id | 검사 대상 | 점수 | 마스킹 |
|---|---|---:|---|
| EMAIL_ADDRESS | 이메일 패턴, email 필드 | 30 | 본문은 첫 글자+`***`+도메인, 구조화 필드는 전체 |
| PHONE_NUMBER | 한국 휴대전화 패턴, phone 필드 | 50 | 본문은 `010-****-5678`, 구조화 필드는 전체 |
| BIRTH_DATE | 생년월일 키워드 뒤 날짜, birth_date/dob 필드 | 50 | 전체 |
| PERSON_NAME | name/customer_name/full_name/이름/성명 필드 | 50 | 전체 |
| KR_RRN | 날짜가 유효한 13자리 주민번호 후보, rrn 필드 | 85 | 전체 |
| JWT | eyJ로 시작하는 3구간 JWT 후보 | 85 | 전체 |
| AUTHORIZATION | Bearer/Basic, authorization/cookie 필드 | 90 | 전체 |
| PASSWORD | password/passwd/pwd 할당, db_password 등 필드 | 90 | 전체 |
| API_KEY | api_key/secret/token 할당, 알려진 키 접두사 | 90 | 전체 |
| DB_CONNECTION_STRING | MySQL/MariaDB/PostgreSQL/MongoDB URL | 95 | 전체 URL |
| PRIVATE_KEY | PEM private key, private_key 필드 | 100 | 전체. END 누락 시 끝까지 |

0~49 LOW, 50~74 MEDIUM, 75~94 HIGH, 95~100 CRITICAL.
탐지가 없으면 LOW/0이며 SecurityEvent를 생성하지 않는다.
이름과 생년월일이 같은 로그에서 탐지되면 사건 점수를 최소 75로 올린다.
그 외에는 가장 높은 규칙 점수를 사용한다. confidence는 규칙 신뢰도 초기값이며
통계적으로 보정된 확률이 아니다. 자유 문장의 이름/주소 NER는 구현 범위에서 제외했다.

주민번호 후보는 날짜 검증만 하며 체크섬 불일치를 이유로 마스킹을 건너뛰지 않는다.
테스트 주민번호 모양 값은 합성 예시이며 실제 발급 여부를 확인하거나 인증에 사용하지 않는다.
전화/이메일 부분 마스킹은 완전한 익명화가 아니다. 공개 화면에 표시할 데이터로 간주하지 않는다.

겹치는 탐지 구간은 합집합 전체를 `[REDACTED]`로 바꾼다. 높은 위험 규칙만 선택해서
바깥쪽 민감 문자가 남는 것을 방지한다. API 키 접두사·정규식·점수 변경 시 VERSION과
관련 fixture/평가 결과를 같이 변경한다.

HIGH 이상 사건은 담당자가 서비스/규칙/시각/요청 ID로 확인하고, 비밀정보 노출이면
해당 서비스 소유자에게 키 폐기·교체 판단을 요청한다. 원문을 댓글/알림에 붙이지 않는다.
MEDIUM/LOW는 오탐 여부와 반복 발생을 확인한다. B 엔진이 키를 자동 폐기하거나
계정/요청을 차단하지는 않는다. 알림과 상태 변경 감사 이력은 C 범위다.
