"""실제 가드레일 시스템 프롬프트로 DeepSeek 컨텍스트 캐싱이 작동하는지 확인한다.

같은 요청을 두 번 보내서 두 번째 응답의 prompt_cache_hit_tokens가
올라가는지 본다. 운영에 영향 없음(별도 스크립트, DB/Kafka 안 건드림).

실행:
    .venv/bin/python scripts/check_prompt_cache.py
"""
import asyncio
import json
import os

import httpx

from app.config import settings
from app.prompts.policy_versions import ACTIVE


async def main() -> None:
    key = settings.deepseek_tarot_api_key or settings.deepseek_api_key
    if not key:
        raise SystemExit("DEEPSEEK_TAROT_API_KEY (또는 DEEPSEEK_API_KEY)가 비어 있습니다.")

    instruction = ACTIVE.COMMON_POLICY + ACTIVE.INPUT_CHECK_INSTRUCTION
    data = {
        "service": "saju",
        "context": "",
        "question": "안녕하세요, 오늘 운세가 궁금해요",
        "history": [],
    }
    payload = {
        "model": settings.ai_guardrail_model,
        "messages": [
            {"role": "system", "content": instruction},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
        ],
        "stream": False,
        "thinking": {"type": "disabled"},
        "response_format": {"type": "json_object"},
        "max_tokens": settings.ai_check_max_tokens,
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        for attempt in (1, 2):
            response = await client.post(
                f"{settings.deepseek_base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json=payload,
            )
            response.raise_for_status()
            usage = response.json().get("usage", {})
            print(f"--- {attempt}차 ---")
            print(json.dumps(usage, ensure_ascii=False, indent=2))
            if attempt == 1:
                await asyncio.sleep(2)


if __name__ == "__main__":
    asyncio.run(main())
