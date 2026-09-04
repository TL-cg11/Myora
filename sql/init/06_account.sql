-- 회원 계정과 생년월일 프로필
-- 적용: sudo mysql -uroot luck_db < sql/init/06_account.sql
--
-- 스키마만 미리 만들어 둔다. 아직 로그인 기능이 없어 이 테이블에 행이 쌓이지
-- 않는다. 로그인 페이지를 만들 때 맞춰볼 실제 테이블이 있는 편이 낫고, 빈
-- 테이블이라 컬럼이 안 맞으면 ALTER TABLE 로 바로 고치면 된다.
--
-- 07_reading.sql 의 reading.user_id 가 app_user 를 FK 로 참조하므로 이 파일이
-- 먼저 적용되어야 한다(파일명 번호 순서가 그 순서다).

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
