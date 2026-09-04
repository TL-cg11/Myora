"""브라우저에서 측정한 관상 비율을 원본 사진 없이 저장한다."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FaceReading, FaceShape, Reading
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


def save_face_reading(
    session: Session, payload: FaceReadingCreate
) -> tuple[Reading, FaceShape]:
    shape_code = classify_face_shape(payload.measurements)
    shape = session.scalar(
        select(FaceShape).where(
            FaceShape.code == shape_code,
            FaceShape.is_active.is_(True),
        )
    )
    if shape is None:
        raise ValueError("사용 가능한 관상 인상 유형을 찾을 수 없어요.")

    reading = Reading(
        service="face",
        guest_key=str(payload.guest_key),
        summary_title=f"{shape.title} · {payload.mood} 분위기",
        summary_text=payload.summary_text,
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
    return reading, shape


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
