# luck-mariadb

Ubuntu Server 24.04에서 동작하는 MariaDB 테스트 서버 구성입니다. FastAPI 서버 한 대에만 애플리케이션 계정 로그인을 허용하고 상태 확인용 테이블을 초기화합니다.

## 구성

- MariaDB 서버: `100.104.124.29:3306`
- 허용된 WAS 주소: `100.66.77.55`
- 데이터베이스: `luck_db`
- 애플리케이션 사용자: `luck_user`
- 초기 테이블: `health_check`

## 설치 및 갱신

```bash
git clone https://github.com/TL-cg11/luck-mariadb.git ~/luck-mariadb
cd ~/luck-mariadb
bash scripts/install.sh
```

이미 clone한 서버에서는 다음과 같이 갱신합니다.

```bash
cd ~/luck-mariadb
git pull --ff-only
bash scripts/install.sh
```

필요하면 설치 시 값을 덮어쓸 수 있습니다.

```bash
DB_PASSWORD='새-비밀번호' WAS_HOST='WAS-IP' bash scripts/install.sh
```

## 확인

```bash
bash scripts/test.sh
sudo ss -ltnp | grep 3306
sudo systemctl status mariadb --no-pager
```

`mariadb.cnf`는 원격 WAS 접속을 위해 TCP 리스닝을 활성화합니다. 데이터베이스 계정은 지정한 WAS 주소와 로컬호스트에서만 인증됩니다. 인터넷에 직접 포트를 공개하지 말고 Tailscale 또는 방화벽으로 접근 범위를 제한하세요.

## 타로 스키마

전체 테이블 명세는 [`docs/schema.md`](docs/schema.md), 설계 배경은 [`docs/schema-design.html`](docs/schema-design.html)에 있습니다.

`sql/init/`의 파일은 파일명 순서대로 전부 적용됩니다. `luck_user`에게는 DDL 권한이 없으므로 스키마 변경은 반드시 root로 적용해야 합니다.

| 파일 | 내용 |
| --- | --- |
| `01_init.sql` | `health_check` (상태 확인용) |
| `02_tarot.sql` | 타로 테이블 6개 |
| `03_tarot_seed.sql` | 스프레드 3종 + 메이저 아르카나 22장 |
| `04_tarot_meaning_seed.sql` | 주제별 해석 176행 (22장 x 4주제 x 2방향) |
| `05_chat_source.sql` | `tarot_chat_message.source` — 답변이 규칙 기반인지 LLM인지 |
| `06_account.sql` | `app_user`, `auth_session`, `birth_profile` — 회원 계정·로그인 세션·생년월일 프로필 |
| `07_reading.sql` | `reading`, `chat_message` — 사주/관상/타로가 공유할 리딩 뼈대 (앱은 아직 안 씀) |
| `08_saju.sql` | `saju_chart`, `saju_reading` — 사주 계산 결과 저장용 (앱은 아직 안 씀) |
| `09_face.sql` | `face_shape`, `face_reading` — 관상 인상 유형과 리딩 상세 (앱은 아직 안 씀) |
| `10_face_seed.sql` | 관상 인상 유형 5종 |
| `11_face_interpretation.sql` | 비율·눈매·입매·조화·분위기별 관상 세부 해석 20종 |
| `12_saju_dictionary.sql` | `saju_term` — 한자·사주 용어의 한글 이름과 뜻 사전 |
| `13_saju_dictionary_seed.sql` | 천간·지지·60갑자·오행·정격·신살·용신 방식·기본 용어 142개 |
| `14_saju_narrative.sql` | `saju_narrative_rule` — 구조화된 상담 프로필과 보완 조언 |
| `15_saju_narrative_seed.sql` | 일주 프로필 60개 + 용신·정격·신살 조언 45개 |

상담형 화면을 배포할 때는 14번과 15번 SQL을 WAS 갱신 전에 적용합니다.
기존 사전·리딩은 유지하며 새 테이블만 추가합니다. `data` JSON에 일주별 키워드,
강점, 약점, 일, 관계와 설명 문장이 들어 있고 WAS가 실제 계산값에 따라 조합합니다.
문구 수정은 `saju_narrative_rule.data`에서 하며 초기 SQL 재적용은 수정한 값을 덮어쓰지 않습니다.
초기 원본은 `luck-was/app/data/saju_narratives.json`입니다.

