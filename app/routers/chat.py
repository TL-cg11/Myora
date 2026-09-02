import logging
from typing import Literal

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.config import settings
from app.prompts import FACE_PERSONA


router = APIRouter(prefix="/api", tags=["chat"])
logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=1_500)


class ChatRequest(BaseModel):
    context: str = Field(min_length=1, max_length=8_000)
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)


class ChatResponse(BaseModel):
    answer: str


def build_deepseek_messages(request: ChatRequest) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": f"{FACE_PERSONA}\n\n[현재 관상 결과]\n{request.context}",
        },
        *(message.model_dump() for message in request.messages),
    ]


@router.post("/face/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    if not settings.deepseek_face_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="관상 페이지의 DeepSeek API 키가 설정되지 않았어요.",
        )

    payload = {
        "model": settings.deepseek_face_model,
        "messages": build_deepseek_messages(request),
        "thinking": {"type": "disabled"},
        "max_tokens": 700,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {settings.deepseek_face_api_key}",
        "Content-Type": "application/json",
    }
    endpoint = f"{settings.deepseek_base_url.rstrip('/')}/chat/completions"

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
            response = await client.post(endpoint, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
    except httpx.TimeoutException as error:
        logger.warning("DeepSeek request timed out: %s", error)
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="AI 답변 시간이 초과됐어요. 잠시 후 다시 시도해 주세요.",
        ) from error
    except httpx.HTTPStatusError as error:
        logger.warning("DeepSeek returned HTTP %s", error.response.status_code)
        if error.response.status_code == status.HTTP_401_UNAUTHORIZED:
            detail = "DeepSeek API 키가 올바르지 않아요. 서버 설정을 확인해 주세요."
        elif error.response.status_code == status.HTTP_429_TOO_MANY_REQUESTS:
            detail = "AI 요청이 많거나 사용 한도에 도달했어요. 잠시 후 다시 시도해 주세요."
        else:
            detail = "AI 서비스가 응답하지 않았어요. 잠시 후 다시 시도해 주세요."
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=detail) from error
    except (httpx.RequestError, ValueError) as error:
        logger.warning("DeepSeek request failed: %s", error)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 서비스에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.",
        ) from error

    try:
        answer = data["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError, AttributeError) as error:
        logger.warning("DeepSeek returned an unexpected response shape")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI 응답 형식을 확인할 수 없어요. 잠시 후 다시 시도해 주세요.",
        ) from error

    if not answer:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="AI가 빈 답변을 보냈어요. 질문을 바꿔 다시 시도해 주세요.",
        )
    return ChatResponse(answer=answer)
