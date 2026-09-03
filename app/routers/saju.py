from datetime import date, datetime, time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


router = APIRouter(prefix="/api/saju", tags=["saju"])


class SajuProfileRequest(BaseModel):
    name: str | None = None
    birth_date: date
    birth_time: time | None = None
    gender: str | None = None


@router.post("/readings")
def create_saju_reading(payload: SajuProfileRequest) -> dict:
    try:
        from korean_saju import Saju, SajuAnalysis, load_bundled_data
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="Install korean-saju first") from exc

    solar_terms = load_bundled_data()[1]
    birth = datetime.combine(payload.birth_date, payload.birth_time or time(12, 0))
    saju = Saju.from_birth(
        kst_moment=birth,
        solar_terms=solar_terms,
        longitude=126.9784,
        yaja_si_separated=True,
    )
    analysis = SajuAnalysis(saju)
    return {
        "status": "ok",
        "profile": payload.model_dump(mode="json"),
        "reading": {
            "pillars": str(saju),
            "jeonggyeok": str(analysis.jeonggyeok),
            "yongsin": str(analysis.yongsin),
            "sinsal": [str(item) for item in analysis.sinsal],
        },
    }
