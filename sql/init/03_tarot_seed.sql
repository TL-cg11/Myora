-- 타로 기준 데이터 (스프레드 + 메이저 아르카나 22장)
-- 재실행해도 안전하도록 code 기준 UPSERT 한다.
-- 마이너 아르카나 56장은 같은 형식으로 이어 붙이면 되며 스키마 변경은 필요 없다.

INSERT INTO tarot_spread (code, name_ko, description, card_count, sort_order) VALUES
  ('one-card',            '한 장 뽑기',   '오늘 하루의 흐름을 한 장으로 간단히 봅니다.',        1, 10),
  ('past-present-future', '쓰리 카드',    '과거·현재·미래의 흐름을 세 장으로 읽습니다.',        3, 20),
  ('situation-advice',    '상황과 조언',  '지금 상황, 걸림돌, 조언을 세 장으로 봅니다.',        3, 30)
ON DUPLICATE KEY UPDATE
  name_ko = VALUES(name_ko), description = VALUES(description),
  card_count = VALUES(card_count), sort_order = VALUES(sort_order);

INSERT INTO tarot_spread_position (spread_id, position_no, label_ko, description)
SELECT s.id, p.position_no, p.label_ko, p.description
FROM tarot_spread s
JOIN (
  SELECT 'one-card' AS code, 1 AS position_no, '오늘'   AS label_ko, '오늘 하루의 핵심 흐름'        AS description UNION ALL
  SELECT 'past-present-future', 1, '과거',   '지금에 영향을 준 지난 흐름'  UNION ALL
  SELECT 'past-present-future', 2, '현재',   '지금 놓여 있는 자리'         UNION ALL
  SELECT 'past-present-future', 3, '미래',   '이대로 갔을 때의 방향'       UNION ALL
  SELECT 'situation-advice',    1, '상황',   '질문이 놓인 현재 상황'       UNION ALL
  SELECT 'situation-advice',    2, '걸림돌', '흐름을 막고 있는 것'         UNION ALL
  SELECT 'situation-advice',    3, '조언',   '지금 취하면 좋은 태도'
) p ON p.code = s.code
ON DUPLICATE KEY UPDATE
  label_ko = VALUES(label_ko), description = VALUES(description);

INSERT INTO tarot_card
  (code, arcana, suit, number, name_ko, name_en, keyword_upright, keyword_reversed, meaning_upright, meaning_reversed, image_path)
