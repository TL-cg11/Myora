"""WAS 보안 로그 스키마 v1.0 생성 및 Kafka 전송."""

from __future__ import annotations

import json
import logging
import os
import time
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import Request, Response

from app.config import settings


SCHEMA_VERSION = "1.0"
SOURCE = "was"
SERVICE = "luck-was"
TOPIC = "myohan.was.app"
FEATURE_PREFIXES = {
    "/api/saju": "saju",
    "/api/tarot": "tarot",
    "/api/face": "face",
}

logger = logging.getLogger(__name__)
_producer: Any | None = None
_current_request_id: ContextVar[str | None] = ContextVar(
    "was_log_request_id", default=None
)


def _feature_from_path(path: str) -> str | None:
    return next(
        (
            feature
            for prefix, feature in FEATURE_PREFIXES.items()
            if path == prefix or path.startswith(f"{prefix}/")
        ),
        None,
    )


def _request_id(request: Request) -> str:
    value = request.headers.get("x-request-id", "").strip()
    return value[:128] if value else uuid4().hex


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",", maxsplit=1)[0].strip()[:45]
    return (request.client.host if request.client else "unknown")[:45]


def _uuid_or_none(value: Any) -> str | None:
    if value is None:
        return None
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError):
        return None


def _request_data(body: bytes) -> dict[str, Any]:
    if not body:
        return {}
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _question_from_data(data: dict[str, Any]) -> str | None:
    """지원하는 API payload에서 실제 사용자 질문 하나만 꺼낸다."""
    for key in ("question", "message"):
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    messages = data.get("messages")
    if isinstance(messages, list):
        for message in reversed(messages):
            if (
                isinstance(message, dict)
                and message.get("role") == "user"
                and isinstance(message.get("content"), str)
                and message["content"]
            ):
                return message["content"]
    return None


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _common_log(
    *, feature: str, event_type: str, request_id: str, guest_key: Any = None
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid4()),
        "request_id": request_id,
        "timestamp": _timestamp(),
        "environment": settings.app_env,
        "severity": "INFO",
        "source": SOURCE,
        "service": SERVICE,
        "feature": feature,
        "event_type": event_type,
        "user_id": None,
        "guest_key": _uuid_or_none(guest_key),
    }


def build_api_request_log(
    request: Request,
    response: Response,
    *,
    body: bytes,
    feature: str,
    request_id: str,
    processing_time: float,
) -> dict[str, Any]:
    """허용된 요청 필드만 사용해 api_request 이벤트를 만든다."""
    data = _request_data(body)
    query_guest_key = request.query_params.get("guest_key")
    input_data: dict[str, str] = {
        key: data[key]
        for key in ("topic",)
        if isinstance(data.get(key), str)
    }
    question = _question_from_data(data)
    if question is not None:
        input_data["question"] = question
    severity = "ERROR" if response.status_code >= 500 else "WARNING" if response.status_code >= 400 else "INFO"

    event = _common_log(
        feature=feature,
        event_type="api_request",
        request_id=request_id,
        guest_key=data.get("guest_key") or query_guest_key,
    )
    event.update({
        "severity": severity,
        "method": request.method,
        "uri": request.url.path,
        "status": response.status_code,
        "client_ip": _client_ip(request),
        "processing_time": round(processing_time, 6),
        "input": input_data,
        "metadata": {"content_length": len(body)},
    })
    return event


def build_ai_request_log(
    *,
    feature: str,
    question: str,
    model: str,
    timeout_seconds: float,
    guest_key: Any = None,
    reading_id: int | None = None,
    question_sequence: int | None = None,
    message_count: int | None = None,
    context_length: int | None = None,
    phase: str | None = None,
    policy_version: str | None = None,
) -> dict[str, Any]:
    """DeepSeek 호출 직전에 기록할 ai_request 이벤트를 만든다."""
    event = _common_log(
        feature=feature,
        event_type="ai_request",
        request_id=_current_request_id.get() or uuid4().hex,
        guest_key=guest_key,
    )
    event.update(
        {
            "ai_call_id": str(uuid4()),
            "ai": {
                "provider": "deepseek",
                "model": model,
                "timeout_seconds": timeout_seconds,
            },
            "input": {},
            "metadata": {
                key: value
                for key, value in {
                    "reading_id": reading_id,
                    "question_sequence": question_sequence,
                    "message_count": message_count,
                    "context_length": context_length,
                    "prompt_length": len(question),
                    "phase": phase,
                    "policy_version": policy_version,
                }.items()
                if value is not None
            },
        }
    )
    return event


