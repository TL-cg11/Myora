-- 주제별 카드 해석 (연애/직업/금전/건강)
-- 적용: sudo mysql -uroot luck_db < sql/init/04_tarot_meaning_seed.sql
--
-- tarot_card 에 없는 주제는 카드의 기본 해석(meaning_upright/meaning_reversed)으로
-- 폴백한다(app/models.py TarotCard.meaning 참고). 이 파일은 메이저 22장에 대해
-- 4주제 x 2방향 = 176행을 채운다. 마이너 아르카나를 추가할 때도 형식은 같다.
--
-- card_id 는 AUTO_INCREMENT 값에 의존하지 않도록 code 조인으로 가져오고,
-- uk_tarot_card_meaning (card_id, topic, orientation) 기준으로 UPSERT 하므로
-- 몇 번을 다시 실행해도 안전하다.
--
-- 각 블록 첫 행의 CAST(... AS CHAR(500)) 은 UNION 결과 컬럼이 짧은 길이로
-- 잡혀 뒷 행이 잘리는 일을 막기 위한 안전장치다.

-- 연애운 ---------------------------------------------------------------------
INSERT INTO tarot_card_meaning (card_id, topic, orientation, meaning)
SELECT c.id, m.topic, m.orientation, m.meaning
FROM tarot_card c
JOIN (
  SELECT 'major-00' AS code,'love' AS topic,'upright' AS orientation,CAST('계산 없이 마음이 먼저 움직이는 시기예요. 재고 따지기보다 솔직하게 다가가도 괜찮아요.' AS CHAR(500)) AS meaning UNION ALL
  SELECT 'major-00','love','reversed','설렘만 믿고 서두르면 상처가 남아요. 상대의 속도도 한 번 확인해 보세요.' UNION ALL
  SELECT 'major-01','love','upright','마음을 표현할 방법이 이미 갖춰져 있어요. 먼저 연락하는 쪽이 흐름을 만들어요.' UNION ALL
  SELECT 'major-01','love','reversed','말은 많은데 진심이 흩어져 있어요. 보여주기보다 한 가지를 오래 지켜보세요.' UNION ALL
  SELECT 'major-02','love','upright','말하지 않아도 느껴지는 것이 있어요. 서두르지 말고 상대의 마음을 지켜봐 주세요.' UNION ALL
  SELECT 'major-02','love','reversed','짐작만 쌓이며 오해가 자라고 있어요. 확인하지 않은 마음은 물어보는 편이 나아요.' UNION ALL
  SELECT 'major-03','love','upright','마음을 넉넉히 주고받는 시기예요. 챙겨주는 만큼 관계가 깊어져요.' UNION ALL
  SELECT 'major-03','love','reversed','주기만 하다 스스로가 비어가고 있어요. 받는 것도 관계의 일부예요.' UNION ALL
  SELECT 'major-04','love','upright','관계에 든든한 기준이 생기는 시기예요. 약속을 지키는 모습이 신뢰를 키워요.' UNION ALL
  SELECT 'major-04','love','reversed','내 방식만 고집하면 상대가 숨 막혀요. 규칙보다 마음을 먼저 물어보세요.' UNION ALL
  SELECT 'major-05','love','upright','믿을 만한 사람의 조언이 도움이 되는 시기예요. 관계를 차분히 이어가기 좋아요.' UNION ALL
  SELECT 'major-05','love','reversed','남들의 기준에 관계를 맞추고 있어요. 두 사람에게 맞는 방식을 찾아도 괜찮아요.' UNION ALL
  SELECT 'major-06','love','upright','마음이 향하는 곳이 분명해지는 시기예요. 진심을 전하면 관계가 한 걸음 나아가요.' UNION ALL
  SELECT 'major-06','love','reversed','결정을 미루는 동안 서로가 지쳐요. 무엇을 원하는지 먼저 정리해 보세요.' UNION ALL
  SELECT 'major-07','love','upright','망설이던 마음을 밀고 나가기 좋은 때예요. 먼저 다가가면 흐름이 열려요.' UNION ALL
  SELECT 'major-07','love','reversed','밀어붙이는 속도가 상대에게 부담이 돼요. 잠시 멈춰 보폭을 맞춰 보세요.' UNION ALL
  SELECT 'major-08','love','upright','다그치지 않는 다정함이 상대를 움직여요. 천천히 곁을 지켜 주세요.' UNION ALL
  SELECT 'major-08','love','reversed','참기만 하다 마음이 소진되고 있어요. 힘든 부분은 말해도 괜찮아요.' UNION ALL
  SELECT 'major-09','love','upright','혼자 정리하는 시간이 관계에 도움이 돼요. 내 마음부터 분명히 해 보세요.' UNION ALL
  SELECT 'major-09','love','reversed','너무 오래 마음을 닫아 두었어요. 한 사람에게라도 문을 열어 보세요.' UNION ALL
  SELECT 'major-10','love','upright','뜻밖의 만남이나 재회가 찾아올 수 있어요. 흐름에 마음을 맡겨도 좋아요.' UNION ALL
  SELECT 'major-10','love','reversed','같은 문제가 반복되고 있어요. 패턴을 바꾸지 않으면 결과도 그대로예요.' UNION ALL
  SELECT 'major-11','love','upright','서로의 몫이 공평해지는 시기예요. 솔직하게 이야기하면 균형이 잡혀요.' UNION ALL
  SELECT 'major-11','love','reversed','한쪽만 애쓰는 관계가 이어지고 있어요. 기울어진 부분을 말할 때예요.' UNION ALL
  SELECT 'major-12','love','upright','지금은 밀어붙이기보다 기다릴 때예요. 상대의 자리에서 한번 바라봐 주세요.' UNION ALL
  SELECT 'major-12','love','reversed','혼자 희생하며 버티고 있어요. 참는 것만이 사랑은 아니에요.' UNION ALL
  SELECT 'major-13','love','upright','한 관계의 형태가 바뀌는 시기예요. 정리하면 오히려 마음이 가벼워져요.' UNION ALL
  SELECT 'major-13','love','reversed','끝난 마음을 붙잡고 있어요. 아쉬움을 인정하면 다음이 보이기 시작해요.' UNION ALL
  SELECT 'major-14','love','upright','서로의 속도를 맞춰가는 시기예요. 무리하지 않는 만큼 오래 가요.' UNION ALL
  SELECT 'major-14','love','reversed','한쪽으로 치우쳐 지치고 있어요. 기대를 조금 덜어내 보세요.' UNION ALL
  SELECT 'major-15','love','upright','놓지 못하는 마음이 스스로를 묶고 있어요. 무엇에 끌리는지 솔직히 봐 주세요.' UNION ALL
  SELECT 'major-15','love','reversed','붙잡고 있던 관계에서 벗어날 힘이 생겨요. 끊어내기 좋은 시기예요.' UNION ALL
  SELECT 'major-16','love','upright','예상 못 한 일이 관계를 흔들 수 있어요. 무너진 자리에서 진심이 드러나요.' UNION ALL
  SELECT 'major-16','love','reversed','지나간 충격의 여파가 남아 있어요. 서둘러 결론 내리지 않아도 괜찮아요.' UNION ALL
  SELECT 'major-17','love','upright','상처가 아물며 마음이 열리는 시기예요. 기대해도 괜찮은 흐름이에요.' UNION ALL
  SELECT 'major-17','love','reversed','기대가 옅어져 마음이 식고 있어요. 결과보다 지금의 회복에 마음을 써 보세요.' UNION ALL
  SELECT 'major-18','love','upright','확실하지 않은 마음이 오가고 있어요. 지금 보이는 것이 전부는 아니에요.' UNION ALL
  SELECT 'major-18','love','reversed','흐릿하던 오해가 풀리는 시기예요. 이야기를 나누면 또렷해져요.' UNION ALL
  SELECT 'major-19','love','upright','솔직할수록 잘 풀리는 시기예요. 마음을 감추지 않아도 괜찮아요.' UNION ALL
  SELECT 'major-19','love','reversed','밝은 모습만 보이려다 지치고 있어요. 힘든 날은 힘들다고 말해도 돼요.' UNION ALL
  SELECT 'major-20','love','upright','미뤄둔 이야기를 매듭지을 때예요. 결정을 내리면 관계가 정리돼요.' UNION ALL
  SELECT 'major-20','love','reversed','지난 일을 계속 곱씹고 있어요. 스스로를 용서하는 데서 시작해 보세요.' UNION ALL
  SELECT 'major-21','love','upright','관계가 한 단계 완성되는 시기예요. 함께 다음을 이야기해도 좋아요.' UNION ALL
  SELECT 'major-21','love','reversed','거의 다 왔는데 마지막이 남아 있어요. 아쉬운 부분을 말로 꺼내 보세요.'
) m ON m.code = c.code
ON DUPLICATE KEY UPDATE meaning = VALUES(meaning);

