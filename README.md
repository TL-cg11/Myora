# luck-was

Ubuntu Server 24.04에서 동작하는 FastAPI 테스트 애플리케이션입니다. Nginx의 요청을 받고 별도 MariaDB 서버의 `health_check` 테이블을 조회합니다.

## 구성

- FastAPI 서버: `100.66.77.55:8000`
- MariaDB 서버: `100.104.124.29:3306`
- `GET /`: 3개 서비스의 상태를 보여주는 테스트 대시보드
- `GET /api/health`: WAS 자체 상태(liveness)
- `GET /health`: MariaDB 스키마와 데이터까지 확인(readiness)

## 설치 및 갱신

```bash
git clone https://github.com/TL-cg11/luck-was.git ~/luck-was
cd ~/luck-was
cp .env.example .env
bash scripts/install.sh
```

이미 clone한 서버에서는 다음과 같이 갱신합니다.

```bash
cd ~/luck-was
git pull --ff-only
bash scripts/install.sh
```

`scripts/install.sh`는 Python 가상환경과 의존성을 구성하고 `luck-was.service`를 설치해 부팅 시 자동 시작되게 합니다.

## 확인

```bash
curl http://127.0.0.1:8000/api/health
curl http://127.0.0.1:8000/health
sudo systemctl status luck-was --no-pager
```

`.env.example`의 계정은 테스트 전용입니다. 운영 환경에서는 `.env`에 별도 비밀번호를 설정하고 MariaDB 사용자 비밀번호도 동일하게 변경하세요.

## 프론트엔드

React + Vite로 만든 묘한운세 랜딩 페이지입니다.

### 실행

```bash
npm install
npm run dev
```

### 페이지

- `/` 메인
- `/saju` 사주
- `/tarot` 타로
- `/face` 관상
- `/login`, `/signup` 로그인·회원가입
- `/mypage` 로그인한 사용자별 사주·타로·관상 기록

## 회원 인증과 사용자별 기록

회원가입은 아이디, 이름, 이메일, 비밀번호를 받습니다. 비밀번호는 PBKDF2-SHA256으로
해시하고, 로그인 토큰도 원문 대신 SHA-256 해시만 `auth_session`에 저장합니다.
로그인된 사주·타로·관상 요청은 토큰에서 확인한 `app_user.id`를 소유자로 사용하므로
클라이언트가 다른 사용자 ID를 지정할 수 없습니다. 가입 또는 로그인할 때 현재 브라우저의
기존 비회원 UUID 기록은 해당 계정으로 한 번 귀속됩니다.

기존 MariaDB에는 WAS 배포 전에 다음 마이그레이션을 적용합니다.

```bash
sudo mysql -uroot luck_db < sql/migrate/2026-09-09_user_auth.sql
sudo mysql -uroot luck_db < sql/migrate/2026-09-09_auth_lockout.sql
```

기본 인증 정책은 연속 5회 로그인 실패 시 60분 계정 잠금, 로그인 세션 1시간 만료입니다.
`AUTH_MAX_FAILED_ATTEMPTS`, `AUTH_LOCKOUT_MINUTES`, `AUTH_SESSION_HOURS` 환경변수로
운영 정책을 조정할 수 있습니다. 계정 잠금은 WAS가 처리하고, IP 단위 속도 제한·차단은
Nginx 또는 Fail2ban/방화벽 계층에서 별도로 적용합니다.

## 사주 한자 뜻 사전

### 결과에 맞춘 상담형 풀이

결과 화면은 일주별 종합 설명과 강점·주의점·일·관계·균형 조언을 먼저 표시합니다.
기존 한자 사전은 **풀이의 바탕이 된 한자와 용어 보기**에서 펼칠 수 있습니다.
`saju_narrative_rule`에 일주 프로필 60개와 용신 균형 5개, 정격별 업무 조언 11개,
신살 보완 조언 29개(총 105개)를 추가했습니다. 기존 사전 142개는 유지합니다.

프로필에는 `code`, `keywords`, `strengths`, `weaknesses`, `career`, `relationship`과
각 항목을 자연스럽게 풀어 쓴 문장이 들어 있습니다. 원본은 `app/data/saju_narratives.json`입니다.
예를 들어 병오 프로필은 활동적·추진력·표현력·승부욕, 실행력·리더십, 성급함·과열을
중심으로 읽습니다. 다른 일주는 해당 천간과 지지의 프로필을 사용합니다.
일주가 같아도 실제 계산된 정격과 용신이 다르면 일·균형 조언이 달라지고,
검출된 신살 중 일간·일지에 해당하는 항목을 우선해 최대 두 가지 조언을 덧붙입니다.
같은 입력은 같은 결과를 내며, 외부 AI 호출 없이 매 요청 DB에서 문구를 읽습니다.

