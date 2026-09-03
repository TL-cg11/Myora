-- 회원 계정과 생년월일 프로필
-- 적용: sudo mysql -uroot luck_db < sql/design/05_account.sql
--
-- 이 파일은 sql/init/ 이 아니라 sql/design/ 에 있다. install.sh 는 sql/init/*.sql 만
-- 적용하므로 이 폴더의 SQL 은 자동으로 실행되지 않는다. 사주·관상 저장을 실제로
-- 하기로 정한 뒤 손으로 적용한다. 배경은 docs/schema-design.html 참고.
--
-- 로그인이 아직 없어도 만들어 둔다. reading.user_id 가 이 테이블을 참조하므로
-- 06_reading.sql 보다 먼저 적용되어야 한다(파일명 순서가 그 순서다).

CREATE TABLE IF NOT EXISTS app_user (
    id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    email         VARCHAR(190) NOT NULL COMMENT 'utf8mb4 인덱스 키 길이 때문에 190자',
    password_hash VARCHAR(255) NULL COMMENT '소셜 로그인만 쓰면 NULL',
    nickname      VARCHAR(40)  NOT NULL,
    status        ENUM('active','dormant','withdrawn') NOT NULL DEFAULT 'active',
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_app_user_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS birth_profile (
    id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id    BIGINT UNSIGNED NOT NULL,
    label      VARCHAR(40) NOT NULL COMMENT '내 사주, 엄마 ...',
    birth_date DATE NOT NULL,
    birth_time TIME NULL COMMENT 'NULL 은 모른다는 뜻. 정오로 대체한 값이 아니다',
    calendar   ENUM('solar','lunar','lunar_leap') NOT NULL DEFAULT 'solar',
    gender     ENUM('female','male','unknown') NOT NULL DEFAULT 'unknown',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY ix_birth_profile_user (user_id),
    CONSTRAINT fk_birth_profile_user FOREIGN KEY (user_id)
        REFERENCES app_user (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
