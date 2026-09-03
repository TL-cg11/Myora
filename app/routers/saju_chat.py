import httpx
from fastapi import APIRouter, HTTPException, status

from app.config import settings
from app.routers.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/saju", tags=["saju-chat"])

SAJU_PERSONA = "사주 결과를 쉽게 설명하는 친절한 안내자다. 제공된 결과 안에서만 답하고, 건강·재물·미래를 확정하지 않으며 오락용 참고임을 안내한다."


@router.post("/chat", response_model=ChatResponse)
async def saju_chat(request: ChatRequest) -> ChatResponse:
    if not settings.deepseek_saju_api_key:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="사주용 DeepSeek API 키가 설정되지 않았습니다.")
    payload = {
        "model": settings.deepseek_saju_model,
        "messages": [{"role": "system", "content": f"{SAJU_PERSONA}\n\n[사주 결과]\n{request.context}"}, *(message.model_dump() for message in request.messages)],
        "max_tokens": 700,
        "stream": False,
    }
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
            response = await client.post(f"{settings.deepseek_base_url.rstrip('/')}/chat/completions", headers={"Authorization": f"Bearer {settings.deepseek_saju_api_key}"}, json=payload)
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, IndexError, TypeError, AttributeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="사주 AI 응답을 가져오지 못했습니다.") from error
    return ChatResponse(answer=answer)
