"""DeepSeek transport shared by all fortune chat and guardrail calls."""

from contextlib import contextmanager
from contextvars import ContextVar
from time import perf_counter
from typing import Iterator

import httpx

from app.config import settings
from app.kafka_logging import emit_ai_request_log
from app.prompts.guardrail import POLICY_VERSION


_captured_calls: ContextVar[list[dict] | None] = ContextVar(
    "captured_ai_calls", default=None
)

# 요청마다 새로 만들지 않고 앱 생명주기 동안 하나만 재사용해 TLS 핸드셰이크를
# 반복하지 않는다. timeout은 클라이언트가 아니라 요청 단위로 준다(check 여부에
# 따라 값이 다르므로). main.py의 startup/shutdown 훅이 열고 닫는다.
_client: httpx.AsyncClient | None = None


def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient()
    return _client


async def close_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


@contextmanager
def capture_ai_calls() -> Iterator[list[dict]]:
    """Collect call metadata for an explicit evaluation without storing content."""
    calls: list[dict] = []
    token = _captured_calls.set(calls)
    try:
        yield calls
    finally:
        _captured_calls.reset(token)


async def completion(
    messages: list[dict[str, str]],
    key: str,
    model: str,
    *,
    check: bool = False,
    feature: str = "unknown",
    phase: str = "generation",
) -> str:
    started = perf_counter()
    usage: dict = {}
    succeeded = False
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
        settings.ai_check_timeout if check else settings.ai_request_timeout,
        connect=settings.ai_connect_timeout,
    )
    try:
        client = get_client()
        response = await client.post(
            f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}"},
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()

        body = response.json()
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        choice = body["choices"][0]
        if choice.get("finish_reason") != "stop":
            raise ValueError("incomplete response")
        text = choice["message"]["content"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("empty response")
        succeeded = True
        return text.strip()
    finally:
        calls = _captured_calls.get()
        if calls is not None:
            calls.append({
                "phase": phase,
                "model": model,
                "elapsed_ms": round((perf_counter() - started) * 1000, 3),
                "success": succeeded,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
            })
