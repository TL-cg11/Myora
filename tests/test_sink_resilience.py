from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from security_sink.common import KafkaMetadata, ProcessResult
from security_sink.resilience import (
    DlqPublisher,
    FailureDetails,
    FailureRepository,
    FilesystemBuffer,
    ResilientProcessor,
    TerminalConsumptionRepository,
)


def metadata(topic: str = "luck.masked-logs") -> KafkaMetadata:
    return KafkaMetadata(
        consumer_group="masked-log-sink",
        topic=topic,
        partition=1,
        offset=23,
        key="raw_evt_fixture_0001",
    )


def raw_payload() -> bytes:
    return json.dumps(
        {
            "event_id": "raw_evt_fixture_0001",
            "schema_version": "1.0",
            "masked_message": "contact=[PHONE_NUMBER]",
        }
    ).encode()


class FakeFailures:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.recovered: list[KafkaMetadata] = []

    def record(self, message: KafkaMetadata, **values: Any) -> None:
        self.records.append({"metadata": message, **values})

    def mark_recovered(self, message: KafkaMetadata) -> None:
        self.recovered.append(message)


class FakeTerminal:
    def __init__(self) -> None:
        self.records: list[tuple[KafkaMetadata, str, str | None]] = []

    def record_dlq(
        self, message: KafkaMetadata, payload_hash: str, event_id: str | None
    ) -> None:
        self.records.append((message, payload_hash, event_id))


class RecordingCursor:
    def __init__(self, connection: "RecordingConnection") -> None:
        self.connection = connection

    def __enter__(self) -> "RecordingCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, values: tuple[object, ...]) -> None:
        self.connection.executions.append((sql, values))


