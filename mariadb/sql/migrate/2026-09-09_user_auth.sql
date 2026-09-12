-- 기존 luck_db에 회원가입/로그인과 사용자별 리딩 소유권을 적용한다.
-- 적용: sudo mysql -uroot luck_db < sql/migrate/2026-09-09_user_auth.sql

ALTER TABLE app_user
    ADD COLUMN IF NOT EXISTS username VARCHAR(40) NULL AFTER id,
    ADD COLUMN IF NOT EXISTS name VARCHAR(40) NULL AFTER username;

-- 예전 nickname 값이 있으면 이름으로 보존한다.
UPDATE app_user SET name = COALESCE(NULLIF(name, ''), nickname, '묘한 사용자') WHERE name IS NULL OR name = '';
UPDATE app_user SET username = CONCAT('legacy_', id) WHERE username IS NULL OR username = '';
UPDATE app_user SET password_hash = '!disabled!' WHERE password_hash IS NULL OR password_hash = '';

ALTER TABLE app_user
    MODIFY COLUMN username VARCHAR(40) NOT NULL,
    MODIFY COLUMN name VARCHAR(40) NOT NULL,
    MODIFY COLUMN nickname VARCHAR(40) NULL,
    MODIFY COLUMN password_hash VARCHAR(255) NOT NULL;

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
    token_hash CHAR(64) NOT NULL,
    expires_at DATETIME NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_auth_session_token (token_hash),
    KEY ix_auth_session_user (user_id),
    CONSTRAINT fk_auth_session_user FOREIGN KEY (user_id)
        REFERENCES app_user (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 타로 리딩도 회원 FK를 확정한다. 기존 비회원 행은 그대로 유지된다.
SET @has_tarot_user_fk = (
    SELECT COUNT(*) FROM information_schema.REFERENTIAL_CONSTRAINTS
    WHERE CONSTRAINT_SCHEMA = DATABASE() AND TABLE_NAME = 'tarot_reading'
      AND CONSTRAINT_NAME = 'fk_tarot_reading_user'
);
SET @add_tarot_user_fk = IF(
    @has_tarot_user_fk = 0,
    'ALTER TABLE tarot_reading ADD CONSTRAINT fk_tarot_reading_user FOREIGN KEY (user_id) REFERENCES app_user (id)',
    'SELECT 1'
);
PREPARE stmt FROM @add_tarot_user_fk;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