-- 직업운 ---------------------------------------------------------------------
INSERT INTO tarot_card_meaning (card_id, topic, orientation, meaning)
SELECT c.id, m.topic, m.orientation, m.meaning
FROM tarot_card c
JOIN (
  SELECT 'major-00' AS code,'career' AS topic,'upright' AS orientation,CAST('해보지 않은 일에 손을 얹기 좋은 때예요. 경험이 부족해도 배우면서 갈 수 있어요.' AS CHAR(500)) AS meaning UNION ALL
  SELECT 'major-00','career','reversed','준비 없이 뛰어들면 중간에 지쳐요. 시작 전에 필요한 것부터 챙겨 보세요.' UNION ALL
  SELECT 'major-01','career','upright','가진 재능을 결과로 바꿀 수 있는 때예요. 미루던 일을 직접 착수해 보세요.' UNION ALL
  SELECT 'major-01','career','reversed','벌여 놓은 일이 많아 어느 것도 끝나지 않아요. 하나를 골라 마무리부터 하세요.' UNION ALL
  SELECT 'major-02','career','upright','드러난 조건보다 분위기를 읽어야 할 때예요. 조용히 관찰한 정보가 힘이 돼요.' UNION ALL
  SELECT 'major-02','career','reversed','정보가 부족한 채로 판단하고 있어요. 아는 척보다 모른다고 말하는 편이 안전해요.' UNION ALL
  SELECT 'major-03','career','upright','공들인 일이 눈에 보이는 성과로 돌아와요. 지금의 방식을 이어가도 좋아요.' UNION ALL
  SELECT 'major-03','career','reversed','한 사람에게 기대는 구조는 오래 못 가요. 스스로 할 수 있는 몫을 늘려 보세요.' UNION ALL
  SELECT 'major-04','career','upright','체계를 잡으면 성과가 따라와요. 미뤄둔 규칙과 역할을 정리하기 좋아요.' UNION ALL
  SELECT 'major-04','career','reversed','통제하려 할수록 팀이 굳어져요. 맡기는 연습이 필요한 시기예요.' UNION ALL
  SELECT 'major-05','career','upright','먼저 걸어본 사람에게 배우면 빨라져요. 조언을 구하는 것이 지름길이에요.' UNION ALL
  SELECT 'major-05','career','reversed','늘 하던 방식이 더는 맞지 않아요. 관행을 한 번 의심해 볼 때예요.' UNION ALL
  SELECT 'major-06','career','upright','두 갈래 중 하나를 고를 때가 왔어요. 조건보다 오래 하고 싶은 쪽을 보세요.' UNION ALL
  SELECT 'major-06','career','reversed','애매한 태도가 신뢰를 깎고 있어요. 하겠다 못 하겠다를 분명히 말할 때예요.' UNION ALL
  SELECT 'major-07','career','upright','목표를 향해 속도를 낼 수 있는 구간이에요. 지금의 추진력을 아끼지 마세요.' UNION ALL
  SELECT 'major-07','career','reversed','바쁘기만 하고 진척이 없어요. 방향이 맞는지부터 다시 확인하세요.' UNION ALL
  SELECT 'major-08','career','upright','버티는 힘이 곧 실력이 되는 시기예요. 서두르지 않아도 인정받아요.' UNION ALL
  SELECT 'major-08','career','reversed','인내가 바닥나 예민해져 있어요. 잠시 거리를 두면 다시 힘이 생겨요.' UNION ALL
  SELECT 'major-09','career','upright','방해 없이 집중할 때 결과가 나와요. 혼자만의 시간을 확보해 보세요.' UNION ALL
  SELECT 'major-09','career','reversed','혼자 끌어안고 있어 진도가 나가지 않아요. 도움을 청하는 것도 능력이에요.' UNION ALL
  SELECT 'major-10','career','upright','기회가 먼저 찾아오는 시기예요. 준비된 만큼 잡을 수 있어요.' UNION ALL
  SELECT 'major-10','career','reversed','일정이 자꾸 밀려도 조급해하지 마세요. 아직 때가 아닐 뿐이에요.' UNION ALL
  SELECT 'major-11','career','upright','정당한 평가를 받을 수 있는 때예요. 근거를 갖춰 요구해도 좋아요.' UNION ALL
  SELECT 'major-11','career','reversed','책임을 미루다 신뢰를 잃기 쉬워요. 내 몫부터 분명히 하세요.' UNION ALL
  SELECT 'major-12','career','upright','잠시 멈춰 관점을 바꾸면 길이 보여요. 다른 방식도 생각해 보세요.' UNION ALL
  SELECT 'major-12','career','reversed','답답한 상황이 길어지고 있어요. 놓아도 되는 일을 골라내 보세요.' UNION ALL
  SELECT 'major-13','career','upright','마무리 짓기 좋은 때예요. 맞지 않는 일을 놓으면 새 자리가 생겨요.' UNION ALL
  SELECT 'major-13','career','reversed','그만둘 결심을 미루며 지쳐가요. 두려움의 정체를 적어 보세요.' UNION ALL
  SELECT 'major-14','career','upright','여러 일을 알맞게 배분하기 좋은 때예요. 속도를 고르면 성과가 이어져요.' UNION ALL
  SELECT 'major-14','career','reversed','욕심이 앞서 일이 넘치고 있어요. 덜어내는 결정이 필요해요.' UNION ALL
  SELECT 'major-15','career','upright','조건에 매여 하기 싫은 일을 이어가고 있어요. 무엇 때문인지 이름 붙여 보세요.' UNION ALL
  SELECT 'major-15','career','reversed','오래 참던 자리에서 나올 용기가 생겨요. 결정하고 나면 생각보다 가벼워요.' UNION ALL
  SELECT 'major-16','career','upright','갑작스러운 변화가 판을 바꿔요. 흔들려도 방향은 오히려 분명해져요.' UNION ALL
  SELECT 'major-16','career','reversed','불안한 상황을 버티는 중이에요. 크게 움직이기보다 안전한 자리를 먼저 만드세요.' UNION ALL
  SELECT 'major-17','career','upright','바라던 방향으로 길이 열리기 시작해요. 조급해하지 않아도 닿아요.' UNION ALL
  SELECT 'major-17','career','reversed','자신감이 떨어져 움츠러들어 있어요. 잘해온 것부터 하나씩 세어 보세요.' UNION ALL
  SELECT 'major-18','career','upright','정보가 분명하지 않아 판단이 어려워요. 큰 결정은 조금 미뤄도 좋아요.' UNION ALL
  SELECT 'major-18','career','reversed','감춰졌던 사정이 드러나며 정리돼요. 이제 방향을 정해도 괜찮아요.' UNION ALL
  SELECT 'major-19','career','upright','노력이 눈에 띄고 인정받는 때예요. 자신 있게 드러내도 좋아요.' UNION ALL
  SELECT 'major-19','career','reversed','자신감이 지나쳐 주변이 멀어질 수 있어요. 한 번씩 눈높이를 낮춰 보세요.' UNION ALL
  SELECT 'major-20','career','upright','다시 부름을 받는 시기예요. 미뤄둔 지원이나 제안에 응답해 보세요.' UNION ALL
  SELECT 'major-20','career','reversed','망설이는 사이 기회가 지나가요. 완벽하지 않아도 답을 주세요.' UNION ALL
  SELECT 'major-21','career','upright','맡았던 일이 제대로 마무리되는 시기예요. 성과를 정리해 다음 자리로 가져가세요.' UNION ALL
  SELECT 'major-21','career','reversed','마무리가 미뤄지며 힘이 빠져요. 남은 일을 목록으로 만들어 보세요.'
) m ON m.code = c.code
ON DUPLICATE KEY UPDATE meaning = VALUES(meaning);

