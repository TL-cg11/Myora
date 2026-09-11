-- 관리자 계정은 채팅 질문 한도가 늘어난다(app/auth.py의 question_limit_for()).
-- 셀프서비스 승격 API는 없다. 관리자 지정은 이 파일 적용 후 아래 UPDATE로 직접 한다.
-- 적용: sudo mysql -uroot luck_db < sql/migrate/2026-09-11_app_user_role.sql

ALTER TABLE app_user
    ADD COLUMN IF NOT EXISTS role ENUM('user','admin') NOT NULL DEFAULT 'user' AFTER status;

-- 관리자로 지정할 계정마다 실행한다. 이 파일 자체는 실행하지 않는다.
-- UPDATE app_user SET role = 'admin' WHERE username = '<계정>';