class RecordingConnection:
    def __init__(self) -> None:
        self.executions: list[tuple[str, tuple[object, ...]]] = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def begin(self) -> None:
        return None

    def cursor(self) -> RecordingCursor:
        return RecordingCursor(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class ResilientProcessorTests(unittest.TestCase):
    def make_processor(
        self,
        failures: FakeFailures,
        terminal: FakeTerminal,
        sent: list[tuple[str, str | None, bytes]],
        **options: Any,
    ) -> ResilientProcessor:
        return ResilientProcessor(
            failures,  # type: ignore[arg-type]
            terminal,  # type: ignore[arg-type]
            DlqPublisher(lambda topic, key, value: sent.append((topic, key, value))),
            **options,
        )

    def test_transient_failure_uses_exponential_retry_and_marks_recovered(self) -> None:
        failures = FakeFailures()
        terminal = FakeTerminal()
        sent: list[tuple[str, str | None, bytes]] = []
        delays: list[float] = []
        attempts = 0

        def operation() -> ProcessResult:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise ConnectionError("temporary DB outage")
            return ProcessResult(event_db_id=10)

        processor = self.make_processor(
            failures, terminal, sent, sleeper=delays.append
        )
        result = processor.execute(operation, raw_payload(), metadata())

        self.assertEqual(result.event_db_id, 10)
        self.assertEqual(attempts, 3)
        self.assertEqual(delays, [1, 2])
        self.assertEqual([item["retry_count"] for item in failures.records], [1, 2])
        self.assertEqual(failures.recovered, [metadata()])
        self.assertEqual(sent, [])
        self.assertEqual(terminal.records, [])

    def test_permanent_validation_failure_goes_directly_to_sanitized_dlq(self) -> None:
        failures = FakeFailures()
        terminal = FakeTerminal()
        sent: list[tuple[str, str | None, bytes]] = []
        processor = self.make_processor(failures, terminal, sent)

        result = processor.execute(
            lambda: (_ for _ in ()).throw(ValueError("raw secret sk-not-in-dlq")),
            raw_payload(),
            metadata(),
        )

        self.assertEqual(result.duplicate, "dlq")
        self.assertEqual(len(sent), 1)
        self.assertEqual(sent[0][0], "luck.masked-logs.sink-dlq")
        envelope = json.loads(sent[0][2])
        self.assertNotIn("raw_value", envelope)
        self.assertNotIn("sk-not-in-dlq", sent[0][2].decode())
        self.assertEqual(envelope["retry_count"], 0)
        self.assertEqual(failures.records[-1]["status"], "DLQ")
        self.assertEqual(len(terminal.records), 1)

    def test_sensitive_message_key_is_hashed_in_dlq(self) -> None:
        failures = FakeFailures()
        terminal = FakeTerminal()
        sent: list[tuple[str, str | None, bytes]] = []
        processor = self.make_processor(failures, terminal, sent)
        sensitive_metadata = KafkaMetadata(
            consumer_group="masked-log-sink",
            topic="luck.masked-logs",
            partition=1,
            offset=24,
            key="api_key=sk-sensitive-key-value",
        )

        processor.execute(
            lambda: (_ for _ in ()).throw(ValueError("invalid contract")),
            raw_payload(),
            sensitive_metadata,
        )

        envelope = json.loads(sent[0][2])
        self.assertTrue(envelope["message_key"].startswith("sha256:"))
        self.assertEqual(sent[0][1], envelope["message_key"])
        self.assertNotIn("sk-sensitive", sent[0][2].decode())

    def test_exhausted_loki_retries_are_buffered_then_sent_to_dlq(self) -> None:
        failures = FakeFailures()
        terminal = FakeTerminal()
        sent: list[tuple[str, str | None, bytes]] = []
        delays: list[float] = []
        attempts = 0

        def operation() -> ProcessResult:
            nonlocal attempts
            attempts += 1
            raise ConnectionError("Loki unavailable")

        with tempfile.TemporaryDirectory() as directory:
            buffer = FilesystemBuffer(Path(directory), max_bytes=100_000)
            processor = self.make_processor(
                failures,
                terminal,
                sent,
                sleeper=delays.append,
                buffer=buffer,
            )
            result = processor.execute(operation, raw_payload(), metadata())
            entries = buffer.entries()

            self.assertEqual(result.duplicate, "dlq")
            self.assertEqual(attempts, 6)
            self.assertEqual(delays, [1, 2, 4, 8, 16])
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].raw_value, raw_payload())
            self.assertEqual(entries[0].metadata, metadata())
            self.assertEqual(len(sent), 1)
            self.assertEqual(failures.records[-1]["retry_count"], 5)
            self.assertEqual(failures.records[-1]["status"], "DLQ")
            self.assertEqual(len(terminal.records), 1)

            buffer.acknowledge(entries[0])
            self.assertEqual(buffer.entries(), [])

    def test_filesystem_buffer_limit_applies_backpressure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            buffer = FilesystemBuffer(Path(directory), max_bytes=10)
            with self.assertRaisesRegex(OSError, "size limit"):
                buffer.store(metadata(), raw_payload())

    def test_retry_and_dlq_callbacks_receive_sanitized_stage(self) -> None:
        failures = FakeFailures()
        terminal = FakeTerminal()
        sent: list[tuple[str, str | None, bytes]] = []
        retries: list[str] = []
        dlqs: list[str] = []
        processor = self.make_processor(
            failures,
            terminal,
            sent,
            max_retries=1,
            sleeper=lambda _delay: None,
            on_retry=lambda _metadata, details: retries.append(details.stage),
            on_dlq=lambda _metadata, details: dlqs.append(details.stage),
        )

        processor.execute(
            lambda: (_ for _ in ()).throw(ConnectionError("private detail")),
            raw_payload(),
            metadata(),
        )

        self.assertEqual(retries, ["sink_processing"])
        self.assertEqual(dlqs, ["sink_processing"])


class FailureRepositoryTests(unittest.TestCase):
    def test_failure_is_upserted_and_can_be_marked_recovered(self) -> None:
        first = RecordingConnection()
        second = RecordingConnection()
        connections = iter([first, second])
        repository = FailureRepository(lambda: next(connections))
        details = FailureDetails(
            "sink_processing", "TRANSIENT_SINK_FAILURE", "temporary error", False
        )

        repository.record(
            metadata(),
            event_id="raw_evt_fixture_0001",
            payload_hash="a" * 64,
            details=details,
            retry_count=2,
            status="RETRYING",
        )
        repository.mark_recovered(metadata())

        self.assertIn("ON DUPLICATE KEY UPDATE", first.executions[0][0])
        self.assertEqual(first.executions[0][1][-2:], (2, "RETRYING"))
        self.assertTrue(first.committed)
        self.assertIn("UPDATE consumer_failure", second.executions[0][0])
        self.assertTrue(second.committed)

    def test_terminal_dlq_consumption_uses_dlq_status(self) -> None:
        connection = RecordingConnection()
        repository = TerminalConsumptionRepository(lambda: connection)

        repository.record_dlq(metadata(), "b" * 64, "raw_evt_fixture_0001")

        self.assertIn("INSERT INTO kafka_consumption", connection.executions[0][0])
        self.assertEqual(connection.executions[0][1][-1], "DLQ")
        self.assertTrue(connection.committed)


if __name__ == "__main__":
    unittest.main()