### 사주 사전 적용

기존 사주 테이블이 있는 DB는 관리자 계정으로 12번과 13번 SQL을 순서대로 적용합니다.
기존 테이블을 변경하지 않습니다. WAS는 계산 결과의 `(category, hanja)`로 사전을 조회해
한글 이름과 뜻을 표시합니다. `meaning_ko`를 UPDATE하면 다음 계산 요청부터 반영됩니다.
13번 SQL을 재실행하면 누락 항목만 추가하고 이미 편집한 뜻은 보존합니다.
초기 데이터 원본은 `luck-was/app/data/saju_terms.json`이고
`luck-was/scripts/export-saju-dictionary.py`로 이 저장소의 13번 SQL을 생성합니다.

### 테이블

- `tarot_card` — 카드 카탈로그. `code`(`major-18` 형태)가 고정 식별자이고 정/역방향 해석을 각각 가집니다.
- `tarot_card_meaning` — 연애·직업·금전·건강 주제별 해석. 행이 없으면 `tarot_card`의 일반 해석을 사용합니다. 메이저 22장은 `04_tarot_meaning_seed.sql`이 네 주제를 모두 채웁니다.
- `tarot_spread` / `tarot_spread_position` — 스프레드 정의와 각 자리(과거·현재·미래 등) 라벨.
- `tarot_reading` — 리딩 1회. 질문, 주제, 결과 요약, 해석 출처(`rule`/`llm`)를 담습니다.
- `tarot_reading_card` — 리딩에서 뽑힌 카드. 자리별 1장, 같은 카드 중복 불가.
- `tarot_chat_message` — 결과 화면의 AI 채팅 기록. 리딩 삭제 시 함께 삭제됩니다.

### 회원 연결

`app_user`와 `auth_session`이 회원 및 로그인 세션을 저장합니다. 비밀번호는 PBKDF2 해시만, 세션은 Bearer 토큰의 SHA-256 해시만 저장합니다. 비회원은 클라이언트가 보관하는 UUID를 `guest_key`에 넣으며 로그인·가입 시 해당 브라우저의 기존 리딩을 회원에게 귀속시킵니다. 기존 DB는 아래 마이그레이션을 한 번 적용합니다.

```sql
sudo mysql -uroot luck_db < sql/migrate/2026-09-09_user_auth.sql
sudo mysql -uroot luck_db < sql/migrate/2026-09-09_auth_lockout.sql
```

### 사주 / 관상 / 리딩 공용 스키마

관상 기능은 `reading`, `face_reading`, `face_shape`, `face_interpretation`을 사용합니다. 사진과 랜드마크 원본은 저장하지 않고 측정 비율과 선택한 분위기만 저장하며, 서버가 기준 데이터에서 해당 문구를 골라 결과를 만듭니다. 사주는 현재 결과를 그 자리에서 계산해 응답으로 돌려주며 아직 공용 리딩 테이블에 저장하지 않습니다.

미리 만들어 둔 이유는 두 가지입니다. 로그인이나 사주/관상 저장 기능을 만들 때 맞춰볼 실제 테이블이 있는 편이 낫고, 빈 테이블이라 나중에 컬럼이 안 맞아도 `ALTER TABLE`로 고치는 비용이 거의 없습니다. 기존 타로 데이터를 이 구조로 옮기는 작업은 `sql/migrate/`에 별도로 있고, 저장 기능이 실제로 만들어질 때 판단합니다. 설계 배경과 테이블별 근거는 `docs/schema-design.html` 참고하세요.

### 마이너 아르카나

`tarot_card`는 `arcana`/`suit`/`number`로 78장을 모두 표현할 수 있습니다(마이너는 11 페이지·12 나이트·13 퀸·14 킹). 56장 추가는 `03_tarot_seed.sql`과 같은 형식의 INSERT만 있으면 되고 스키마 변경은 필요 없습니다. 주제별 해석도 `04_tarot_meaning_seed.sql`에 같은 형식으로 이어 붙이면 됩니다.
