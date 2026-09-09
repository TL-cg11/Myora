import json
import unittest

from consumer.was_kafka_consumer import InvalidWasLog, handle_was_log, parse_was_log


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


if __name__ == "__main__":
    unittest.main()
