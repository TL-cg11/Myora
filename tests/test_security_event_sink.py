from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from security_sink.common import KafkaMetadata
from security_sink.security_events import SecurityEventRepository, SecurityEventSink


ROOT = Path(__file__).resolve().parents[1]


def fixture() -> dict:
    with (ROOT / "fixtures" / "luck.security-events.normal.json").open(
        encoding="utf-8"
    ) as handle:
        return json.load(handle)


def metadata(*, offset: int = 7) -> KafkaMetadata:
    return KafkaMetadata(
        consumer_group="security-event-sink",
        topic="myohan.security-events",
        partition=2,
        offset=offset,
        key="sec_evt_fixture_0001",
    )


class FakeCursor:
    def __init__(self, connection: "FakeConnection") -> None:
        self.connection = connection
        self.lastrowid = 41
        self._row: tuple[int] | None = None

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def execute(self, sql: str, values: tuple[object, ...]) -> None:
        if self.connection.fail_on_detection and "security_event_detection" in sql:
            raise RuntimeError("simulated detection insert failure")
        if self.connection.fail_on_notification and "notification_log" in sql:
            raise RuntimeError("simulated notification insert failure")
        self.connection.executions.append((sql, values))
        if "FROM kafka_consumption" in sql:
            self._row = (90,) if self.connection.consumed else None
        elif "FROM security_event WHERE" in sql:
            self._row = (
                (self.connection.existing_event_id,)
                if self.connection.existing_event_id is not None
                else None
            )
        else:
            self._row = None

    def fetchone(self) -> tuple[int] | None:
        return self._row


class FakeConnection:
    def __init__(
        self,
        *,
        fail_on_detection: bool = False,
        fail_on_notification: bool = False,
        consumed: bool = False,
        existing_event_id: int | None = None,
    ) -> None:
        self.fail_on_detection = fail_on_detection
        self.fail_on_notification = fail_on_notification
        self.consumed = consumed
        self.existing_event_id = existing_event_id
        self.executions: list[tuple[str, tuple[object, ...]]] = []
        self.begun = False
        self.committed = False
        self.rolled_back = False
        self.closed = False

    def begin(self) -> None:
        self.begun = True

    def cursor(self) -> FakeCursor:
        return FakeCursor(self)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def close(self) -> None:
        self.closed = True


