-- 일반 회원 로그인 연속 실패 잠금 상태를 저장한다.
-- 적용: sudo mysql -uroot luck_db < sql/migrate/2026-09-09_auth_lockout.sql

ALTER TABLE app_user
    ADD COLUMN IF NOT EXISTS failed_login_attempts SMALLINT UNSIGNED NOT NULL DEFAULT 0 AFTER status,
    ADD COLUMN IF NOT EXISTS locked_until DATETIME NULL AFTER failed_login_attempts;
