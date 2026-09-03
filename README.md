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

`sql/init/`의 파일은 파일명 순서대로 전부 적용됩니다. `luck_user`에게는 DDL 권한이 없으므로 스키마 변경은 반드시 root로 적용해야 합니다.

| 파일 | 내용 |
| --- | --- |
| `01_init.sql` | `health_check` (상태 확인용) |
| `02_tarot.sql` | 타로 테이블 6개 |
| `03_tarot_seed.sql` | 스프레드 3종 + 메이저 아르카나 22장 |
| `04_tarot_meaning_seed.sql` | 주제별 해석 176행 (22장 x 4주제 x 2방향) |

### 테이블

- `tarot_card` — 카드 카탈로그. `code`(`major-18` 형태)가 고정 식별자이고 정/역방향 해석을 각각 가집니다.
- `tarot_card_meaning` — 연애·직업·금전·건강 주제별 해석. 행이 없으면 `tarot_card`의 일반 해석을 사용합니다. 메이저 22장은 `04_tarot_meaning_seed.sql`이 네 주제를 모두 채웁니다.
- `tarot_spread` / `tarot_spread_position` — 스프레드 정의와 각 자리(과거·현재·미래 등) 라벨.
- `tarot_reading` — 리딩 1회. 질문, 주제, 결과 요약, 해석 출처(`rule`/`llm`)를 담습니다.
- `tarot_reading_card` — 리딩에서 뽑힌 카드. 자리별 1장, 같은 카드 중복 불가.
- `tarot_chat_message` — 결과 화면의 AI 채팅 기록. 리딩 삭제 시 함께 삭제됩니다.

### 회원 연결

`tarot_reading.user_id`는 `users` 테이블이 아직 없어 FK 없이 nullable로 두었습니다. 비회원은 클라이언트가 보관하는 UUID를 `guest_key`에 넣으며, 둘 중 하나는 반드시 있어야 합니다(`ck_tarot_reading_owner`). 인증 담당이 `users`를 만든 뒤 FK를 추가하면 됩니다.

```sql
ALTER TABLE tarot_reading
  ADD CONSTRAINT fk_tarot_reading_user FOREIGN KEY (user_id) REFERENCES users (id);
```

### 마이너 아르카나

`tarot_card`는 `arcana`/`suit`/`number`로 78장을 모두 표현할 수 있습니다(마이너는 11 페이지·12 나이트·13 퀸·14 킹). 56장 추가는 `03_tarot_seed.sql`과 같은 형식의 INSERT만 있으면 되고 스키마 변경은 필요 없습니다. 주제별 해석도 `04_tarot_meaning_seed.sql`에 같은 형식으로 이어 붙이면 됩니다.