운영 적용 시 기존 12~13번에 이어 **14번 테이블·15번 데이터 SQL을 먼저 적용한 뒤 WAS를 갱신**합니다.
기존 테이블과 저장된 사주는 수정하지 않습니다. 새 SQL도 재실행 시 편집한 문구를 보존합니다.
로컬은 `scripts/run-local.ps1`을 재실행하면 새 테이블과 초기 데이터가 추가됩니다.
`scripts/export-saju-dictionary.py`는 사전과 상담 초기 SQL을 모두 생성합니다.
추가 질문 채팅에는 화면에 표시한 상담 내용과 원국을 전달하며, 중복 사전 데이터는 제외해
기존 8,000자 제한을 지킵니다. 시간 미상은 기존 정오 계산 기준을 사용했음을 화면에 안내합니다.

### 한자 사전 동작

사주 계산 결과의 한자를 키로 `saju_term`에서 한글 이름과 뜻을 조회해 표시합니다.
요청 처리 중 코드나 라이브러리에서 해석 문구를 생성하지 않으며, 매 요청 DB를 조회합니다.
DB에서 `name_ko` 또는 `meaning_ko`를 수정하면 다음 사주 결과에 바로 반영됩니다.
기존 사주 계산·원국 저장·POST 응답 필드와 채팅 연결은 유지하고,
`reading.interpretation`에 DB에서 조회한 뜻만 추가했습니다.

사전은 현재 `korean-saju 0.3.0` 계산 결과에 필요한 **142개 항목**을 담습니다.
천간 10개, 지지 12개, 60갑자 60개, 오행 5개, 정격 11개, 신살 29개,
용신 도출 방식 7개, 기본 용어 8개입니다. 모든 생년월일 조합을 미리 저장하는 방식이 아니라,
계산 결과를 구성하는 글자와 용어의 뜻을 저장합니다.

`app/data/saju_terms.json`은 초기 데이터 원본입니다. 천간·지지·신살은 설치된 엔진의
한국어 설명을 기준으로, 나머지는 한글 용어 설명으로 구성했습니다.
실행 중 응답의 이름과 뜻은 이 파일이 아닌 DB에서 읽습니다.
분류와 한자를 함께 조회하므로 같은 한글 음을 가진 `辛`과 `申`도 구별됩니다.
필요한 항목이 DB에 없으면 503 오류를 반환하고 결과 저장을 취소합니다.

### MariaDB 초기 데이터 적용

기존 사주 테이블(06~08번 SQL)이 있는 DB에서, `luck-mariadb` 디렉터리 기준:

```bash
sudo mysql -uroot luck_db < sql/init/12_saju_dictionary.sql
sudo mysql -uroot luck_db < sql/init/13_saju_dictionary_seed.sql
```

새 DB는 기존 설치 스크립트가 `sql/init/*.sql`을 순서대로 적용합니다.
기존 테이블은 변경하지 않고 사전 테이블만 추가합니다.
초기 데이터를 재적용해도 관리자가 수정한 뜻은 덮어쓰지 않고 누락 행만 추가합니다.
수정 예시:

```sql
SELECT category, hanja, name_ko, meaning_ko FROM saju_term ORDER BY category, id;
UPDATE saju_term SET meaning_ko = '큰 나무를 뜻하며 성장과 시작을 상징합니다.'
WHERE category = 'stem' AND hanja = '甲';
```

JSON 원본을 수정한 경우 `.venv/Scripts/python scripts/export-saju-dictionary.py`로
MariaDB 초기 SQL을 다시 생성합니다. 기존 DB 문구 수정은 위 UPDATE처럼 별도로 적용합니다.

### Windows 로컬 테스트

`luck-was`의 기존 가상환경과 npm 의존성이 설치되어 있는 상태에서:

```powershell
npm run build
powershell -ExecutionPolicy Bypass -File scripts/run-local.ps1
```

