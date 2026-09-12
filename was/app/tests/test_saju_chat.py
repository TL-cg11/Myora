import unittest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from app.routers.saju_chat import saju_chat
from app.routers.chat import ChatRequest, ChatResponse

class SajuChatTests(unittest.IsolatedAsyncioTestCase):
    async def test_uses_shared_pipeline(self):
        request = ChatRequest(reading_id=1, guest_key=uuid4(),message='용신 뜻')
        with patch('app.routers.saju_chat.reading_chat', AsyncMock(return_value=ChatResponse(answer='설명',questions_used=1))) as call:
            result = await saju_chat(request, 'session', None)
        self.assertEqual(result.answer,'설명')
        self.assertEqual(call.await_args.args[0],'saju')
