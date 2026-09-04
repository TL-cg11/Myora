import unittest
from datetime import datetime
from uuid import uuid4

from pydantic import ValidationError

from app.models import FaceReading, FaceShape, Reading
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


class FakeSession:
    def __init__(self, shape: FaceShape | None):
        self.shape = shape
        self.added = []
        self.committed = False

    def scalar(self, _statement):
        return self.shape

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

        reading, selected_shape = save_face_reading(session, payload())

        detail = next(item for item in session.added if isinstance(item, FaceReading))
        self.assertEqual(reading.id, 101)
        self.assertEqual(reading.service, "face")
        self.assertEqual(reading.status, "interpreted")
        self.assertEqual(reading.summary_title, f"{shape.title} · 밝은 분위기")
        self.assertEqual(selected_shape.code, "균형형")
        self.assertEqual(detail.shape_id, shape.id)
        self.assertEqual(str(detail.eye_ratio), "0.185")
        self.assertFalse(hasattr(detail, "image"))
        self.assertFalse(hasattr(detail, "landmarks"))
        self.assertTrue(session.committed)

    def test_fails_when_shape_seed_is_missing(self) -> None:
        with self.assertRaisesRegex(ValueError, "인상 유형"):
            save_face_reading(FakeSession(None), payload())


if __name__ == "__main__":
    unittest.main()