VALUES
  ('major-00','major',NULL, 0,'바보','The Fool','시작,자유,순수','무모함,불안,회피','아직 정해지지 않은 길 위에 서 있어요. 계산보다 마음이 끌리는 쪽으로 첫발을 내디뎌도 좋은 때예요.','준비 없이 서두르면 흔들리기 쉬워요. 설레는 마음과 현실을 한 번 맞춰볼 시점이에요.','/assets/tarot/major-00.png'),
  ('major-01','major',NULL, 1,'마법사','The Magician','실행,재능,주도','과신,산만,공회전','필요한 재료가 이미 손안에 있어요. 미루던 일을 직접 움직여 시작하기 좋은 흐름이에요.','의욕은 큰데 방향이 흩어져 있어요. 여러 갈래 대신 하나에 힘을 모아보세요.','/assets/tarot/major-01.png'),
  ('major-02','major',NULL, 2,'여사제','The High Priestess','직관,침묵,내면','불신,외면,혼란','드러난 것보다 감춰진 쪽에 답이 있어요. 서둘러 말하기보다 조용히 지켜볼 때예요.','속마음을 계속 덮어두면 오해가 자라요. 스스로의 감을 다시 믿어봐도 괜찮아요.','/assets/tarot/major-02.png'),
  ('major-03','major',NULL, 3,'여황제','The Empress','풍요,돌봄,결실','소진,의존,정체','들인 정성이 눈에 보이는 결실로 돌아오는 시기예요. 나를 넉넉히 챙겨도 좋아요.','남을 돌보느라 스스로가 비어가고 있어요. 받는 연습도 필요한 때예요.','/assets/tarot/major-03.png'),
  ('major-04','major',NULL, 4,'황제','The Emperor','안정,기준,책임','고집,통제,경직','원칙을 세우면 흐름이 잡혀요. 미뤄둔 구조와 규칙을 정리하기 좋은 때예요.','내 방식만 고수하면 관계가 굳어져요. 기준을 조금 느슨히 해도 무너지지 않아요.','/assets/tarot/major-04.png'),
  ('major-05','major',NULL, 5,'교황','The Hierophant','배움,조언,전통','형식,답습,반발','먼저 걸어본 사람의 말이 도움이 되는 시기예요. 조언을 구하는 것이 지름길이에요.','익숙한 방식이 나에게 맞지 않을 수 있어요. 내 기준으로 다시 물어볼 때예요.','/assets/tarot/major-05.png'),
  ('major-06','major',NULL, 6,'연인','The Lovers','선택,조화,진심','갈등,미룸,불균형','관계와 가치 사이에서 진심을 확인해 보세요. 마음이 향하는 쪽이 답에 가까워요.','결정을 미루는 동안 마음이 지쳐요. 무엇을 포기할지부터 정하면 가벼워져요.','/assets/tarot/major-06.png'),
  ('major-07','major',NULL, 7,'전차','The Chariot','추진,의지,돌파','제자리,조급,방향상실','흔들림 없이 밀고 나가면 길이 열려요. 지금은 속도를 내도 좋은 구간이에요.','힘은 쓰는데 앞으로 나아가지 않아요. 목적지를 다시 확인할 때예요.','/assets/tarot/major-07.png'),
  ('major-08','major',NULL, 8,'힘','Strength','끈기,용기,다정함','위축,소모,인내부족','부드러운 끈기가 상황을 바꿀 수 있어요. 세게 누르기보다 천천히 달래보세요.','참는 일이 버거워지고 있어요. 잠시 물러나 힘을 회복해도 괜찮아요.','/assets/tarot/major-08.png'),
  ('major-09','major',NULL, 9,'은둔자','The Hermit','성찰,고요,집중','고립,회피,외로움','혼자 있는 시간이 답을 데려와요. 소란에서 한 발 떨어져 정리해 보세요.','너무 오래 혼자 두면 생각이 굳어요. 한 사람에게라도 마음을 열어보세요.','/assets/tarot/major-09.png'),
  ('major-10','major',NULL,10,'운명의 수레바퀴','Wheel of Fortune','전환,기회,흐름','지연,반복,타이밍','상황이 스스로 움직이기 시작해요. 찾아온 기회를 놓치지 않는 것이 중요해요.','같은 자리를 도는 느낌이라면 잠시 멈춰도 좋아요. 아직 때가 아닐 뿐이에요.','/assets/tarot/major-10.png'),
  ('major-11','major',NULL,11,'정의','Justice','균형,공정,결정','편향,미결,책임회피','한쪽으로 기울었던 것이 제자리를 찾아요. 솔직하게 따져보면 답이 분명해져요.','판단을 미루면 부담만 커져요. 감정과 사실을 나눠서 볼 필요가 있어요.','/assets/tarot/major-11.png'),
  ('major-12','major',NULL,12,'매달린 사람','The Hanged Man','전환,기다림,관점','정체,희생,답답함','지금은 애쓰기보다 관점을 바꿀 때예요. 멈춤도 하나의 선택이에요.','붙잡고 있는 것 때문에 지쳐가요. 놓아도 되는 것을 구분해 보세요.','/assets/tarot/major-12.png'),
  ('major-13','major',NULL,13,'죽음','Death','마무리,변화,정리','미련,지연,두려움','한 시기가 끝나고 새로운 자리가 생겨요. 정리하는 만큼 가벼워지는 때예요.','끝난 것을 붙잡고 있어요. 아쉬움을 인정하면 다음이 보이기 시작해요.','/assets/tarot/major-13.png'),
  ('major-14','major',NULL,14,'절제','Temperance','조율,중용,회복','과함,불균형,조바심','서로 다른 것을 알맞게 섞는 감각이 살아나요. 속도를 고르면 오래 갈 수 있어요.','한쪽으로 치우쳐 무리하고 있어요. 덜어내는 쪽이 회복을 앞당겨요.','/assets/tarot/major-14.png'),
  ('major-15','major',NULL,15,'악마','The Devil','집착,유혹,욕망','해방,자각,끊어냄','놓지 못하는 습관이나 관계가 있어요. 무엇에 묶여 있는지 이름 붙여 보세요.','묶여 있던 것에서 벗어날 힘이 생겨요. 끊어내기 좋은 시기예요.','/assets/tarot/major-15.png'),
  ('major-16','major',NULL,16,'탑','The Tower','급변,붕괴,각성','여파,불안,버티기','예상 못 한 변화가 판을 바꿔요. 무너진 자리에서 진짜가 드러나요.','흔들림의 여파가 남아 있어요. 크게 움직이기보다 안전한 자리를 먼저 만드세요.','/assets/tarot/major-16.png'),
  ('major-17','major',NULL,17,'별','The Star','희망,치유,신뢰','실망,흐림,자신감저하','바라던 방향으로 작은 희망이 자라고 있어요. 조급해하지 않아도 괜찮아요.','기대가 옅어지고 있어요. 결과보다 지금 회복하는 데 마음을 써보세요.','/assets/tarot/major-17.png'),
  ('major-18','major',NULL,18,'달','The Moon','불안,직감,모호함','명료,해소,진실','감춰진 마음을 천천히 들여다볼 때예요. 지금 보이는 것이 전부는 아니에요.','흐릿하던 것이 조금씩 걷혀요. 오해가 풀리며 상황이 또렷해져요.','/assets/tarot/major-18.png'),
  ('major-19','major',NULL,19,'태양','The Sun','성공,활력,솔직함','지침,과열,자만','솔직한 선택이 좋은 흐름을 불러와요. 숨기지 않을수록 잘 풀리는 때예요.','밝게 보이려 애쓰다 지칠 수 있어요. 쉬어가도 빛은 사라지지 않아요.','/assets/tarot/major-19.png'),
  ('major-20','major',NULL,20,'심판','Judgement','결단,회복,부름','망설임,후회,외면','지나온 일을 매듭짓고 다시 부름을 받는 때예요. 결정을 내리기 좋아요.','과거를 계속 곱씹고 있어요. 스스로를 용서하는 데서 시작해 보세요.','/assets/tarot/major-20.png'),
  ('major-21','major',NULL,21,'세계','The World','완성,성취,확장','미완,답보,아쉬움','하나의 과정이 완성되고 다음 문이 열려요. 충분히 자랑스러워해도 좋아요.','거의 다 왔는데 마지막이 남아 있어요. 마무리에 조금만 더 힘을 실어보세요.','/assets/tarot/major-21.png')
ON DUPLICATE KEY UPDATE
  name_ko = VALUES(name_ko), name_en = VALUES(name_en),
  keyword_upright = VALUES(keyword_upright), keyword_reversed = VALUES(keyword_reversed),
  meaning_upright = VALUES(meaning_upright), meaning_reversed = VALUES(meaning_reversed),
  image_path = VALUES(image_path);