def build_guardrail_decision_log(
    *,
    feature: str,
    decision: str,
    risk_level: str,
    rules: list[str],
    policy_version: str,
    phase: str,
) -> dict[str, Any]:
    """사용자 원문이나 모델 답변 없이 가드레일 판정만 기록한다."""
    event = _common_log(
        feature=feature,
        event_type="ai_guardrail_decision",
        request_id=_current_request_id.get() or uuid4().hex,
    )
    event.update(
        {
            "severity": {
                "LOW": "INFO",
                "MEDIUM": "INFO",
                "HIGH": "WARNING",
                "CRITICAL": "WARNING",
            }.get(risk_level, "WARNING"),
            "guardrail": {
                "policy_version": policy_version,
                "phase": phase,
                "decision": decision,
                "risk_level": risk_level,
                "rules": rules,
            },
        }
    )
    return event


def build_chat_exchange_log(
    *,
    feature: str,
    question: str,
    answer: str,
    guest_key: Any = None,
    reading_id: int | None = None,
    generated: bool | None = None,
) -> dict[str, Any]:
    """사용자에게 확정해서 돌려준 질문·답변 한 쌍을 기록한다."""
    event = _common_log(
        feature=feature,
        event_type="chat_exchange",
        request_id=_current_request_id.get() or uuid4().hex,
        guest_key=guest_key,
    )
    event.update(
        {
            "input": {"question": question},
            "output": {"answer": answer},
            "metadata": {
                key: value
                for key, value in {
                    "reading_id": reading_id,
                    "prompt_length": len(question),
                    "answer_length": len(answer),
                    "generated": generated,
                }.items()
                if value is not None
            },
        }
    )
    return event


def _get_producer() -> Any:
    global _producer
    if _producer is None:
        from confluent_kafka import Producer

        _producer = Producer(
            {
                "bootstrap.servers": os.getenv(
                    "KAFKA_BOOTSTRAP_SERVERS", "localhost:9092"
                ),
                "client.id": SERVICE,
                "enable.idempotence": True,
                "acks": "all",
            }
        )
    return _producer


def _delivery_report(error: Any, message: Any) -> None:
    if error is not None:
        logger.error("WAS Kafka 로그 전송 실패: %s", error)


def emit_was_log(event: dict[str, Any]) -> None:
    """요청 처리를 막지 않고 WAS JSON 로그를 Kafka로 전송한다."""
    try:
        producer = _get_producer()
        producer.produce(
            TOPIC,
            key=event["request_id"],
            value=json.dumps(event, ensure_ascii=False, separators=(",", ":")),
            callback=_delivery_report,
        )
        producer.poll(0)
    except Exception as error:
        logger.error("WAS Kafka 로그 생성 또는 큐 적재 실패: %s", error)


def emit_ai_request_log(**kwargs: Any) -> str:
    """ai_request 이벤트를 Kafka로 보내고 생성한 ai_call_id를 반환한다."""
    event = build_ai_request_log(**kwargs)
    emit_was_log(event)
    return event["ai_call_id"]


def emit_guardrail_decision_log(**kwargs: Any) -> None:
    emit_was_log(build_guardrail_decision_log(**kwargs))


def emit_chat_exchange_log(**kwargs: Any) -> None:
    emit_was_log(build_chat_exchange_log(**kwargs))


def flush_was_logs(timeout: float = 10.0) -> None:
    """프로세스 종료 전에 Producer 큐의 메시지를 가능한 만큼 전송한다."""
    if _producer is None:
        return
    remaining = _producer.flush(timeout)
    if remaining:
        logger.error("종료 시 전송하지 못한 WAS Kafka 로그: %s건", remaining)


async def api_request_log_middleware(request: Request, call_next) -> Response:
    """사주·타로·관상 API의 처리 결과를 JSON 로그로 기록한다."""
    feature = _feature_from_path(request.url.path)
    if feature is None:
        return await call_next(request)

    request_id = _request_id(request)
    request_id_token = _current_request_id.set(request_id)
    body = await request.body()
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        event = build_api_request_log(
            request,
            Response(status_code=500),
            body=body,
            feature=feature,
            request_id=request_id,
            processing_time=time.perf_counter() - started_at,
        )
        emit_was_log(event)
        raise
    finally:
        _current_request_id.reset(request_id_token)

    emit_was_log(
        build_api_request_log(
            request,
            response,
            body=body,
            feature=feature,
            request_id=request_id,
            processing_time=time.perf_counter() - started_at,
        )
    )
    response.headers["X-Request-ID"] = request_id
    return response
