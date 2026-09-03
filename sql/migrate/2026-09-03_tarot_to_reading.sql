-- 기존 타로 리딩을 공통 reading 구조로 옮긴다.
--
-- sql/init/ 에 두지 않는다. install.sh 가 sql/init/*.sql 을 매번 전부 적용하는데
-- 이관은 한 번만 실행되어야 하기 때문이다.
--
-- 실행:  sudo mysql -uroot luck_db < sql/migrate/2026-09-03_tarot_to_reading.sql
-- 선행:  sql/design/05_account.sql, 06_reading.sql 이 먼저 적용되어 있어야 한다.
--
-- ⚠ 이 스크립트는 원자적이지 않다. MariaDB 는 DDL(RENAME/CREATE/ALTER)에서 암묵적
--   커밋을 일으켜 트랜잭션으로 묶어도 롤백되지 않는다. 중간에 실패하면
--   2026-09-03_tarot_to_reading_rollback.sql 을 실행해 되돌린 뒤 원인을 고치고
--   다시 시작한다. 실행 전 반드시 mysqldump 로 백업할 것.

DELIMITER //

CREATE OR REPLACE PROCEDURE migrate_tarot_to_reading()
BEGIN
  -- 두 번 돌리면 reading 에 같은 id 가 다시 들어가 깨진다. 흔적으로 판단해 막는다.
  IF EXISTS (SELECT 1 FROM information_schema.TABLES
             WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tarot_reading_old') THEN
    SELECT '이미 이관됐습니다(tarot_reading_old 존재). 아무것도 하지 않았습니다.' AS status;
  ELSEIF NOT EXISTS (SELECT 1 FROM information_schema.TABLES
                     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'reading') THEN
    SELECT 'reading 테이블이 없습니다. sql/design/06_reading.sql 을 먼저 적용하세요.' AS status;
  ELSE
    -- 1) 옛 테이블을 밀어둔다. 이름만 바꾸는 것이라 데이터는 그대로다.
    RENAME TABLE tarot_reading      TO tarot_reading_old;
    RENAME TABLE tarot_chat_message TO tarot_chat_message_old;

    -- 2) 옛 테이블의 FK 를 뗀다.
    --    InnoDB 의 FK 이름은 스키마 전체에서 유일해야 하는데, RENAME 은 제약 이름을
    --    그대로 들고 간다. 떼지 않으면 아래에서 같은 이름을 다시 쓸 수 없다.
    --    백업용 테이블이라 FK 가 없어도 된다.
    ALTER TABLE tarot_reading_old DROP FOREIGN KEY fk_tarot_reading_spread;

    -- 3) 소유자/요약/상태를 reading 으로 올린다.
    --    id 를 그대로 가져가면 아래 단계에서 매핑 테이블이 필요 없다.
    INSERT INTO reading
      (id, service, user_id, guest_key, summary_title, summary_text,
       interpretation_source, llm_model, status, created_at, updated_at)
    SELECT
      id, 'tarot', user_id, guest_key, summary_title, summary_text,
      interpretation_source, llm_model,
      -- 옛 status 는 drawn/interpreted/failed, 새 status 는 created/interpreted/failed
      CASE status WHEN 'drawn' THEN 'created' ELSE status END,
      created_at, updated_at
    FROM tarot_reading_old;

    -- 4) 타로에만 있는 칼럼으로 새 tarot_reading 을 만든다.
    CREATE TABLE tarot_reading (
        reading_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
        spread_id  SMALLINT UNSIGNED NOT NULL,
        topic      ENUM('general','love','career','money','health') NOT NULL DEFAULT 'general',
        question   VARCHAR(255) NULL,
        KEY ix_tarot_reading_spread (spread_id),
        CONSTRAINT fk_tarot_reading_reading FOREIGN KEY (reading_id)
            REFERENCES reading (id) ON DELETE CASCADE,
        CONSTRAINT fk_tarot_reading_spread FOREIGN KEY (spread_id)
            REFERENCES tarot_spread (id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

    INSERT INTO tarot_reading (reading_id, spread_id, topic, question)
    SELECT id, spread_id, topic, question FROM tarot_reading_old;

    -- 5) 대화를 공통 chat_message 로 옮긴다. reading_id 가 그대로라 변환이 없다.
    INSERT INTO chat_message (reading_id, seq, role, content, created_at)
    SELECT reading_id, seq, role, content, created_at FROM tarot_chat_message_old;

    -- 6) tarot_reading_card 의 FK 를 옛 테이블에서 reading 으로 옮긴다.
    --    RENAME 때 InnoDB 가 참조 대상을 tarot_reading_old 로 자동으로 바꿔 놓았다.
    ALTER TABLE tarot_reading_card DROP FOREIGN KEY fk_tarot_reading_card_reading;
    ALTER TABLE tarot_reading_card
      ADD CONSTRAINT fk_tarot_reading_card_reading FOREIGN KEY (reading_id)
          REFERENCES reading (id) ON DELETE CASCADE;

    SELECT '이관 완료' AS status;
  END IF;
END //

DELIMITER ;

CALL migrate_tarot_to_reading();
DROP PROCEDURE migrate_tarot_to_reading;

-- 7) 옮겨진 행 수가 맞는지 확인한다. 세 줄 모두 old_cnt = new_cnt 여야 한다.
SELECT 'reading'       AS what, (SELECT COUNT(*) FROM tarot_reading_old) AS old_cnt,
                                (SELECT COUNT(*) FROM reading WHERE service='tarot') AS new_cnt
UNION ALL
SELECT 'tarot_reading', (SELECT COUNT(*) FROM tarot_reading_old),
                        (SELECT COUNT(*) FROM tarot_reading)
UNION ALL
SELECT 'chat_message',  (SELECT COUNT(*) FROM tarot_chat_message_old),
                        (SELECT COUNT(*) FROM chat_message);

-- 8) 앱 전환이 끝나고 며칠 지켜본 뒤 옛 테이블을 지운다.
--    DROP TABLE tarot_chat_message_old, tarot_reading_old;
