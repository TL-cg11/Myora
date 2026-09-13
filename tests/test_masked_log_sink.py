from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from security_sink.common import KafkaMetadata
from security_sink.masked_logs import ConsumptionRepository, LokiClient, MaskedLogSink
from security_sink.resilience import FilesystemBuffer


ROOT = Path(__file__).resolve().parents[1]


def fixture() -> dict:
    with (ROOT / "fixtures" / "luck.masked-logs.normal.json").open(
        encoding="utf-8"
    ) as handle:
        return json.load(handle)


def metadata() -> KafkaMetadata:
    return KafkaMetadata(
        consumer_group="masked-log-sink",
        topic="myohan.masked-logs",
        partition=1,
        offset=19,
        key="raw_evt_fixture_0001",
    )


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, values: tuple[object, ...]) -> None:
        self.connection.executions.append((sql, values))

    def fetchone(self) -> tuple[int] | None:
        return (1,) if self.connection.consumed else None


class FakeConnection:
    def __init__(self, *, consumed: bool = False) -> None:
        self.consumed = consumed
        self.executions: list[tuple[str, tuple[object, ...]]] = []
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def begin(self) -> None:
        return None

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class MaskedLogSinkTests(unittest.TestCase):
    def test_micro_batch_uses_one_loki_push_and_one_consumption_batch(self) -> None:
        class BatchConsumption:
            def __init__(self) -> None:
                self.recorded = []

            def processed_batch(self, _items):
                return set()

            def record_processed_batch(self, items):
                self.recorded.extend(items)

        first = fixture()
        second = copy.deepcopy(first)
        second["event_id"] = "raw_evt_fixture_0002"
        sent: list[dict] = []

        def transport(_url: str, body: bytes, _timeout: float) -> None:
            sent.append(json.loads(body))

        consumption = BatchConsumption()
        sink = MaskedLogSink(consumption, LokiClient("http://loki", transport=transport))
        first_metadata = metadata()
        second_metadata = KafkaMetadata(
            consumer_group=first_metadata.consumer_group,
            topic=first_metadata.topic,
            partition=first_metadata.partition,
            offset=first_metadata.offset + 1,
            key="raw_evt_fixture_0002",
        )

        results = sink.handle_batch(
            [
                (json.dumps(first).encode(), first_metadata),
                (json.dumps(second).encode(), second_metadata),
            ]
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(len(sent), 1)
        self.assertEqual(sum(len(stream["values"]) for stream in sent[0]["streams"]), 2)
        self.assertEqual(len(consumption.recorded), 2)

    def test_loki_succeeds_before_offset_is_recorded(self) -> None:
        read_connection = FakeConnection()
        write_connection = FakeConnection()
        connections = iter([read_connection, write_connection])
        calls: list[tuple[str, bytes, float]] = []
        loki = LokiClient(
            "http://127.0.0.1:3100/",
            transport=lambda url, body, timeout: calls.append((url, body, timeout)),
        )
        sink = MaskedLogSink(
            ConsumptionRepository(lambda: next(connections)), loki
        )

        result = sink.handle(json.dumps(fixture()).encode(), metadata())

        self.assertIsNone(result.duplicate)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0], "http://127.0.0.1:3100/loki/api/v1/push")
        loki_payload = json.loads(calls[0][1])
        stream = loki_payload["streams"][0]
        self.assertEqual(stream["stream"]["pipeline"], "security-masked-logs")
        self.assertEqual(stream["stream"]["data_class"], "masked")
        self.assertEqual(stream["stream"]["source_service"], "luck-was")
        self.assertIn("[PHONE_NUMBER]", stream["values"][0][1])
        self.assertEqual(len(write_connection.executions), 1)
        self.assertIn("INSERT INTO kafka_consumption", write_connection.executions[0][0])
        self.assertTrue(write_connection.committed)

    def test_duplicate_offset_skips_loki_and_second_db_connection(self) -> None:
        read_connection = FakeConnection(consumed=True)
        calls: list[tuple[str, bytes, float]] = []
        opened = 0

        def factory() -> FakeConnection:
            nonlocal opened
            opened += 1
            return read_connection

        sink = MaskedLogSink(
            ConsumptionRepository(factory),
            LokiClient(
                "http://127.0.0.1:3100",
                transport=lambda url, body, timeout: calls.append((url, body, timeout)),
            ),
        )

        result = sink.handle(fixture(), metadata())

        self.assertEqual(result.duplicate, "offset")
        self.assertEqual(calls, [])
        self.assertEqual(opened, 1)

    def test_loki_failure_does_not_record_offset(self) -> None:
        read_connection = FakeConnection()
        opened = 0

        def factory() -> FakeConnection:
            nonlocal opened
            opened += 1
            return read_connection

        def fail_loki(_url: str, _body: bytes, _timeout: float) -> None:
            raise RuntimeError("simulated Loki failure")

        sink = MaskedLogSink(
            ConsumptionRepository(factory),
            LokiClient("http://127.0.0.1:3100", transport=fail_loki),
        )

        with self.assertRaisesRegex(RuntimeError, "Loki failure"):
            sink.handle(fixture(), metadata())

        self.assertEqual(opened, 1)
        self.assertFalse(read_connection.committed)

    def test_unmasked_sensitive_log_is_rejected_before_loki_or_db(self) -> None:
        opened = False
        calls: list[tuple[str, bytes, float]] = []

        def factory() -> FakeConnection:
            nonlocal opened
            opened = True
            return FakeConnection()

        with (
            ROOT / "fixtures" / "luck.masked-logs.sensitive-unmasked.json"
        ).open(encoding="utf-8") as handle:
            sensitive = json.load(handle)
        sink = MaskedLogSink(
            ConsumptionRepository(factory),
            LokiClient(
                "http://127.0.0.1:3100",
                transport=lambda url, body, timeout: calls.append((url, body, timeout)),
            ),
        )

        with self.assertRaisesRegex(ValueError, "unmasked sensitive"):
            sink.handle(sensitive, metadata())
        self.assertFalse(opened)
        self.assertEqual(calls, [])

    def test_buffered_log_is_replayed_and_acknowledged_after_restart(self) -> None:
        calls: list[tuple[str, bytes, float]] = []
        loki = LokiClient(
            "http://127.0.0.1:3100",
            transport=lambda url, body, timeout: calls.append((url, body, timeout)),
        )
        sink = MaskedLogSink(
            ConsumptionRepository(lambda: FakeConnection()), loki
        )
        raw_value = json.dumps(fixture()).encode()

        with tempfile.TemporaryDirectory() as directory:
            buffer = FilesystemBuffer(Path(directory), max_bytes=100_000)
            buffer.store(metadata(), raw_value)
            entry = buffer.entries()[0]

            sink.replay_buffered(entry.raw_value, entry.metadata)
            buffer.acknowledge(entry)

            self.assertEqual(len(calls), 1)
            self.assertEqual(buffer.entries(), [])


if __name__ == "__main__":
    unittest.main()
