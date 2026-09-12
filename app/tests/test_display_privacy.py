import unittest
from unittest.mock import AsyncMock, Mock, patch

import httpx

from app.services.display_privacy import mask_display_text


class DisplayPrivacyTests(unittest.IsolatedAsyncioTestCase):
    async def test_returns_context_model_result(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "display_text": "주문번호 010-1234-5678을 조회해줘"
        }
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.return_value = response

        with patch("app.services.display_privacy.httpx.AsyncClient", return_value=client):
            result = await mask_display_text("주문번호 010-1234-5678을 조회해줘")

        self.assertEqual(result, "주문번호 010-1234-5678을 조회해줘")

    async def test_service_failure_masks_identifiers(self):
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.side_effect = httpx.ConnectError("offline")

        with patch("app.services.display_privacy.httpx.AsyncClient", return_value=client):
            result = await mask_display_text("전화번호 010-1234-5678")

        self.assertNotIn("010-1234-5678", result)
