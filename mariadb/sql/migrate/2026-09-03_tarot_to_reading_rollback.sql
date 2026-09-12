-- 이관을 되돌린다. 이관 도중 실패했거나 앱 전환 후 문제가 생겼을 때 쓴다.
-- 실행: sudo mysql -uroot luck_db < sql/migrate/2026-09-03_tarot_to_reading_rollback.sql
--
-- tarot_reading_old 가 남아 있는지로 되돌릴 것이 있는지 판단한다. 없으면 아무것도
-- 하지 않는다. 조건 없이 DROP TABLE tarot_reading 을 하면 이미 되돌아온 진짜
-- 데이터를 지우게 되므로, 프로시저로 감싸 상태를 확인한 뒤 실행한다.
--
-- 옛 테이블을 이미 DROP 했다면 이 스크립트로는 되돌릴 수 없다. 백업에서 복구해야 한다.

DELIMITER //

CREATE OR REPLACE PROCEDURE rollback_tarot_to_reading()
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.TABLES
                 WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tarot_reading_old') THEN
    SELECT '되돌릴 것이 없습니다. tarot_reading_old 가 없어 이미 롤백됐거나 이관이 시작된 적 없습니다.' AS status;
  ELSE
    -- 1) tarot_reading_card 를 새 구조에서 떼어낸다.
    ALTER TABLE tarot_reading_card DROP FOREIGN KEY IF EXISTS fk_tarot_reading_card_reading;

    -- 2) 이관이 만든 것만 지운다. 여기서 지우는 tarot_reading 은 reading_id 를 PK 로
    --    갖는 새 테이블이고, 원본은 tarot_reading_old 에 그대로 있다.
    DROP TABLE IF EXISTS tarot_reading;
    DELETE FROM chat_message
     WHERE reading_id IN (SELECT id FROM reading WHERE service = 'tarot');
    DELETE FROM reading WHERE service = 'tarot';

    -- 3) 옛 테이블을 제자리로 되돌린다.
    RENAME TABLE tarot_reading_old TO tarot_reading;
    IF EXISTS (SELECT 1 FROM information_schema.TABLES
               WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'tarot_chat_message_old') THEN
      RENAME TABLE tarot_chat_message_old TO tarot_chat_message;
    END IF;

    -- 4) FK 를 복구한다. 이관이 어디서 멈췄느냐에 따라 남아 있을 수 있어 먼저 뗀다.
    ALTER TABLE tarot_reading DROP FOREIGN KEY IF EXISTS fk_tarot_reading_spread;
    ALTER TABLE tarot_reading
      ADD CONSTRAINT fk_tarot_reading_spread FOREIGN KEY (spread_id)
          REFERENCES tarot_spread (id);
    ALTER TABLE tarot_reading_card
      ADD CONSTRAINT fk_tarot_reading_card_reading FOREIGN KEY (reading_id)
          REFERENCES tarot_reading (id) ON DELETE CASCADE;

    SELECT '롤백 완료' AS status,
           (SELECT COUNT(*) FROM tarot_reading) AS 리딩,
           (SELECT COUNT(*) FROM tarot_reading_card) AS 카드,
           (SELECT COUNT(*) FROM tarot_chat_message) AS 대화;
  END IF;
END //

DELIMITER ;

CALL rollback_tarot_to_reading();
DROP PROCEDURE rollback_tarot_to_reading;
