-- 관상 인상 유형 5종
-- 적용: sudo mysql -uroot luck_db < sql/design/09_face_seed.sql
--
-- 이 파일은 sql/init/ 이 아니라 sql/design/ 에 있다. install.sh 는 sql/init/*.sql 만
-- 적용하므로 이 폴더의 SQL 은 자동으로 실행되지 않는다. 사주·관상 저장을 실제로
-- 하기로 정한 뒤 손으로 적용한다. 배경은 docs/schema-design.html 참고.
-- 문구의 원본은 src/features/face-reading/interpretation/faceReadingRules.js 의
-- shapeReadings 다. code 는 classifyFaceShape() 가 돌려주는 값과 정확히 같아야 한다.
-- 재실행해도 안전하도록 code 기준 UPSERT 한다.

INSERT INTO face_shape (code, title, keyword, summary) VALUES
  ('하트형','섬세한 선과 또렷한 중심이 만나는 인상','#섬세한윤곽','윗부분의 여유와 아래로 모이는 윤곽이 함께 보여요. 전통 관상식 표현으로는 부드러운 감각과 분명한 집중력이 공존하는 모습으로 풀곤 해요.'),
  ('각진형','단정한 윤곽에서 안정감이 느껴지는 인상','#단정한인상','볼과 턱선의 폭이 비교적 고르게 이어져 전체 윤곽이 단정해 보여요. 옛 관상에서는 이런 균형을 꾸준함과 안정감의 상징으로 이야기하곤 했어요.'),
  ('둥근형','부드러운 여백이 편안함을 주는 인상','#편안한윤곽','세로와 가로 비율이 부드럽게 어우러지고 턱선도 완만하게 보여요. 전통적인 해석에서는 친근함과 유연한 분위기를 떠올리는 윤곽이에요.'),
  ('긴 타원형','차분한 흐름과 섬세함이 돋보이는 인상','#차분한인상','세로선이 자연스럽게 이어져 얼굴 전체가 차분하고 정돈되어 보여요. 옛 관상식으로는 생각을 천천히 정리하는 섬세한 기운에 빗대곤 해요.'),
  ('균형형','부드러움과 또렷함이 조화로운 인상','#균형있는인상','이마부터 턱까지의 흐름과 좌우 폭이 한쪽으로 치우치지 않고 자연스럽게 이어져요. 전통 관상에서는 이런 조화를 편안한 적응력의 상징으로 풀기도 해요.')
ON DUPLICATE KEY UPDATE
  title = VALUES(title), keyword = VALUES(keyword), summary = VALUES(summary);
