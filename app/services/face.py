"""브라우저에서 측정한 관상 비율을 원본 사진 없이 저장한다."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FaceInterpretation, FaceReading, FaceShape, Reading
from app.schemas import FaceMeasurementsIn, FaceReadingCreate


def classify_face_shape(measurements: FaceMeasurementsIn) -> str:
    """프론트의 classifyFaceShape와 같은 경계값을 사용한다."""
    if measurements.aspect_ratio >= 1.43:
        return "긴 타원형"
    if measurements.aspect_ratio <= 1.28 and measurements.jaw_ratio >= 0.72:
        return "둥근형"
    if (
        measurements.forehead_ratio - measurements.jaw_ratio >= 0.08
        and measurements.jaw_ratio < 0.82
    ):
        return "하트형"
    if measurements.jaw_ratio >= 0.82 and measurements.aspect_ratio <= 1.42:
        return "각진형"
    return "균형형"


def _decimal(value: float | None) -> Decimal | None:
    return None if value is None else Decimal(str(value))


MOOD_CODE = {
    "차분한": "calm",
    "밝은": "bright",
    "신비로운": "mysterious",
    "단단한": "strong",
}


def _interpretation_codes(measurements: FaceMeasurementsIn, mood: str) -> dict[str, str]:
    width_difference = measurements.forehead_ratio - measurements.jaw_ratio
    return {
        "proportion": (
            "long"
            if measurements.aspect_ratio >= 1.45
            else "short" if measurements.aspect_ratio <= 1.34 else "balanced"
        ),
        "contour": (
            "tapered"
            if width_difference >= 0.07
            else "strong-jaw" if width_difference <= -0.04 else "even"
        ),
        "eye": (
            "wide"
            if measurements.eye_ratio >= 0.2
            else "narrow" if measurements.eye_ratio <= 0.175 else "balanced"
        ),
        "mouth": (
            "wide"
            if measurements.mouth_ratio >= 0.375
            else "narrow" if measurements.mouth_ratio <= 0.325 else "balanced"
        ),
        "harmony": (
            "high"
            if measurements.symmetry_score >= 0.96
            else "balanced" if measurements.symmetry_score >= 0.91 else "natural"
        ),
        "mood": MOOD_CODE[mood],
        "closing": "default",
    }


def _load_interpretations(session: Session) -> dict[tuple[str, str], FaceInterpretation]:
    rows = session.scalars(
        select(FaceInterpretation).where(FaceInterpretation.is_active.is_(True))
    ).all()
    return {(row.category, row.code): row for row in rows}


def compose_face_reading(
    shape: FaceShape,
    measurements: FaceMeasurementsIn,
    mood: str,
    interpretations: dict[tuple[str, str], FaceInterpretation],
) -> tuple[str, str, list[str]]:
    """DB 기준 문구를 측정 결과에 맞게 골라 제목·본문·키워드를 만든다."""
    codes = _interpretation_codes(measurements, mood)
    selected: dict[str, FaceInterpretation] = {}
    for category, code in codes.items():
        row = interpretations.get((category, code))
        if row is None:
            raise ValueError(f"관상 세부 해석이 누락됐어요: {category}/{code}")
        selected[category] = row

    title = f"{shape.title} · {mood} 분위기"
    result = "\n\n".join(
        [
            f"사진에서 가장 먼저 보이는 건 {shape.title}이에요.",
            f"얼굴형 · {shape.summary}",
            f"비율 포인트 · {selected['proportion'].description} {selected['contour'].description}",
            f"눈매 · {selected['eye'].description}",
            f"입매 · {selected['mouth'].description}",
            f"전체 조화 · {selected['harmony'].description}",
            f"선택한 분위기 · {selected['mood'].description}",
            f"묘라의 한마디 · {selected['closing'].description}",
            "※ 이 결과는 얼굴 비율을 전통 관상 표현에 연결한 재미용 콘텐츠예요. 외모로 실제 성격·능력·건강·미래를 판단할 수는 없어요.",
        ]
    )

    detail = selected["eye"]
    if codes["eye"] == "balanced":
        detail = selected["mouth"] if codes["mouth"] != "balanced" else selected["contour"]
    keywords = [shape.keyword, selected["mood"].keyword, detail.keyword]
    return title, result, [keyword for keyword in keywords if keyword]


def save_face_reading(
    session: Session, payload: FaceReadingCreate
) -> tuple[Reading, FaceShape, list[str]]:
    shape_code = classify_face_shape(payload.measurements)
    shape = session.scalar(
        select(FaceShape).where(
            FaceShape.code == shape_code,
            FaceShape.is_active.is_(True),
        )
    )
    if shape is None:
        raise ValueError("사용 가능한 관상 인상 유형을 찾을 수 없어요.")

    title, result, keywords = compose_face_reading(
        shape,
        payload.measurements,
        payload.mood,
        _load_interpretations(session),
    )

    reading = Reading(
        service="face",
        guest_key=str(payload.guest_key),
        summary_title=title,
        summary_text=result,
        interpretation_source="rule",
        status="interpreted",
    )
    session.add(reading)
    session.flush()

    measurements = payload.measurements
    session.add(
        FaceReading(
            reading_id=reading.id,
            shape_id=shape.id,
            aspect_ratio=_decimal(measurements.aspect_ratio),
            jaw_ratio=_decimal(measurements.jaw_ratio),
            forehead_ratio=_decimal(measurements.forehead_ratio),
            eye_ratio=_decimal(measurements.eye_ratio),
            mouth_ratio=_decimal(measurements.mouth_ratio),
            symmetry_score=_decimal(measurements.symmetry_score),
            mood=payload.mood,
            detector_version=payload.detector_version,
            coverage=_decimal(measurements.coverage),
            roll_degrees=_decimal(measurements.roll_degrees),
            nose_offset=_decimal(measurements.nose_offset),
        )
    )
    session.commit()
    session.refresh(reading)
    return reading, shape, keywords


def list_face_readings(
    session: Session, *, guest_key: str, limit: int
) -> list[tuple[Reading, FaceReading, FaceShape]]:
    statement = (
        select(Reading, FaceReading, FaceShape)
        .join(FaceReading, FaceReading.reading_id == Reading.id)
        .join(FaceShape, FaceShape.id == FaceReading.shape_id)
        .where(Reading.service == "face", Reading.guest_key == guest_key)
        .order_by(Reading.created_at.desc(), Reading.id.desc())
        .limit(limit)
    )
    return list(session.execute(statement).all())