[사주 페이지](http://127.0.0.1:8000/saju)에서 테스트합니다. 로컬 DB는
`.local/saju-dictionary.db`이며, 처음 실행할 때 사전 142개 행이 실제로 저장됩니다.
재실행해도 수정한 사전 문구는 유지됩니다. `-Port 8001`로 포트를 바꿀 수 있습니다.
로컬 SQLite에는 사주 관련 테이블만 생성하므로 타로·관상 DB 기능 전체 테스트는
기존 MariaDB 환경을 사용하세요. 기존 `.env` 및 기본 MariaDB 연결은 그대로입니다.

이전에 추가했던 결과 스냅샷 컬럼과 최근 기록 UI/API는 제거했습니다.
이전 로컬 `.local/luck.db`는 데이터 보호를 위해 그대로 보관하며 새 구현에서는 사용하지 않습니다.
한글 뜻 조회에는 AI 키가 필요 없고 기존 추가 질문 채팅에는 사주용 API 키가 필요합니다.

검증: `.venv/Scripts/python -m unittest discover -s app/tests`, `npm test`, `npm run build`.
DB 문구 수정 반영, 초기화 재실행 보존, 사전 전체 항목, 누락 시 롤백, 기존 응답·저장을 확인합니다.

## 보안 이벤트 조회 API

`/api/security/events`는 `security_monitoring` DB를 조회하며 `/api/security` 전용
Bearer 인증과 VIEWER 이상의 `event:read` 권한이 필요합니다. 인증 설정과 token 생성은
`docs/security-api-auth.md`를 참고합니다.

```bash
curl -H "Authorization: Bearer $SECURITY_API_TOKEN" \
  'http://127.0.0.1:8000/api/security/events?risk_level=HIGH&status=OPEN&page=1&page_size=50'
curl -H "Authorization: Bearer $SECURITY_API_TOKEN" \
  http://127.0.0.1:8000/api/security/events/evt-example
```

목록은 `start_time`, `end_time`, `risk_level`, `status`, `source` 필터와
`sort_by`(`occurred_at`, `detected_at`, `risk_score`, `created_at`), `sort_order`,
`page`, `page_size`를 지원합니다. 상세 응답에는 detections와 시간순 actions가 포함됩니다.

EDITOR 이상은 다음 endpoint로 이벤트를 조치합니다. 이벤트 행 잠금 후 이벤트 변경과
`security_event_action` INSERT를 같은 transaction으로 commit하며 actor ID는 인증 정보만
사용합니다.

```text
PATCH /api/security/events/{event_id}/status
PATCH /api/security/events/{event_id}/assignee
POST  /api/security/events/{event_id}/false-positive
POST  /api/security/events/{event_id}/reopen
```

오탐과 재오픈은 전용 endpoint만 허용해 각각 `MARKED_FALSE_POSITIVE`, `REOPENED` action이
남도록 보장합니다. 감사 action을 수정하거나 삭제하는 API는 제공하지 않습니다.

`GET /api/security/audit-logs`는 VIEWER 이상에게 append-only 조치 이력을 제공합니다.
`start_time`, `end_time`, `event_id`, `actor_id`, `action_type`, `sort_order`, `page`,
`page_size`로 조회할 수 있으며 내부 DB key는 응답하지 않습니다. 같은 경로에 대한
POST·PUT·PATCH·DELETE는 405로 거부되고 DB API 계정에도 action UPDATE·DELETE 권한이 없습니다.

## 타로 기능

카드 뽑기와 해석은 서버가 정합니다. 화면에서 카드를 고르더라도 어떤 카드가 나왔는지는
서버가 결정해야 결과를 조작할 수 없습니다. 리딩 조회는 `guest_key` 가 일치할 때만 됩니다.

스키마와 기준 데이터는 `luck-mariadb` 의 `sql/init/02~04` 에 있습니다.

### 결과 채팅 (DeepSeek)

`.env` 에 키를 넣으면 켜지고, 비워두면 카드에서 바로 끌어오는 규칙 기반 답변으로
동작합니다. 호출이 실패해도 같은 답변으로 되돌아가므로 채팅이 끊기지는 않습니다.

```
DEEPSEEK_TAROT_API_KEY=sk-...
DEEPSEEK_TAROT_MODEL=deepseek-v4-flash
LLM_TIMEOUT=20
```

응답의 `source` 가 이번 답변을 무엇으로 만들었는지 알려줍니다(`llm` / `rule`).
화면에서는 채팅 패널 오른쪽 위 배지로 보입니다.

`DEEPSEEK_BASE_URL` 은 관상 채팅과 공용입니다.

리딩 요약은 LLM 을 쓰지 않습니다. 카드를 뽑는 순간에 외부 API 를 기다리게 하지
않으려는 것이고, 바꾸려면 `app/routers/tarot.py` 의 주석을 보세요.


## Kafka 보안 로그

WAS는 `api_request`, `ai_request` JSON 로그를 `myohan.was.app`으로 직접 전송합니다.
Nginx와 WAS 로그는 서로 다른 Consumer 프로세스가 처리합니다.

실행 방법, topic/group, offset 정책, PII 처리 경계, 서버 테스트와 systemd 등록은
[Kafka 로깅과 Consumer 운영 가이드](consumer/README.md)를 참고하세요. JSON 필드 계약과
마스킹 정책은 [WAS 로그 스키마](schemas/README.md)를 참고하세요.
