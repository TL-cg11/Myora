"""DeepSeek 호출.

OpenAI 호환 형식이라 /chat/completions 에 그대로 POST 한다. SDK 를 붙이지 않은 건
쓰는 기능이 이것 하나뿐이고, 의존성을 늘리면 배포 스크립트도 같이 손봐야 해서다.

이 모듈은 실패를 삼키지 않고 LlmUnavailable 로 올린다. 무엇으로 대체할지는
호출하는 쪽이 정한다.
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# 답변이 길어지면 채팅 말풍선이 화면을 다 덮는다. 서너 문장이면 충분하다.
MAX_TOKENS = 500


class LlmUnavailable(RuntimeError):
    """키가 없거나, 응답이 늦거나, 형식이 예상과 다를 때."""


def is_enabled() -> bool:
    return settings.tarot_llm_enabled


def complete(messages: list[dict[str, str]]) -> str:
    """messages 는 OpenAI 형식의 role/content 목록."""
    if not settings.tarot_llm_enabled:
        raise LlmUnavailable("DEEPSEEK_TAROT_API_KEY 가 설정되지 않았어요.")

    try:
        response = httpx.post(
            f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.deepseek_tarot_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.deepseek_tarot_model,
                "messages": messages,
                "max_tokens": MAX_TOKENS,
                "temperature": 1.0,
                "stream": False,
            },
            timeout=settings.llm_timeout,
        )
    except httpx.HTTPError as exc:
        # 키가 로그에 남지 않도록 예외 종류만 남긴다.
        logger.warning("DeepSeek 요청 실패: %s", type(exc).__name__)
        raise LlmUnavailable("응답 서버에 연결하지 못했어요.") from exc

    if response.status_code != 200:
        logger.warning("DeepSeek 응답 코드 %s", response.status_code)
        raise LlmUnavailable(f"응답 서버가 {response.status_code} 를 돌려줬어요.")

    try:
        content = response.json()["choices"][0]["message"]["content"]
    except (KeyError, IndexError, ValueError) as exc:
        logger.warning("DeepSeek 응답 형식이 예상과 달라요: %s", type(exc).__name__)
        raise LlmUnavailable("응답 형식을 읽지 못했어요.") from exc

    text = (content or "").strip()
    if not text:
        raise LlmUnavailable("빈 답변이 왔어요.")
    return text
