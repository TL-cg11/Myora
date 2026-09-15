import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from fastapi import HTTPException

from app.models import AppUser, AppUserRole, ChatRole, Topic
from app.config import settings
from app.routers import tarot_chat
from app.schemas import ChatCreate
from app.services.guardrail import SafeAnswer


class FakeSession:
    def __init__(self) -> None:
        self.added = []
        self.committed = False

    def add(self, message) -> None:
        if message.created_at is None:
            message.created_at = datetime.now(UTC).replace(tzinfo=None)
        self.added.append(message)

    def commit(self) -> None:
        self.committed = True


def reading(messages=None):
    return SimpleNamespace(
        id=1,
        topic=Topic.general,
        question=None,
        messages=messages if messages is not None else [],
        cards=[],
        spread=SimpleNamespace(
            name_ko="한 장",
            description="현재 흐름",
            positions=[],
        ),
    )


def user_message(seq):
    return SimpleNamespace(
        role=ChatRole.user, seq=seq, content="이전 질문", policy_version="1.1",
        created_at=datetime.now(UTC).replace(tzinfo=None),
    )


class TarotGuardrailTests(unittest.IsolatedAsyncioTestCase):
    async def test_tarot_uses_shared_guardrail_before_storage(self) -> None:
        current = reading()
        session = FakeSession()
        guarded = SafeAnswer("안전 안내", "[안전 검사로 저장하지 않은 질문]")

        with (
            patch.object(tarot_chat, "_load_reading", return_value=current),
            patch.object(tarot_chat, "safe_answer", AsyncMock(return_value=guarded)) as safe,
        ):
            response = await tarot_chat.create_chat_message(
                1,
                uuid4(),
                ChatCreate(message="위험한 원문"),
                session,
                None,
            )

        self.assertEqual(response.answer, "안전 안내")
        self.assertTrue(session.committed)
        self.assertEqual(safe.await_count, 1)
        self.assertEqual([item.role for item in session.added], [ChatRole.user, ChatRole.assistant])
        self.assertEqual(session.added[0].content, "위험한 원문")
        self.assertEqual(response.messages[0].content, "위험한 원문")


class TarotAdminQuestionLimitTests(unittest.IsolatedAsyncioTestCase):
    """공통 채팅과 같은 question_limit_for()를 쓰므로 관리자 한도도 그대로 적용된다."""

    async def test_admin_can_pass_the_common_limit(self) -> None:
        admin = AppUser(role=AppUserRole.admin)
        current = reading([user_message(i) for i in range(settings.chat_question_limit)])
        session = FakeSession()
        guarded = SafeAnswer("안전 안내", "질문", True)

        with (
            patch.object(tarot_chat, "_load_reading", return_value=current),
            patch.object(tarot_chat, "safe_answer", AsyncMock(return_value=guarded)) as safe,
        ):
            response = await tarot_chat.create_chat_message(
                1, uuid4(), ChatCreate(message="추가 질문"), session, admin,
            )

        self.assertEqual(response.answer, "안전 안내")
        safe.assert_awaited_once()

    async def test_regular_user_still_stops_at_the_common_limit(self) -> None:
        current = reading([user_message(i) for i in range(settings.chat_question_limit)])
        session = FakeSession()

        with (
            patch.object(tarot_chat, "_load_reading", return_value=current),
            patch.object(tarot_chat, "safe_answer", AsyncMock()) as safe,
        ):
            with self.assertRaises(HTTPException) as raised:
                await tarot_chat.create_chat_message(
                    1, uuid4(), ChatCreate(message="추가 질문"), session, None,
                )

        self.assertEqual(raised.exception.status_code, 429)
        safe.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
