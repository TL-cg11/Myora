import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException

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
