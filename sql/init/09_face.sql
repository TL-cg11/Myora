-- 관상 인상 유형과 리딩 상세
-- 적용: sudo mysql -uroot luck_db < sql/init/09_face.sql
--
-- 스키마만 미리 만들어 둔다. 관상 판정은 지금 브라우저(MediaPipe)에서 이뤄지고
-- 서버에는 아무것도 보내지 않는다. 판정을 서버로 옮기고 결과를 저장하기로
-- 정하면 이 테이블을 그대로 쓰면 된다.
--
-- 사진과 랜드마크 좌표는 저장하지 않는다. 결과 문구를 다시 만드는 데 필요한 것은
-- 비율 여섯 개와 사용자가 고른 mood 뿐이다(faceReadingRules.js createFaceReading).
-- 얼굴형은 aspect/jaw/forehead 세 비율에서 파생되므로 따로 저장하지 않아도 된다.

CREATE TABLE IF NOT EXISTS face_shape (
    id        SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    code      VARCHAR(32) NOT NULL COMMENT 'classifyFaceShape 가 돌려주는 값',
    title     VARCHAR(80) NOT NULL,
    keyword   VARCHAR(40) NOT NULL,
    summary   VARCHAR(500) NOT NULL,
    is_active TINYINT(1) NOT NULL DEFAULT 1,
    UNIQUE KEY uk_face_shape_code (code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS face_reading (
    reading_id       BIGINT UNSIGNED NOT NULL PRIMARY KEY,
    shape_id         SMALLINT UNSIGNED NULL,
    -- 판정 경계값(eyeRatio >= 0.205, jawRatio > 0.91)과 정확히 비교하려고
    -- FLOAT 이 아니라 DECIMAL 을 쓴다. 모든 비율이 얼굴 폭 대비라 1 근처에 모인다.
    aspect_ratio     DECIMAL(5,4) NOT NULL COMMENT '얼굴 세로/가로',
    jaw_ratio        DECIMAL(5,4) NOT NULL,
    forehead_ratio   DECIMAL(5,4) NOT NULL,
    eye_ratio        DECIMAL(5,4) NOT NULL,
    mouth_ratio      DECIMAL(5,4) NOT NULL,
    symmetry_score   DECIMAL(5,4) NOT NULL COMMENT '좌우 대칭. 결과 문장은 harmonyReading 이 만든다',
    mood             VARCHAR(20) NULL COMMENT '사용자가 고른 첫인상 키워드',
    detector_version VARCHAR(32) NOT NULL COMMENT 'MediaPipe 모델 버전',
    -- 아래 셋은 촬영 품질 게이트(validateFacePose)용이라 결과에 영향이 없다.
    -- 문의 대응 때 재현하려면 필요해서 남겨두되 NULL 을 허용한다.
    coverage         DECIMAL(5,4) NULL,
    roll_degrees     DECIMAL(5,2) NULL,
    nose_offset      DECIMAL(5,4) NULL,
    CONSTRAINT fk_face_reading_reading FOREIGN KEY (reading_id)
        REFERENCES reading (id) ON DELETE CASCADE,
    CONSTRAINT fk_face_reading_shape FOREIGN KEY (shape_id)
        REFERENCES face_shape (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
