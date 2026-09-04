-- 관상 세부 해석 20종
-- 적용: sudo mysql -uroot luck_db < sql/init/11_face_interpretation.sql
--
-- 얼굴형 5종은 face_shape 에서 관리하고, 측정 비율·첫인상에 따라 달라지는
-- 나머지 문구는 이 테이블에서 관리한다. 앱은 category/code 로 필요한 행을 골라
-- 최종 결과를 조합한다. 재실행해도 안전하도록 (category, code) 기준 UPSERT 한다.

CREATE TABLE IF NOT EXISTS face_interpretation (
    id          SMALLINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
    category    VARCHAR(24) NOT NULL COMMENT 'proportion/contour/eye/mouth/harmony/mood/closing',
    code        VARCHAR(32) NOT NULL,
    label       VARCHAR(80) NOT NULL,
    description VARCHAR(500) NOT NULL,
    keyword     VARCHAR(40) NULL,
    sort_order  SMALLINT UNSIGNED NOT NULL DEFAULT 0,
    is_active   TINYINT(1) NOT NULL DEFAULT 1,
    UNIQUE KEY uk_face_interpretation_category_code (category, code),
    KEY ix_face_interpretation_active (category, is_active, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO face_interpretation
    (category, code, label, description, keyword, sort_order)
VALUES
  ('proportion','long','길게 이어지는 세로 흐름','세로 흐름이 비교적 길게 이어져 차분하고 정돈된 윤곽으로 보여요.','#차분한윤곽',10),
  ('proportion','short','부드러운 가로세로 조화','세로와 가로 폭의 차이가 크지 않아 부드럽고 편안한 윤곽으로 보여요.','#편안한비율',20),
  ('proportion','balanced','안정적인 얼굴 비율','세로 길이와 가로 폭이 자연스럽게 맞물려 안정적인 윤곽으로 보여요.','#안정적인비율',30),

  ('contour','tapered','부드럽게 모이는 윤곽','이마 쪽의 여유에서 턱선으로 부드럽게 모이는 흐름이 보여요.','#부드러운윤곽',10),
  ('contour','strong-jaw','또렷한 하단 윤곽','이마보다 턱 쪽의 선이 또렷해 단정한 하단 윤곽이 돋보여요.','#또렷한턱선',20),
  ('contour','even','고르게 이어지는 윤곽','이마와 턱의 폭 차이가 크지 않아 위아래 흐름이 고르게 이어져요.','#고른윤곽',30),

  ('eye','wide','생동감 있는 눈매','눈의 가로 폭이 얼굴 윤곽 안에서 비교적 또렷하게 보여, 표정의 생동감이 먼저 전해지는 편이에요.','#또렷한눈매',10),
  ('eye','narrow','섬세하고 차분한 눈매','눈매가 전체 윤곽에 차분하게 어우러져, 처음에는 담백하고 가까이 볼수록 섬세한 분위기가 느껴져요.','#섬세한눈매',20),
  ('eye','balanced','편안하게 어우러지는 눈매','눈매와 얼굴 폭의 비율이 자연스럽게 어우러져, 편안하면서도 또렷한 첫인상을 만들어요.','#편안한눈매',30),

  ('mouth','wide','시원한 입매','입매의 가로선이 비교적 시원하게 보여요. 전통적인 표현으로는 활기찬 소통의 이미지에 빗대곤 해요.','#시원한입매',10),
  ('mouth','narrow','단정한 입매','입매가 단정하게 모여 보여 차분한 분위기를 더해요. 옛 해석에서는 신중한 소통의 이미지로 표현하곤 했어요.','#단정한입매',20),
  ('mouth','balanced','자연스러운 입매','입매가 얼굴 중심과 안정적으로 어우러져 부드럽고 자연스러운 소통의 인상을 더해요.','#자연스러운입매',30),

  ('harmony','high','매우 안정적인 좌우 흐름','사진 속 좌우 흐름이 매우 안정적으로 잡혀 전체적으로 정돈된 인상이 잘 드러났어요.','#정돈된조화',10),
  ('harmony','balanced','편안한 균형감','좌우 흐름이 자연스럽게 어우러져 편안한 균형감이 느껴져요.','#편안한균형',20),
  ('harmony','natural','생동감 있는 자연스러움','표정과 촬영 각도에서 생기는 자연스러운 좌우 차이가 보여 한층 생동감 있는 분위기가 느껴져요.','#자연스러운조화',30),

  ('mood','calm','차분한 첫인상','정돈된 표정과 차분한 분위기가 윤곽의 안정감을 더해 줘요.','#차분한분위기',10),
  ('mood','bright','밝은 첫인상','밝게 느껴지는 표정이 눈매와 입매의 생동감을 한층 살려 줘요.','#밝은분위기',20),
  ('mood','mysterious','신비로운 첫인상','잔잔한 표정 안에 시선이 머무는 분위기가 있어 여러 인상을 떠올리게 해요.','#신비로운분위기',30),
  ('mood','strong','단단한 첫인상','또렷한 중심선과 단정한 표정이 힘 있는 인상을 더해 줘요.','#단단한분위기',40),

  ('closing','default','묘라의 한마디','지금 가진 인상은 하나로 단정하기보다 표정과 마음에 따라 여러 매력으로 달라질 수 있어요. 편안하게 웃을 때 드러나는 자연스러운 분위기를 가장 좋은 복으로 간직해 보세요.',NULL,10)
ON DUPLICATE KEY UPDATE
  label = VALUES(label),
  description = VALUES(description),
  keyword = VALUES(keyword),
  sort_order = VALUES(sort_order),
  is_active = 1;
