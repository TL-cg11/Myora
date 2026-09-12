-- 기존 한자 사전 및 리딩을 유지하고 상담용 구조화 데이터만 추가한다.
CREATE TABLE IF NOT EXISTS saju_narrative_rule (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    category VARCHAR(24) NOT NULL,
    hanja VARCHAR(16) NOT NULL,
    data JSON NOT NULL,
    UNIQUE KEY uk_saju_narrative_rule (category, hanja)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
