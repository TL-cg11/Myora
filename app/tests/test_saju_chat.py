import unittest
from types import SimpleNamespace
from unittest.mock import patch

from fastapi import HTTPException

from app.routers import saju_chat as saju_chat_module
from app.routers.chat import ChatMessage, ChatRequest


class FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"choices": [{"message": {"content": self.content}}]}


class FakeAsyncClient:
    request = None
    response_content = "test answer"

    def __init__(self, **_kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def post(self, endpoint, headers, json):
        type(self).request = {"endpoint": endpoint, "headers": headers, "json": json}
        return FakeResponse(type(self).response_content)


def saju_request() -> ChatRequest:
    return ChatRequest(
        context="saju result",
        messages=[ChatMessage(role="user", content="What are my strengths?")],
    )


class SajuChatTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        FakeAsyncClient.response_content = "test answer"
        FakeAsyncClient.request = None

    async def test_saju_chat_disables_thinking_and_returns_answer(self) -> None:
        fake_settings = SimpleNamespace(
            deepseek_saju_api_key="secret-key",
            deepseek_saju_model="deepseek-v4-flash",
            deepseek_base_url="https://api.deepseek.com/",
        )
        with (
            patch.object(saju_chat_module, "settings", fake_settings),
            patch.object(saju_chat_module.httpx, "AsyncClient", FakeAsyncClient),
        ):
            response = await saju_chat_module.saju_chat(saju_request())

        self.assertEqual(response.answer, "test answer")
        self.assertEqual(FakeAsyncClient.request["json"]["thinking"], {"type": "disabled"})

    async def test_saju_chat_rejects_empty_deepseek_answer(self) -> None:
        FakeAsyncClient.response_content = "   "
        fake_settings = SimpleNamespace(
            deepseek_saju_api_key="secret-key",
            deepseek_saju_model="deepseek-v4-flash",
            deepseek_base_url="https://api.deepseek.com/",
        )
        with (
            patch.object(saju_chat_module, "settings", fake_settings),
            patch.object(saju_chat_module.httpx, "AsyncClient", FakeAsyncClient),
            self.assertRaises(HTTPException) as raised,
        ):
            await saju_chat_module.saju_chat(saju_request())

        self.assertEqual(raised.exception.status_code, 502)


if __name__ == "__main__":
    unittest.main()
