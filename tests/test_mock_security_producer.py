from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import mock_security_producer as producer  # noqa: E402


def fixture(name: str) -> dict:
    with (ROOT / "fixtures" / name).open(encoding="utf-8") as handle:
        return json.load(handle)


class ContractValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.security = fixture("luck.security-events.normal.json")
        self.masked = fixture("luck.masked-logs.normal.json")

    def test_normal_security_event_is_valid(self) -> None:
        producer.validate("myohan.security-events", self.security)

    def test_normal_masked_log_is_valid(self) -> None:
        producer.validate("myohan.masked-logs", self.masked)

    def test_invalid_fixtures_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            producer.validate("myohan.security-events", fixture("luck.security-events.invalid-schema.json"))
        with self.assertRaises(ValueError):
            producer.validate("myohan.masked-logs", fixture("luck.masked-logs.invalid-schema.json"))

    def test_additional_field_is_rejected(self) -> None:
        record = copy.deepcopy(self.security)
        record["unexpected"] = True
        with self.assertRaisesRegex(ValueError, "additional fields"):
            producer.validate("myohan.security-events", record)

    def test_invalid_environment_is_rejected(self) -> None:
        record = copy.deepcopy(self.security)
        record["environment"] = ""
        with self.assertRaisesRegex(ValueError, "must be one of"):
            producer.validate("myohan.security-events", record)

    def test_invalid_datetime_is_rejected(self) -> None:
        record = copy.deepcopy(self.security)
        record["occurred_at"] = "not-a-dateZ"
        with self.assertRaisesRegex(ValueError, "ISO 8601"):
            producer.validate("myohan.security-events", record)

    def test_invalid_detection_category_is_rejected(self) -> None:
        record = copy.deepcopy(self.security)
        record["detections"][0]["category"] = "UNKNOWN"
        with self.assertRaisesRegex(ValueError, "must be one of"):
            producer.validate("myohan.security-events", record)

    def test_schema_numeric_ranges_are_enforced(self) -> None:
        record = copy.deepcopy(self.security)
        record["risk_score"] = 101
        with self.assertRaisesRegex(ValueError, "greater than 100"):
            producer.validate("myohan.security-events", record)


if __name__ == "__main__":
    unittest.main()
