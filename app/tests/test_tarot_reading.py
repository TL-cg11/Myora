import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models import Arcana, Base, TarotCard, TarotSpread, TarotSpreadPosition, Topic
from app.prompts.guardrail import POLICY_VERSION
from app.routers import tarot
from app.schemas import ReadingCreate
from app.services.guardrail import InputDecision


def decision(verdict, rules=(), crisis_kind='none'):
    return InputDecision(decision=verdict, rules=list(rules), crisis_kind=crisis_kind)


class TarotQuestionScreeningTests(unittest.TestCase):
    """최초 질문은 검사 없이 저장되면 되돌릴 수 없으므로 저장 전에 거른다."""

    def request(self, question):
        return ReadingCreate(spread_code='one', guest_key=uuid4(), topic='general', question=question)

    def test_direct_identifier_is_rejected_before_any_lookup(self):
        for question in ('연락처는 010-1234-5678이에요', 'a@b.com으로 알려주세요',
                         '주민번호 900101-1234567', 'https://example.com/me 참고'):
            with patch.object(tarot, 'get_spread') as lookup:
                with self.assertRaises(HTTPException) as raised:
                    tarot.create_reading(self.request(question), None, None)
            self.assertEqual(raised.exception.status_code, 400)
            self.assertNotIn(question, raised.exception.detail)
            lookup.assert_not_called()

    def test_ordinary_question_passes_screening(self):
        with patch.object(tarot, 'get_spread', return_value=None) as lookup:
            with self.assertRaises(HTTPException) as raised:
                tarot.create_reading(self.request('지금 이 일을 계속 해도 될까요?'), None, None)
        self.assertEqual(raised.exception.status_code, 404)
        lookup.assert_called_once()

    def test_empty_question_is_allowed(self):
        with patch.object(tarot, 'get_spread', return_value=None):
            with self.assertRaises(HTTPException) as raised:
                tarot.create_reading(self.request(None), None, None)
        self.assertEqual(raised.exception.status_code, 404)


if __name__ == '__main__':
    unittest.main()


class QuestionScreenEndpointTests(unittest.IsolatedAsyncioTestCase):
    """카드를 뽑기 전에 최초 질문을 의미 검사까지 통과시킨다."""

    def payload(self, question):
        from app.schemas import QuestionCheck
        return QuestionCheck(question=question)

    async def screen(self, verdict):
        with patch.object(tarot, 'screen_question', AsyncMock(return_value=verdict)) as call:
            return await tarot.check_question(self.payload('니 이름 뭐야?')), call

    async def test_allow_passes_without_blocking(self):
        response, call = await self.screen(decision('allow'))
        self.assertEqual(response.status_code, 204)
        self.assertEqual(call.await_count, 1)

    async def test_out_of_scope_does_not_block_card_draw(self):
        # 카드도 이력도 없는 시점이라 '결과와 무관한가'는 판단 근거가 없다.
        response, _ = await self.screen(decision('out_of_scope', ['G01']))
        self.assertEqual(response.status_code, 204)

    async def test_restrict_and_crisis_stop_before_drawing(self):
        for verdict, expected in (
            (decision('restrict', ['G03']), tarot.RESTRICT),
            (decision('crisis', ['G07'], 'self_harm'), tarot.CRISIS['self_harm']),
        ):
            with patch.object(tarot, 'screen_question', AsyncMock(return_value=verdict)):
                with self.assertRaises(HTTPException) as raised:
                    await tarot.check_question(self.payload('위험한 질문'))
            self.assertEqual(raised.exception.status_code, 400)
            self.assertEqual(raised.exception.detail, expected)

    async def test_screening_failure_is_not_silently_allowed(self):
        with patch.object(tarot, 'screen_question', AsyncMock(return_value=None)):
            with self.assertRaises(HTTPException) as raised:
                await tarot.check_question(self.payload('평범한 질문'))
        self.assertEqual(raised.exception.status_code, 503)

    async def test_identifier_is_rejected_without_calling_model(self):
        with patch.object(tarot, 'screen_question', AsyncMock()) as call:
            with self.assertRaises(HTTPException) as raised:
                await tarot.check_question(self.payload('연락처 010-1234-5678'))
        self.assertEqual(raised.exception.status_code, 400)
        call.assert_not_awaited()


class DrawReadingGreetingTests(unittest.TestCase):
    """카드를 뽑을 때 자동으로 넣는 첫 인사가 policy_version 없이 저장되면
    상세 조회(_to_reading_out)와 대화 다시보기(get_user_conversation) 양쪽에서
    조용히 사라진다. 지금까지 그래서 프런트가 하드코딩 기본값으로 땜질해 왔다."""

    def setUp(self):
        self.engine = create_engine('sqlite://')
        Base.metadata.create_all(self.engine)
        self.session = Session(self.engine)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.session.close)

        spread = TarotSpread(id=1, code='one', name_ko='한 장', description='현재 흐름', card_count=1)
        self.session.add(spread)
        self.session.add(TarotSpreadPosition(id=1, spread_id=1, position_no=1, label_ko='오늘'))
        self.session.add(TarotCard(
            id=1, code='fool', arcana=Arcana.major, number=0,
            name_ko='바보', name_en='The Fool',
            keyword_upright='시작', keyword_reversed='경솔',
            meaning_upright='새로운 시작', meaning_reversed='성급한 판단',
        ))
        self.session.commit()
        self.spread = spread

    def test_greeting_carries_the_current_policy_version(self) -> None:
        reading = tarot.draw_reading(
            self.session, spread=self.spread, guest_key=str(uuid4()),
            user_id=None, topic=Topic.general, question=None,
        )
        greeting = next(m for m in reading.messages if m.seq == 1)
        self.assertEqual(greeting.policy_version, POLICY_VERSION)

    def test_reading_detail_no_longer_drops_the_greeting(self) -> None:
        reading = tarot.draw_reading(
            self.session, spread=self.spread, guest_key=str(uuid4()),
            user_id=None, topic=Topic.general, question=None,
        )
        out = tarot._to_reading_out(reading)
        self.assertEqual(len(out.messages), 1)
        self.assertIn('결과를 함께 보고 있어요', out.messages[0].content)
