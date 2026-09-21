-- 로그인 실패 잠금을 계정이 아닌 접속 IP 기준으로 저장한다.
-- 기존 app_user 잠금 컬럼은 호환을 위해 유지하지만 WAS는 더 이상 사용하지 않는다.
CREATE TABLE IF NOT EXISTS auth_ip_lockout (
    ip_address            VARCHAR(45) NOT NULL,
    failed_login_attempts SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    locked_until          DATETIME NULL,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (ip_address),
    KEY ix_auth_ip_lockout_locked_until (locked_until)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