-- 금전운 ---------------------------------------------------------------------
INSERT INTO tarot_card_meaning (card_id, topic, orientation, meaning)
SELECT c.id, m.topic, m.orientation, m.meaning
FROM tarot_card c
JOIN (
  SELECT 'major-00' AS code,'money' AS topic,'upright' AS orientation,CAST('새로운 방식으로 돈을 굴려볼 만한 시기예요. 작은 규모로 먼저 시험해 보세요.' AS CHAR(500)) AS meaning UNION ALL
  SELECT 'major-00','money','reversed','즉흥적인 지출이 늘어나 있어요. 결제 전에 하루만 미뤄 보세요.' UNION ALL
  SELECT 'major-01','money','upright','수입을 만들 방법이 손안에 있어요. 아이디어를 실행으로 옮길 시점이에요.' UNION ALL
  SELECT 'major-01','money','reversed','자신을 과신한 결정이 위험해요. 숫자로 확인되지 않은 이야기는 걸러내세요.' UNION ALL
  SELECT 'major-02','money','upright','드러난 수익보다 숨은 조건을 봐야 해요. 계약서의 작은 글씨를 확인하세요.' UNION ALL
  SELECT 'major-02','money','reversed','확실하지 않은 정보에 돈이 묶일 수 있어요. 출처가 불분명한 제안은 미루세요.' UNION ALL
  SELECT 'major-03','money','upright','들어오는 흐름이 안정되는 시기예요. 나를 위해 쓰는 돈도 아깝지 않아요.' UNION ALL
  SELECT 'major-03','money','reversed','정을 못 이겨 나가는 돈이 많아요. 마음과 지갑은 나눠서 생각해 보세요.' UNION ALL
  SELECT 'major-04','money','upright','예산과 원칙을 세우면 돈이 안정돼요. 고정 지출부터 정리해 보세요.' UNION ALL
  SELECT 'major-04','money','reversed','지나친 통제가 기회를 놓치게 해요. 안전만 좇다 흐름을 놓치지 않도록 하세요.' UNION ALL
  SELECT 'major-05','money','upright','검증된 방법이 안전한 시기예요. 유행보다 기본을 지키는 쪽이 좋아요.' UNION ALL
  SELECT 'major-05','money','reversed','남을 따라 한 결정이 손해로 이어질 수 있어요. 내 상황에 맞는 기준을 세우세요.' UNION ALL
  SELECT 'major-06','money','upright','함께 내리는 결정이 좋은 결과를 만들어요. 상의하고 움직이면 든든해요.' UNION ALL
  SELECT 'major-06','money','reversed','돈 문제로 마음이 어긋나기 쉬워요. 금액과 몫을 미리 말로 정해 두세요.' UNION ALL
  SELECT 'major-07','money','upright','계획한 대로 밀고 가면 목표액에 닿아요. 흔들리지 말고 유지하세요.' UNION ALL
  SELECT 'major-07','money','reversed','조급한 결정이 손실을 부를 수 있어요. 남의 속도에 따라가지 마세요.' UNION ALL
  SELECT 'major-08','money','upright','꾸준히 모으는 방식이 가장 확실해요. 작은 금액도 이어가면 커져요.' UNION ALL
  SELECT 'major-08','money','reversed','참다가 한 번에 크게 쓰기 쉬워요. 무리한 절약 대신 여유를 조금 두세요.' UNION ALL
  SELECT 'major-09','money','upright','조용히 점검하기 좋은 시기예요. 지출 내역을 처음부터 살펴보세요.' UNION ALL
  SELECT 'major-09','money','reversed','혼자 판단하다 놓치는 것이 생겨요. 아는 사람에게 한 번 물어보세요.' UNION ALL
  SELECT 'major-10','money','upright','흐름이 좋은 쪽으로 도는 때예요. 타이밍을 놓치지 않는 것이 중요해요.' UNION ALL
  SELECT 'major-10','money','reversed','들어왔다 나가기를 반복하고 있어요. 큰 결정은 잠시 미루세요.' UNION ALL
  SELECT 'major-11','money','upright','계산이 맞아떨어지는 시기예요. 미뤄둔 정산을 마무리하기 좋아요.' UNION ALL
  SELECT 'major-11','money','reversed','감정으로 내린 금전 결정이 부담이 돼요. 숫자를 다시 확인해 보세요.' UNION ALL
  SELECT 'major-12','money','upright','지금은 묶어두는 편이 나은 시기예요. 서둘러 움직이지 않아도 괜찮아요.' UNION ALL
  SELECT 'major-12','money','reversed','묶인 돈이 오래 잠겨 부담이 돼요. 손실을 인정하고 정리할 용기도 필요해요.' UNION ALL
  SELECT 'major-13','money','upright','오래된 지출과 계약을 끊어낼 시기예요. 정리하는 만큼 여유가 생겨요.' UNION ALL
  SELECT 'major-13','money','reversed','손실을 인정하지 못해 더 커지고 있어요. 지금 멈추는 것도 방법이에요.' UNION ALL
  SELECT 'major-14','money','upright','쓰는 것과 모으는 것의 균형이 잡혀요. 지금의 비율을 유지하세요.' UNION ALL
  SELECT 'major-14','money','reversed','극단적인 절약과 지출이 번갈아 반복돼요. 중간 지점을 정해 보세요.' UNION ALL
  SELECT 'major-15','money','upright','소비 습관이 나를 끌고 가고 있어요. 자동 결제부터 확인해 보세요.' UNION ALL
  SELECT 'major-15','money','reversed','끊고 싶던 지출을 정리할 수 있어요. 지금 시작하면 잘 이어져요.' UNION ALL
  SELECT 'major-16','money','upright','예상 밖의 지출이 생길 수 있어요. 비상금을 확인해 두세요.' UNION ALL
  SELECT 'major-16','money','reversed','손실 뒤의 불안이 판단을 흐려요. 회복을 서두르다 더 잃지 않도록 하세요.' UNION ALL
  SELECT 'major-17','money','upright','상황이 서서히 나아지는 시기예요. 길게 보는 계획이 잘 맞아요.' UNION ALL
  SELECT 'major-17','money','reversed','막연한 기대에 기대고 있어요. 숫자로 확인한 계획이 필요해요.' UNION ALL
  SELECT 'major-18','money','upright','조건이 명확하지 않은 제안이 있어요. 확인하기 전에는 움직이지 마세요.' UNION ALL
  SELECT 'major-18','money','reversed','불투명하던 부분이 밝혀져요. 정리하고 나면 마음이 놓여요.' UNION ALL
  SELECT 'major-19','money','upright','수입이 늘고 흐름이 밝아져요. 성과를 누려도 괜찮은 시기예요.' UNION ALL
  SELECT 'major-19','money','reversed','좋을 때의 씀씀이가 그대로 남아 있어요. 지금 규모에 맞춰 다시 잡아 보세요.' UNION ALL
  SELECT 'major-20','money','upright','흐트러진 재정을 정리하기 좋은 때예요. 결산하고 나면 길이 보여요.' UNION ALL
  SELECT 'major-20','money','reversed','지난 결정에 대한 후회가 발목을 잡아요. 지금부터의 계획을 세우세요.' UNION ALL
  SELECT 'major-21','money','upright','목표한 금액에 닿는 시기예요. 다음 계획을 세우기 좋아요.' UNION ALL
  SELECT 'major-21','money','reversed','결실을 눈앞에 두고 정체돼 있어요. 마무리에 조금만 더 힘을 실어 보세요.'
) m ON m.code = c.code
ON DUPLICATE KEY UPDATE meaning = VALUES(meaning);

