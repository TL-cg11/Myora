import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.routers import chat as chat_module
from app.config import settings
from app.routers.chat import ChatMessage, ChatRequest, build_deepseek_messages


class FakeResponse:
    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": "  따뜻한 답변이에요.  "}}]}


class FakeAsyncClient:
    request = None

    def __init__(self, **_kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def post(self, endpoint, headers, json):
        type(self).request = {"endpoint": endpoint, "headers": headers, "json": json}
        return FakeResponse()


def face_request() -> ChatRequest:
    return ChatRequest(
        context="관상 결과: 부드러운 인상",
        messages=[ChatMessage(role="user", content="첫인상을 더 설명해줘")],
    )


class ChatPromptTests(unittest.TestCase):
    def test_face_prompt_contains_persona_and_result(self) -> None:
        messages = build_deepseek_messages(face_request())

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("관상 해설가", messages[0]["content"])
        self.assertIn("관상 결과: 부드러운 인상", messages[0]["content"])
        self.assertEqual(messages[-1]["content"], "첫인상을 더 설명해줘")

    def test_rejects_more_than_five_questions(self) -> None:
        limit = settings.chat_question_limit
        messages = [
            ChatMessage(role="user", content=f"질문 {index}")
            for index in range(1, limit + 2)
        ]
        with self.assertRaisesRegex(ValidationError, f"최대 {limit}회"):
            ChatRequest(context="관상 결과", messages=messages)


class ChatEndpointTests(unittest.IsolatedAsyncioTestCase):
    async def test_missing_api_key_returns_service_unavailable(self) -> None:
        fake_settings = SimpleNamespace(
            chat_question_limit=settings.chat_question_limit,
            deepseek_face_api_key="",
            deepseek_face_model="deepseek-v4-flash",
        )
        with patch.object(chat_module, "settings", fake_settings):
            with self.assertRaises(HTTPException) as raised:
                await chat_module.chat(face_request())

        self.assertEqual(raised.exception.status_code, 503)

    async def test_chat_calls_deepseek_without_exposing_key(self) -> None:
        fake_settings = SimpleNamespace(
            chat_question_limit=settings.chat_question_limit,
            deepseek_face_api_key="secret-key",
            deepseek_face_model="deepseek-v4-flash",
            deepseek_base_url="https://api.deepseek.com/",
        )
        with (
            patch.object(chat_module, "settings", fake_settings),
            patch.object(chat_module.httpx, "AsyncClient", FakeAsyncClient),
        ):
            response = await chat_module.chat(face_request())

        self.assertEqual(response.answer, "따뜻한 답변이에요.")
        self.assertEqual(
            FakeAsyncClient.request["endpoint"],
            "https://api.deepseek.com/chat/completions",
        )
        self.assertEqual(
            FakeAsyncClient.request["headers"]["Authorization"],
            "Bearer secret-key",
        )
        self.assertNotIn("secret-key", str(FakeAsyncClient.request["json"]))


if __name__ == "__main__":
    unittest.main()
