-- 로그인 실패 잠금은 auth_ip_lockout에서만 관리한다.
-- app_user에는 계정 잠금 상태를 남기지 않는다.
ALTER TABLE app_user
    DROP COLUMN IF EXISTS failed_login_attempts,
    DROP COLUMN IF EXISTS locked_until;
