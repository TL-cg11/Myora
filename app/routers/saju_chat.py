import httpx
from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.prompts.saju import SAJU_PERSONA
from app.routers.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/saju", tags=["saju-chat"])

@router.post("/chat", response_model=ChatResponse)
async def saju_chat(request: ChatRequest) -> ChatResponse:
    if not settings.deepseek_saju_api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="사주용 DeepSeek API 키가 설정되지 않았습니다.")
    payload = {
        "model": settings.deepseek_saju_model,
        "messages": [{"role": "system", "content": f"{SAJU_PERSONA}\n\n[사주 결과]\n{request.context}"}, *(message.model_dump() for message in request.messages)],
        "thinking": {"type": "disabled"},
        "max_tokens": 700,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
            response = await client.post(f"{settings.deepseek_base_url.rstrip('/')}/chat/completions", headers={"Authorization": f"Bearer {settings.deepseek_saju_api_key}"}, json=payload)
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"].strip()
            if not answer:
                raise ValueError("DeepSeek returned an empty answer")
    except (httpx.HTTPError, KeyError, IndexError, TypeError, AttributeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="사주 AI 응답을 가져오지 못했습니다.") from error
    return ChatResponse(answer=answer)
