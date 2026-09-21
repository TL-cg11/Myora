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
    username      VARCHAR(40)  NOT NULL,
    name          VARCHAR(40)  NOT NULL,
    email         VARCHAR(190) NOT NULL COMMENT 'utf8mb4 인덱스 키 길이 때문에 190자',
    password_hash VARCHAR(255) NOT NULL,
    nickname      VARCHAR(40)  NULL COMMENT '이전 스키마 호환용. 신규 앱은 name 사용',
    status        ENUM('active','dormant','withdrawn') NOT NULL DEFAULT 'active',
    role          ENUM('user','admin') NOT NULL DEFAULT 'user' COMMENT '관리자는 채팅 질문 한도가 늘어난다. 셀프서비스 승격 API는 없다',
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_app_user_username (username),
    UNIQUE KEY uk_app_user_email (email)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 로그인 기능 전의 app_user가 이미 있는 서버도 install.sh 재실행으로 안전하게 보강한다.
ALTER TABLE app_user
    ADD COLUMN IF NOT EXISTS username VARCHAR(40) NULL AFTER id,
    ADD COLUMN IF NOT EXISTS name VARCHAR(40) NULL AFTER username,
    ADD COLUMN IF NOT EXISTS role ENUM('user','admin') NOT NULL DEFAULT 'user' AFTER status;
UPDATE app_user SET name = COALESCE(NULLIF(name, ''), nickname, '묘한 사용자') WHERE name IS NULL OR name = '';
UPDATE app_user SET username = CONCAT('legacy_', id) WHERE username IS NULL OR username = '';
UPDATE app_user SET password_hash = '!disabled!' WHERE password_hash IS NULL OR password_hash = '';
ALTER TABLE app_user
    MODIFY COLUMN username VARCHAR(40) NOT NULL,
    MODIFY COLUMN name VARCHAR(40) NOT NULL,
    MODIFY COLUMN password_hash VARCHAR(255) NOT NULL,
    MODIFY COLUMN nickname VARCHAR(40) NULL,
    DROP COLUMN IF EXISTS failed_login_attempts,
    DROP COLUMN IF EXISTS locked_until;
SET @has_username_index = (
    SELECT COUNT(*) FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'app_user'
      AND INDEX_NAME = 'uk_app_user_username'
);
SET @add_username_index = IF(
    @has_username_index = 0,
    'ALTER TABLE app_user ADD UNIQUE KEY uk_app_user_username (username)',
    'SELECT 1'
);
PREPARE add_username_index FROM @add_username_index;
EXECUTE add_username_index;
DEALLOCATE PREPARE add_username_index;

CREATE TABLE IF NOT EXISTS auth_session (
    id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id    BIGINT UNSIGNED NOT NULL,
    token_hash CHAR(64) NOT NULL COMMENT 'Bearer 토큰 SHA-256. 원문 토큰은 저장하지 않음',
    expires_at DATETIME NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_auth_session_token (token_hash),
    KEY ix_auth_session_user (user_id),
    CONSTRAINT fk_auth_session_user FOREIGN KEY (user_id)
        REFERENCES app_user (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS auth_ip_lockout (
    ip_address            VARCHAR(45) NOT NULL,
    failed_login_attempts SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    locked_until          DATETIME NULL,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (ip_address),
    KEY ix_auth_ip_lockout_locked_until (locked_until)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- tarot_reading은 02번에서 먼저 생성되므로 계정 테이블이 생긴 이 시점에 FK를 건다.
SET @has_tarot_user_fk = (
    SELECT COUNT(*) FROM information_schema.TABLE_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'tarot_reading'
      AND CONSTRAINT_NAME = 'fk_tarot_reading_user'
);
SET @add_tarot_user_fk = IF(
    @has_tarot_user_fk = 0,
    'ALTER TABLE tarot_reading ADD CONSTRAINT fk_tarot_reading_user FOREIGN KEY (user_id) REFERENCES app_user (id)',
    'SELECT 1'
);
PREPARE add_tarot_user_fk FROM @add_tarot_user_fk;
EXECUTE add_tarot_user_fk;
DEALLOCATE PREPARE add_tarot_user_fk;

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
