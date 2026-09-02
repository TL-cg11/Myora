-- 타로 도메인 스키마
-- 적용: sudo mysql -uroot luck_db < sql/init/02_tarot.sql
-- luck_user 에게는 DDL 권한이 없으므로 반드시 root 로 적용한다.

-- 카드 카탈로그 --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tarot_card (
    id               SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    code             VARCHAR(16)  NOT NULL COMMENT 'major-18, cups-03 형태의 고정 식별자',
    arcana           ENUM('major','minor') NOT NULL,
    suit             ENUM('wands','cups','swords','pentacles') NULL COMMENT '메이저는 NULL',
    number           TINYINT UNSIGNED NOT NULL COMMENT '메이저 0-21, 마이너 1-14(11 페이지·12 나이트·13 퀸·14 킹)',
    name_ko          VARCHAR(40)  NOT NULL,
    name_en          VARCHAR(40)  NOT NULL,
    keyword_upright  VARCHAR(120) NOT NULL COMMENT '쉼표로 구분한 핵심어',
    keyword_reversed VARCHAR(120) NOT NULL,
    meaning_upright  VARCHAR(500) NOT NULL,
    meaning_reversed VARCHAR(500) NOT NULL,
    image_path       VARCHAR(255) NULL COMMENT '/assets 기준 상대 경로',
    is_active        TINYINT(1)   NOT NULL DEFAULT 1,
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_tarot_card_code (code),
    UNIQUE KEY uk_tarot_card_arcana_suit_number (arcana, suit, number),
    KEY ix_tarot_card_active (is_active)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 주제별 해석 (연애/직업/금전...). 없으면 tarot_card 의 일반 해석을 사용한다.
CREATE TABLE IF NOT EXISTS tarot_card_meaning (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    card_id     SMALLINT UNSIGNED NOT NULL,
    topic       ENUM('love','career','money','health') NOT NULL,
    orientation ENUM('upright','reversed') NOT NULL,
    meaning     VARCHAR(500) NOT NULL,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY uk_tarot_card_meaning (card_id, topic, orientation),
    CONSTRAINT fk_tarot_card_meaning_card FOREIGN KEY (card_id)
        REFERENCES tarot_card (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 스프레드 정의 --------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tarot_spread (
    id          SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    code        VARCHAR(32)  NOT NULL COMMENT 'one-card, past-present-future ...',
    name_ko     VARCHAR(40)  NOT NULL,
    description VARCHAR(255) NOT NULL,
    card_count  TINYINT UNSIGNED NOT NULL,
    sort_order  SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    is_active   TINYINT(1)   NOT NULL DEFAULT 1,
    created_at  TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_tarot_spread_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tarot_spread_position (
    id          SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    spread_id   SMALLINT UNSIGNED NOT NULL,
    position_no TINYINT UNSIGNED NOT NULL COMMENT '1부터 시작',
    label_ko    VARCHAR(40)  NOT NULL COMMENT '과거 / 현재 / 미래',
    description VARCHAR(255) NULL,
    UNIQUE KEY uk_tarot_spread_position (spread_id, position_no),
    CONSTRAINT fk_tarot_spread_position_spread FOREIGN KEY (spread_id)
        REFERENCES tarot_spread (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 리딩 기록 ------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tarot_reading (
    id                    BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    user_id               BIGINT UNSIGNED NULL COMMENT '회원. users 테이블 확정 후 FK 추가 예정',
    guest_key             CHAR(36) NULL COMMENT '비회원 식별용 UUID(클라이언트 보관)',
    spread_id             SMALLINT UNSIGNED NOT NULL,
    topic                 ENUM('general','love','career','money','health') NOT NULL DEFAULT 'general',
    question              VARCHAR(255) NULL,
    summary_title         VARCHAR(120) NULL,
    summary_text          TEXT NULL,
    interpretation_source ENUM('rule','llm') NOT NULL DEFAULT 'rule',
    llm_model             VARCHAR(64) NULL,
    status                ENUM('drawn','interpreted','failed') NOT NULL DEFAULT 'drawn',
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    KEY ix_tarot_reading_user (user_id, created_at),
    KEY ix_tarot_reading_guest (guest_key, created_at),
    CONSTRAINT fk_tarot_reading_spread FOREIGN KEY (spread_id)
        REFERENCES tarot_spread (id),
    CONSTRAINT ck_tarot_reading_owner CHECK (user_id IS NOT NULL OR guest_key IS NOT NULL)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS tarot_reading_card (
    id          BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    reading_id  BIGINT UNSIGNED NOT NULL,
    position_no TINYINT UNSIGNED NOT NULL,
    card_id     SMALLINT UNSIGNED NOT NULL,
    orientation ENUM('upright','reversed') NOT NULL DEFAULT 'upright',
    UNIQUE KEY uk_tarot_reading_card_position (reading_id, position_no),
    UNIQUE KEY uk_tarot_reading_card_card (reading_id, card_id) COMMENT '한 리딩에 같은 카드 중복 금지',
    KEY ix_tarot_reading_card_card (card_id),
    CONSTRAINT fk_tarot_reading_card_reading FOREIGN KEY (reading_id)
        REFERENCES tarot_reading (id) ON DELETE CASCADE,
    CONSTRAINT fk_tarot_reading_card_card FOREIGN KEY (card_id)
        REFERENCES tarot_card (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 결과 화면의 AI 채팅 (POST /api/chat) --------------------------------------
CREATE TABLE IF NOT EXISTS tarot_chat_message (
    id         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    reading_id BIGINT UNSIGNED NOT NULL,
    seq        SMALLINT UNSIGNED NOT NULL COMMENT '리딩 내 순번, 1부터',
    role       ENUM('system','user','assistant') NOT NULL,
    content    TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_tarot_chat_message_seq (reading_id, seq),
    CONSTRAINT fk_tarot_chat_message_reading FOREIGN KEY (reading_id)
        REFERENCES tarot_reading (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
