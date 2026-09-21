import json
import unittest

from app.kafka_logging import build_guardrail_decision_log
from consumer.was_kafka_consumer import (
    BASE_DIR,
    InvalidWasLog,
    handle_was_log,
    load_schema_validator,
    parse_was_log,
)


class FakeValidator:
    def validate(self, event) -> None:
        if event.get("service") != "luck-was":
            raise ValueError("invalid service")


class WasKafkaConsumerTest(unittest.TestCase):
    def test_decodes_and_validates_message(self) -> None:
        event = {"service": "luck-was", "event_type": "api_request"}
        parsed = parse_was_log(json.dumps(event).encode("utf-8"), FakeValidator())
        self.assertEqual(parsed, event)

    def test_rejects_invalid_json(self) -> None:
        with self.assertRaises(InvalidWasLog):
            parse_was_log(b"{invalid", FakeValidator())

    def test_rejects_schema_failure(self) -> None:
        with self.assertRaises(InvalidWasLog):
            parse_was_log(b'{"service":"other"}', FakeValidator())

    def test_default_handler_does_not_allow_offset_commit(self) -> None:
        self.assertFalse(
            handle_was_log(
                {
                    "event_id": "event-1",
                    "request_id": "request-1",
                    "event_type": "api_request",
                }
            )
        )

    def test_real_schema_accepts_guardrail_decision_event(self) -> None:
        event = build_guardrail_decision_log(
            feature="face",
            decision="restrict",
            risk_level="HIGH",
            rules=["G04"],
            policy_version="1.1",
            phase="input",
        )

        parsed = parse_was_log(
            json.dumps(event).encode("utf-8"), load_schema_validator()
        )

        self.assertEqual(parsed["guardrail"], event["guardrail"])

    def test_real_schema_rejects_incomplete_guardrail_decision(self) -> None:
        event = build_guardrail_decision_log(
            feature="face",
            decision="restrict",
            risk_level="HIGH",
            rules=["G04"],
            policy_version="1.1",
            phase="input",
        )
        del event["guardrail"]["phase"]

        with self.assertRaises(InvalidWasLog):
            parse_was_log(json.dumps(event).encode("utf-8"), load_schema_validator())

    def test_ai_request_example_matches_empty_input_contract(self) -> None:
        payload = (BASE_DIR / "schemas" / "examples" / "was-ai-request.json").read_bytes()

        event = parse_was_log(payload, load_schema_validator())

        self.assertEqual(event["event_type"], "ai_request")
        self.assertEqual(event["input"], {})


if __name__ == "__main__":
    unittest.main()
