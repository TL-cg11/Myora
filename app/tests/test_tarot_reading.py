import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from app.routers import tarot
from app.schemas import ReadingCreate


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
