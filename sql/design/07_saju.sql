-- 사주 계산 결과와 리딩 상세
-- 적용: sudo mysql -uroot luck_db < sql/design/07_saju.sql
--
-- 이 파일은 sql/init/ 이 아니라 sql/design/ 에 있다. install.sh 는 sql/init/*.sql 만
-- 적용하므로 이 폴더의 SQL 은 자동으로 실행되지 않는다. 사주·관상 저장을 실제로
-- 하기로 정한 뒤 손으로 적용한다. 배경은 docs/schema-design.html 참고.
--
-- 사주는 같은 생년월일시/성별이면 언제 계산해도 결과가 같다. 그래서 리딩마다
-- 복사하지 않고 saju_chart 에 한 번 계산해 두고 참조한다.
-- engine_version 을 유니크 키에 넣은 이유는 korean-saju 가 올라가 계산이 달라져도
-- 과거 리딩이 그때 보여준 결과를 그대로 유지하기 위해서다. 새 버전은 새 행이 된다.

CREATE TABLE IF NOT EXISTS saju_chart (
    id             BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    birth_date     DATE NOT NULL,
    birth_time     TIME NULL,
    time_unknown   TINYINT(1) NOT NULL DEFAULT 0,
    gender         ENUM('female','male','unknown') NOT NULL,
    engine_version VARCHAR(32) NOT NULL COMMENT 'korean-saju 버전',
    pillar_year    CHAR(2) NOT NULL COMMENT '갑자 두 글자',
    pillar_month   CHAR(2) NOT NULL,
    pillar_day     CHAR(2) NOT NULL,
    pillar_hour    CHAR(2) NULL COMMENT '시각을 모르면 NULL',
    jeonggyeok     VARCHAR(40) NULL,
    yongsin        VARCHAR(40) NULL,
    sinsal         JSON NULL COMMENT '개수가 유동적이라 JSON. 조회가 필요해지면 펴면 된다',
    computed_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- birth_time 이 NULL 인 행은 MySQL 유니크 키가 중복을 막지 못한다.
    -- time_unknown=1 인 경우 birth_time 을 '00:00:00' 으로 채워 넣어 회피한다.
    UNIQUE KEY uk_saju_chart (birth_date, birth_time, time_unknown, gender, engine_version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS saju_reading (
    reading_id       BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    chart_id         BIGINT UNSIGNED NOT NULL,
    birth_profile_id BIGINT UNSIGNED NULL COMMENT '비회원이면 NULL',
    topic            ENUM('general','love','career','money','health') NOT NULL DEFAULT 'general',
    question         VARCHAR(255) NULL,
    KEY ix_saju_reading_chart (chart_id),
    KEY ix_saju_reading_profile (birth_profile_id),
    CONSTRAINT fk_saju_reading_reading FOREIGN KEY (reading_id)
        REFERENCES reading (id) ON DELETE CASCADE,
    CONSTRAINT fk_saju_reading_chart FOREIGN KEY (chart_id)
        REFERENCES saju_chart (id),
    CONSTRAINT fk_saju_reading_profile FOREIGN KEY (birth_profile_id)
        REFERENCES birth_profile (id) ON DELETE SET NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
