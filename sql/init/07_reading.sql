-- 세 기능이 공유하는 리딩 뼈대와 대화
-- 적용: sudo mysql -uroot luck_db < sql/init/07_reading.sql
--
-- 스키마만 미리 만들어 둔다. 사주/관상이 아직 이 테이블에 아무것도 쓰지 않고,
-- 타로는 기존 tarot_reading 을 그대로 계속 쓴다(마이그레이션은 아직 안 한다).
-- 빈 테이블이라 모양이 안 맞으면 ALTER TABLE 로 바로 고치면 된다. 배경은
-- docs/schema-design.html 참고.
--
-- 사주/관상/타로의 결과는 모두 reading 행 하나로 시작하고, 기능 고유 정보는
-- saju_reading / face_reading / tarot_reading 이 같은 PK 로 1:1 로 물고 간다.
-- 마이페이지 목록이 이 테이블 하나만 읽으면 되도록 하는 것이 목적이다.

CREATE TABLE IF NOT EXISTS reading (
    id            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    service       ENUM('saju','face','tarot') NOT NULL,
    user_id       BIGINT UNSIGNED NULL,
    guest_key     CHAR(36) NULL COMMENT '비회원 식별자. 브라우저가 보관한다',
    summary_title VARCHAR(120) NULL,
    summary_text  TEXT NULL,
    interpretation_source ENUM('rule','llm') NOT NULL DEFAULT 'rule',
    llm_model     VARCHAR(64) NULL,
    status        ENUM('created','interpreted','failed') NOT NULL DEFAULT 'created',
    created_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY ix_reading_user  (user_id, created_at),
    KEY ix_reading_guest (guest_key, created_at),
    -- ON DELETE SET NULL 을 쓰면 아래 CHECK 를 만들 수 없다. MariaDB 는 SET NULL 이
    -- CHECK 를 깰 수 있다고 보고 거부한다(ERROR 1901). RESTRICT(기본값)로 두면
    -- 리딩이 있는 회원은 행을 지울 수 없고, 탈퇴는 status='withdrawn' 으로 처리하게 된다.
    -- 설계 의도가 원래 그것이라 제약으로 굳힌다.
    CONSTRAINT fk_reading_user FOREIGN KEY (user_id)
        REFERENCES app_user (id),
    CONSTRAINT ck_reading_owner CHECK (user_id IS NOT NULL OR guest_key IS NOT NULL)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS chat_message (
    id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    reading_id BIGINT UNSIGNED NOT NULL,
    seq        SMALLINT UNSIGNED NOT NULL,
    role       ENUM('system','user','assistant') NOT NULL,
    content    TEXT NOT NULL,
    source     ENUM('rule','llm') NULL COMMENT 'assistant 답변을 무엇으로 만들었나',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_chat_message_seq (reading_id, seq),
    CONSTRAINT fk_chat_message_reading FOREIGN KEY (reading_id)
        REFERENCES reading (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