-- 건강운 ---------------------------------------------------------------------
INSERT INTO tarot_card_meaning (card_id, topic, orientation, meaning)
SELECT c.id, m.topic, m.orientation, m.meaning
FROM tarot_card c
JOIN (
  SELECT 'major-00' AS code,'health' AS topic,'upright' AS orientation,CAST('몸을 새로 움직이기 좋은 출발선이에요. 가볍게 시작하는 쪽이 오래 가요.' AS CHAR(500)) AS meaning UNION ALL
  SELECT 'major-00','health','reversed','무리한 도전이 탈을 부를 수 있어요. 몸이 보내는 신호를 흘려듣지 마세요.' UNION ALL
  SELECT 'major-01','health','upright','마음먹은 대로 몸이 따라와 주는 시기예요. 계획한 운동을 오늘 시작해 보세요.' UNION ALL
  SELECT 'major-01','health','reversed','이것저것 손대다 아무것도 꾸준하지 않아요. 습관 하나만 남겨 보세요.' UNION ALL
  SELECT 'major-02','health','upright','몸이 조용히 보내는 신호에 답이 있어요. 무리하지 말고 쉬는 시간을 늘려 보세요.' UNION ALL
  SELECT 'major-02','health','reversed','이상 신호를 애써 못 본 척하고 있어요. 미뤄둔 검진을 잡아 두면 마음이 놓여요.' UNION ALL
  SELECT 'major-03','health','upright','잘 먹고 잘 쉬는 것만으로 회복되는 때예요. 몸을 넉넉히 돌봐 주세요.' UNION ALL
  SELECT 'major-03','health','reversed','남을 돌보느라 내 몸이 뒷전이에요. 오늘 하루는 나를 먼저 챙기세요.' UNION ALL
  SELECT 'major-04','health','upright','규칙적인 생활이 몸을 다시 세워 줘요. 자는 시간부터 고정해 보세요.' UNION ALL
  SELECT 'major-04','health','reversed','몸을 의지로만 밀어붙이고 있어요. 쉬는 것도 관리의 일부예요.' UNION ALL
  SELECT 'major-05','health','upright','전문가의 말을 따르면 회복이 빨라져요. 혼자 판단하기보다 진료를 권해요.' UNION ALL
  SELECT 'major-05','health','reversed','떠도는 정보에 몸을 맡기고 있어요. 제대로 된 곳에서 한 번 확인해 보세요.' UNION ALL
  SELECT 'major-06','health','upright','몸과 마음의 균형이 맞아 가는 때예요. 좋아하는 사람과의 시간이 약이 돼요.' UNION ALL
  SELECT 'major-06','health','reversed','마음의 갈등이 몸으로 나타나고 있어요. 미뤄둔 감정을 꺼내 놓아 보세요.' UNION ALL
  SELECT 'major-07','health','upright','몸에 힘이 붙는 시기예요. 강도를 조금 올려도 잘 따라와 줘요.' UNION ALL
  SELECT 'major-07','health','reversed','의지로만 버티다 탈이 날 수 있어요. 쉬어가는 날을 일정에 넣으세요.' UNION ALL
  SELECT 'major-08','health','upright','부드러운 꾸준함이 몸을 바꿔요. 센 운동보다 매일 하는 쪽이 좋아요.' UNION ALL
  SELECT 'major-08','health','reversed','기운이 떨어져 회복이 더뎌요. 무리하지 말고 잘 자는 것부터 챙기세요.' UNION ALL
  SELECT 'major-09','health','upright','쉬는 시간이 가장 좋은 처방이에요. 혼자 회복하는 시간을 가져 보세요.' UNION ALL
  SELECT 'major-09','health','reversed','외로움이 몸의 기운까지 끌어내려요. 밖으로 한 걸음 나가 보세요.' UNION ALL
  SELECT 'major-10','health','upright','컨디션이 회복 국면으로 접어들어요. 좋은 습관을 이때 붙여 두세요.' UNION ALL
  SELECT 'major-10','health','reversed','나았다 다시 나빠지기를 반복해요. 원인을 근본부터 찾아볼 때예요.' UNION ALL
  SELECT 'major-11','health','upright','생활의 균형이 몸을 회복시켜요. 일과 휴식의 비율을 맞춰 보세요.' UNION ALL
  SELECT 'major-11','health','reversed','한쪽으로 치우친 생활이 신호를 보내요. 미뤄둔 관리를 시작하세요.' UNION ALL
  SELECT 'major-12','health','upright','쉬는 것이 곧 치료예요. 멈춤을 스스로에게 허락해 주세요.' UNION ALL
  SELECT 'major-12','health','reversed','참고 미룬 피로가 쌓여 있어요. 억지로 버티는 일을 하나 줄이세요.' UNION ALL
  SELECT 'major-13','health','upright','나쁜 습관 하나를 끊기 좋은 때예요. 바꾸면 몸이 먼저 알아차려요.' UNION ALL
  SELECT 'major-13','health','reversed','변화를 미루는 동안 부담이 쌓여요. 작은 것부터 하나만 바꿔 보세요.' UNION ALL
  SELECT 'major-14','health','upright','회복이 순조롭게 이어지는 시기예요. 규칙적인 식사가 큰 힘이 돼요.' UNION ALL
  SELECT 'major-14','health','reversed','조바심이 몸을 더 지치게 해요. 결과를 재촉하지 마세요.' UNION ALL
  SELECT 'major-15','health','upright','몸에 해로운 습관이 굳어가고 있어요. 하루만 멈춰 보는 것부터 해보세요.' UNION ALL
  SELECT 'major-15','health','reversed','나쁜 습관을 끊어낼 힘이 돌아와요. 도움을 받으면 더 수월해요.' UNION ALL
  SELECT 'major-16','health','upright','갑작스러운 신호를 무시하지 마세요. 이상하다 싶으면 바로 확인하는 게 좋아요.' UNION ALL
  SELECT 'major-16','health','reversed','무리한 뒤의 여파가 남아 있어요. 회복 기간을 넉넉히 잡으세요.' UNION ALL
  SELECT 'major-17','health','upright','회복이 순조롭게 이어져요. 몸도 마음도 편안해지는 시기예요.' UNION ALL
  SELECT 'major-17','health','reversed','지친 마음이 몸까지 끌어내려요. 쉬면서 기운을 채워 주세요.' UNION ALL
  SELECT 'major-18','health','upright','원인을 알기 어려운 피로가 있어요. 잠과 스트레스를 먼저 살펴보세요.' UNION ALL
  SELECT 'major-18','health','reversed','답답하던 증상의 이유가 밝혀져요. 이제 관리 방향을 잡을 수 있어요.' UNION ALL
  SELECT 'major-19','health','upright','활력이 돌아오는 시기예요. 햇빛과 바깥 활동이 특히 좋아요.' UNION ALL
  SELECT 'major-19','health','reversed','과열된 일정이 몸을 태우고 있어요. 쉬어가도 빛은 사라지지 않아요.' UNION ALL
  SELECT 'major-20','health','upright','회복의 전환점을 맞는 시기예요. 관리하던 것을 다시 시작해 보세요.' UNION ALL
  SELECT 'major-20','health','reversed','알면서 미뤄둔 일이 있어요. 외면할수록 부담만 커져요.' UNION ALL
  SELECT 'major-21','health','upright','관리해온 것이 몸으로 나타나요. 지금의 습관을 그대로 이어가세요.' UNION ALL
  SELECT 'major-21','health','reversed','회복이 마지막에서 더뎌요. 조바심 대신 시간을 조금 더 주세요.'
) m ON m.code = c.code
ON DUPLICATE KEY UPDATE meaning = VALUES(meaning);
