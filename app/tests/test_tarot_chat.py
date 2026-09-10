import unittest
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.models import ChatRole, Topic
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


def reading():
    return SimpleNamespace(
        id=1,
        topic=Topic.general,
        question=None,
        messages=[],
        cards=[],
        spread=SimpleNamespace(
            name_ko="한 장",
            description="현재 흐름",
            positions=[],
        ),
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
        self.assertNotIn("위험한 원문", " ".join(item.content for item in session.added))


if __name__ == "__main__":
    unittest.main()
