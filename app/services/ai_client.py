"""DeepSeek transport shared by all fortune chat and guardrail calls."""

import httpx

from app.config import settings
from app.kafka_logging import emit_ai_request_log
from app.prompts.guardrail import POLICY_VERSION


async def completion(
    messages: list[dict[str, str]],
    key: str,
    model: str,
    *,
    check: bool = False,
    feature: str = "unknown",
    phase: str = "generation",
) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "thinking": {"type": "disabled"},
        "max_tokens": (
            settings.ai_check_max_tokens if check else settings.ai_max_tokens
        ),
    }
    if check:
        payload["response_format"] = {"type": "json_object"}

    emit_ai_request_log(
        feature=feature,
        question="",
        model=model,
        timeout_seconds=settings.ai_request_timeout,
        message_count=len(messages),
        phase=phase,
        policy_version=POLICY_VERSION,
    )

    timeout = httpx.Timeout(
        settings.ai_request_timeout,
        connect=settings.ai_connect_timeout,
    )
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
        )
        response.raise_for_status()

    choice = response.json()["choices"][0]
    if choice.get("finish_reason") != "stop":
        raise ValueError("incomplete response")
    text = choice["message"]["content"]
    if not isinstance(text, str) or not text.strip():
        raise ValueError("empty response")
    return text.strip()
