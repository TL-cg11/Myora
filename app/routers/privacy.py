"""브라우저가 사용자 말풍선에 쓸 문맥 기반 마스킹 API."""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.services.display_privacy import mask_display_text

router = APIRouter(prefix="/api/privacy", tags=["privacy"])


class DisplayMaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=settings.ai_message_max_chars)


class DisplayMaskResponse(BaseModel):
    display_text: str


@router.post("/display-mask", response_model=DisplayMaskResponse)
async def display_mask(payload: DisplayMaskRequest) -> DisplayMaskResponse:
    return DisplayMaskResponse(display_text=await mask_display_text(payload.text))