class SecurityEventSinkTests(unittest.TestCase):
    def test_micro_batch_uses_one_transaction_and_bulk_writes(self) -> None:
        class BatchCursor:
            def __init__(self, connection):
                self.connection = connection
                self.rows = []

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return None

            def execute(self, sql, values):
                self.connection.executions.append((sql, values))
                if "FROM kafka_consumption WHERE" in sql:
                    self.rows = []
                elif "SELECT event_id,id FROM security_event" in sql:
                    self.rows = list(self.connection.event_ids.items())
                else:
                    self.rows = []

            def executemany(self, sql, values):
                rows = list(values)
                self.connection.bulk_executions.append((sql, rows))
                if sql.startswith("INSERT INTO security_event ("):
                    for row in rows:
                        self.connection.event_ids[row[0]] = 100 + len(self.connection.event_ids)

            def fetchall(self):
                return self.rows

        class BatchConnection:
            def __init__(self):
                self.executions = []
                self.bulk_executions = []
                self.event_ids = {}
                self.begins = 0
                self.commits = 0

            def begin(self):
                self.begins += 1

            def cursor(self):
                return BatchCursor(self)

            def commit(self):
                self.commits += 1

            def rollback(self):
                raise AssertionError("batch should not roll back")

            def close(self):
                return None

        first = fixture()
        second = copy.deepcopy(first)
        second["event_id"] = "sec_evt_fixture_0002"
        second["source_event_id"] = "raw_evt_fixture_0002"
        second["request_id"] = "req_fixture_0002"
        second["detections"][0]["detection_id"] = "det_fixture_0002"
        connection = BatchConnection()
        repository = SecurityEventRepository(lambda: connection)

        results = repository.save_batch(
            [
                (first, metadata(offset=7), "a" * 64),
                (second, metadata(offset=8), "b" * 64),
            ]
        )

        self.assertEqual(connection.begins, 1)
        self.assertEqual(connection.commits, 1)
        self.assertEqual([result.duplicate for result in results], [None, None])
        consumption_batches = [
            rows
            for sql, rows in connection.bulk_executions
            if "INSERT INTO kafka_consumption" in sql
        ]
        self.assertEqual(len(consumption_batches), 1)
        self.assertEqual(len(consumption_batches[0]), 2)

    def test_event_children_action_and_offset_are_one_transaction(self) -> None:
        connection = FakeConnection()
        sink = SecurityEventSink(SecurityEventRepository(lambda: connection))

        result = sink.handle(json.dumps(fixture()).encode(), metadata())

        self.assertEqual(result.event_db_id, 41)
        self.assertIsNone(result.duplicate)
        self.assertTrue(connection.begun)
        self.assertTrue(connection.committed)
        self.assertFalse(connection.rolled_back)
        self.assertTrue(connection.closed)
        self.assertEqual(len(connection.executions), 8)
        self.assertIn("FROM kafka_consumption", connection.executions[0][0])
        self.assertIn("FROM security_event WHERE", connection.executions[1][0])
        self.assertIn("INSERT INTO security_event (", connection.executions[2][0])
        self.assertIn("security_event_detection", connection.executions[3][0])
        self.assertIn("security_event_detection", connection.executions[4][0])
        self.assertIn("security_event_action", connection.executions[5][0])
        self.assertEqual(connection.executions[5][1], (41, "SYSTEM", "security-event-sink"))
        notifications = connection.executions[6:7]
        self.assertTrue(all("INSERT IGNORE INTO notification_log" in sql for sql, _ in notifications))
        self.assertEqual(
            {values[2] for _, values in notifications},
            {"SECURITY_EVENT"},
        )
        self.assertEqual({values[3] for _, values in notifications}, {"DISCORD"})
        self.assertIn("INSERT INTO kafka_consumption", connection.executions[7][0])
        self.assertEqual(connection.executions[7][1][0:4], metadata().identity_values())
        self.assertEqual(len(str(connection.executions[7][1][5])), 64)

    def test_duplicate_offset_skips_all_writes(self) -> None:
        connection = FakeConnection(consumed=True)
        sink = SecurityEventSink(SecurityEventRepository(lambda: connection))

        result = sink.handle(fixture(), metadata())

        self.assertEqual(result.duplicate, "offset")
        self.assertIsNone(result.event_db_id)
        self.assertEqual(len(connection.executions), 1)
        self.assertTrue(connection.committed)

    def test_duplicate_event_records_new_offset_without_child_rows(self) -> None:
        connection = FakeConnection(existing_event_id=77)
        sink = SecurityEventSink(SecurityEventRepository(lambda: connection))

        result = sink.handle(fixture(), metadata(offset=8))

        self.assertEqual(result.duplicate, "event_id")
        self.assertEqual(result.event_db_id, 77)
        self.assertEqual(len(connection.executions), 3)
        self.assertIn("INSERT INTO kafka_consumption", connection.executions[2][0])
        self.assertTrue(connection.committed)

    def test_detection_insert_failure_rolls_back_event_and_offset(self) -> None:
        connection = FakeConnection(fail_on_detection=True)
        sink = SecurityEventSink(SecurityEventRepository(lambda: connection))

        with self.assertRaisesRegex(RuntimeError, "detection insert failure"):
            sink.handle(fixture(), metadata())

        self.assertFalse(connection.committed)
        self.assertTrue(connection.rolled_back)
        self.assertTrue(connection.closed)
        self.assertFalse(
            any("INSERT INTO kafka_consumption" in sql for sql, _ in connection.executions)
        )

    def test_notification_insert_failure_rolls_back_event_and_offset(self) -> None:
        connection = FakeConnection(fail_on_notification=True)
        sink = SecurityEventSink(SecurityEventRepository(lambda: connection))

        with self.assertRaisesRegex(RuntimeError, "notification insert failure"):
            sink.handle(fixture(), metadata())

        self.assertFalse(connection.committed)
        self.assertTrue(connection.rolled_back)
        self.assertFalse(
            any("INSERT INTO kafka_consumption" in sql for sql, _ in connection.executions)
        )

    def test_invalid_contract_is_rejected_before_db_connection(self) -> None:
        opened = False

        def connection_factory() -> FakeConnection:
            nonlocal opened
            opened = True
            return FakeConnection()

        invalid = copy.deepcopy(fixture())
        del invalid["event_id"]
        sink = SecurityEventSink(SecurityEventRepository(connection_factory))

        with self.assertRaisesRegex(ValueError, "event_id"):
            sink.handle(invalid, metadata())
        self.assertFalse(opened)

    def test_unmasked_sensitive_excerpt_is_rejected_before_db(self) -> None:
        opened = False

        def connection_factory() -> FakeConnection:
            nonlocal opened
            opened = True
            return FakeConnection()

        with (
            ROOT / "fixtures" / "luck.security-events.sensitive-unmasked.json"
        ).open(encoding="utf-8") as handle:
            sensitive = json.load(handle)
        sink = SecurityEventSink(SecurityEventRepository(connection_factory))

        with self.assertRaisesRegex(ValueError, "unmasked sensitive"):
            sink.handle(sensitive, metadata())
        self.assertFalse(opened)


if __name__ == "__main__":
    unittest.main()
