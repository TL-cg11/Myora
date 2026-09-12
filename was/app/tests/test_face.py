import unittest
from datetime import datetime
from uuid import uuid4

from pydantic import ValidationError

from app.models import FaceInterpretation, FaceReading, FaceShape, Reading
from app.schemas import FaceMeasurementsIn, FaceReadingCreate
from app.services.face import classify_face_shape, save_face_reading


def measurements(**overrides) -> FaceMeasurementsIn:
    values = {
        "aspect_ratio": 1.39,
        "jaw_ratio": 0.87,
        "forehead_ratio": 0.89,
        "eye_ratio": 0.185,
        "mouth_ratio": 0.35,
        "symmetry_score": 0.95,
        "coverage": 0.25,
        "roll_degrees": 1.2,
        "nose_offset": 0.01,
    }
    values.update(overrides)
    return FaceMeasurementsIn(**values)


def payload(**overrides) -> FaceReadingCreate:
    values = {
        "guest_key": uuid4(),
        "mood": "밝은",
        "detector_version": "face-landmarker-float16-v1",
        "summary_text": "측정 비율에 따라 만든 관상 결과예요.",
        "measurements": measurements(),
    }
    values.update(overrides)
    return FaceReadingCreate(**values)


INTERPRETATION_CODES = {
    "proportion": ["long", "short", "balanced"],
    "contour": ["tapered", "strong-jaw", "even"],
    "eye": ["wide", "narrow", "balanced"],
    "mouth": ["wide", "narrow", "balanced"],
    "harmony": ["high", "balanced", "natural"],
    "mood": ["calm", "bright", "mysterious", "strong"],
    "closing": ["default"],
}


def interpretation_rows() -> list[FaceInterpretation]:
    return [
        FaceInterpretation(
            id=index,
            category=category,
            code=code,
            label=f"{category}/{code}",
            description=f"DB 설명: {category}/{code}",
            keyword=None if category == "closing" else f"#{category}-{code}",
            sort_order=index,
            is_active=True,
        )
        for index, (category, code) in enumerate(
            (
                (category, code)
                for category, codes in INTERPRETATION_CODES.items()
                for code in codes
            ),
            start=1,
        )
    ]


class FakeScalarRows:
    def __init__(self, rows):
        self.rows = rows

    def all(self):
        return self.rows


class FakeSession:
    def __init__(self, shape: FaceShape | None, details=None):
        self.shape = shape
        self.details = interpretation_rows() if details is None else details
        self.added = []
        self.committed = False

    def scalar(self, _statement):
        return self.shape

    def scalars(self, _statement):
        return FakeScalarRows(self.details)

    def add(self, item):
        self.added.append(item)

    def flush(self):
        reading = next((item for item in self.added if isinstance(item, Reading)), None)
        if reading is not None:
            reading.id = 101
            reading.created_at = datetime(2026, 9, 4, 12, 0, 0)

    def commit(self):
        self.committed = True

    def refresh(self, _item):
        return None


class FaceClassificationTests(unittest.TestCase):
    def test_classifies_all_seeded_shape_codes(self) -> None:
        cases = [
            (measurements(jaw_ratio=0.76, forehead_ratio=0.86), "하트형"),
            (measurements(aspect_ratio=1.4, jaw_ratio=0.84), "각진형"),
            (measurements(aspect_ratio=1.24, jaw_ratio=0.76), "둥근형"),
            (measurements(aspect_ratio=1.5, jaw_ratio=0.8), "긴 타원형"),
            (measurements(aspect_ratio=1.36, jaw_ratio=0.79, forehead_ratio=0.84), "균형형"),
        ]
        for measured, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(classify_face_shape(measured), expected)

    def test_rejects_photo_or_landmark_fields(self) -> None:
        with self.assertRaises(ValidationError):
            FaceReadingCreate(
                guest_key=uuid4(),
                mood="차분한",
                detector_version="face-landmarker-float16-v1",
                summary_text="결과",
                measurements=measurements(),
                image="data:image/jpeg;base64,not-allowed",
            )


class FacePersistenceTests(unittest.TestCase):
    def test_has_twenty_database_interpretation_variants(self) -> None:
        self.assertEqual(len(interpretation_rows()), 20)

    def test_saves_common_reading_and_measurements_without_photo(self) -> None:
        shape = FaceShape(
            id=5,
            code="균형형",
            title="부드러움과 또렷함이 조화로운 인상",
            keyword="#균형있는인상",
            summary="균형 잡힌 윤곽이에요.",
            is_active=True,
        )
        session = FakeSession(shape)

        reading, selected_shape, keywords = save_face_reading(session, payload())

        detail = next(item for item in session.added if isinstance(item, FaceReading))
        self.assertEqual(reading.id, 101)
        self.assertEqual(reading.service, "face")
        self.assertEqual(reading.status, "interpreted")
        self.assertEqual(reading.summary_title, f"{shape.title} · 밝은 분위기")
        self.assertIn(f"가장 먼저 보이는 건 {shape.title}이에요", reading.summary_text)
        self.assertIn("DB 설명: proportion/balanced", reading.summary_text)
        self.assertNotIn("측정 비율에 따라 만든 관상 결과예요.", reading.summary_text)
        self.assertEqual(selected_shape.code, "균형형")
        self.assertEqual(keywords, ["#균형있는인상", "#mood-bright", "#contour-even"])
        self.assertEqual(detail.shape_id, shape.id)
        self.assertEqual(str(detail.eye_ratio), "0.185")
        self.assertFalse(hasattr(detail, "image"))
        self.assertFalse(hasattr(detail, "landmarks"))
        self.assertTrue(session.committed)

    def test_fails_when_shape_seed_is_missing(self) -> None:
        with self.assertRaisesRegex(ValueError, "인상 유형"):
            save_face_reading(FakeSession(None), payload())

    def test_fails_when_detail_seed_is_missing(self) -> None:
        shape = FaceShape(
            id=5,
            code="균형형",
            title="균형 잡힌 인상",
            keyword="#균형",
            summary="균형 잡힌 윤곽이에요.",
            is_active=True,
        )
        with self.assertRaisesRegex(ValueError, "세부 해석이 누락"):
            save_face_reading(FakeSession(shape, details=[]), payload())


if __name__ == "__main__":
    unittest.main()
