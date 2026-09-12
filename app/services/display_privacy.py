"""채팅 표시값을 Kafka 어댑터의 동일 문맥 모델로 검사한다."""

import logging

import httpx

from app.config import settings
from app.services.guardrail import redact

logger = logging.getLogger(__name__)


async def mask_display_text(text: str) -> str:
    """모델 서비스 장애 시 정규식으로 가리는 fail-closed 표시값을 반환한다."""
    fallback = redact(text)
    host = (
        f"[{settings.display_masking_host}]"
        if ":" in settings.display_masking_host
        else settings.display_masking_host
    )
    url = (
        f"http://{host}:"
        f"{settings.display_masking_port}/v1/mask"
    )
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json={"text": text})
            response.raise_for_status()
            value = response.json().get("display_text")
        if not isinstance(value, str) or len(value) > len(text) + 100:
            raise ValueError("invalid display masking response")
        return value
    except (httpx.HTTPError, ValueError, TypeError, KeyError) as error:
        logger.warning("display masking fallback: error=%s", type(error).__name__)
        return fallback
