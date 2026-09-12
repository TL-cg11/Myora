-- AI 가드레일과 회원 권한 등급 컬럼
-- 적용: sudo mysql -uroot luck_db < sql/init/16_ai_guardrail.sql
--
-- WAS 모델(app/models.py)이 이미 사용하는 컬럼인데 init SQL 에 빠져 있던 항목이다.
--   app_user.role                    : 일반 회원/관리자 구분. 관리자는 채팅 질문 한도가 다르다.
--   chat_message.policy_version      : 사주·관상 답변을 만들 때 적용한 가드레일 정책 버전
--   tarot_chat_message.policy_version: 타로 답변에 적용한 가드레일 정책 버전
-- ADD COLUMN IF NOT EXISTS 라 다시 실행해도 안전하고 기존 행은 건드리지 않는다.

ALTER TABLE app_user
    ADD COLUMN IF NOT EXISTS role ENUM('user','admin') NOT NULL DEFAULT 'user' AFTER status;

ALTER TABLE chat_message
    ADD COLUMN IF NOT EXISTS policy_version VARCHAR(16) NULL
        COMMENT '답변 생성에 적용한 가드레일 정책 버전. 모델 호출 전 예약 행은 NULL'
        AFTER source;

ALTER TABLE tarot_chat_message
    ADD COLUMN IF NOT EXISTS policy_version VARCHAR(16) NULL
        COMMENT '답변 생성에 적용한 가드레일 정책 버전. 모델 호출 전 예약 행은 NULL'
        AFTER source;
