-- 결과 스냅샷이 아닌, 한자/용어별 한글 뜻 사전. 기존 테이블 변경 없음.
CREATE TABLE IF NOT EXISTS saju_term (
    id INT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    category VARCHAR(24) NOT NULL,
    hanja VARCHAR(16) NOT NULL,
    name_ko VARCHAR(40) NOT NULL,
    meaning_ko TEXT NOT NULL,
    UNIQUE KEY uk_saju_term (category, hanja)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
