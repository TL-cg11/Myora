from __future__ import annotations

import unittest
from pathlib import Path

from security_sink.retention import (
    MAX_BATCH_SIZE,
    RETENTION_QUERIES,
    run_retention_batch,
    run_retention_cleanup,
)


class FakeCursor:
    def __init__(self, selected, fail_on: str | None = None):
        self.selected = iter(selected)
        self.fail_on = fail_on
        self.executed: list[tuple[str, tuple | None]] = []
        self.rows = []
        self.rowcount = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, query, params=None):
        normalized = " ".join(query.split())
        self.executed.append((normalized, params))
        if self.fail_on and self.fail_on in normalized:
            raise RuntimeError("injected delete failure")
        if normalized.startswith("SELECT"):
            self.rows = [(value,) for value in next(self.selected)]
            self.rowcount = len(self.rows)
        else:
            self.rowcount = len(params or ())

    def fetchall(self):
        return self.rows


class FakeConnection:
    def __init__(self, selected, fail_on: str | None = None):
        self.cursor_value = FakeCursor(selected, fail_on)
        self.begun = False
        self.committed = False
        self.rollbacks = 0
        self.closed = False

    def begin(self):
        self.begun = True

    def cursor(self):
        return self.cursor_value

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


class RetentionCleanupTests(unittest.TestCase):
    def selected(self):
        return [[11], [21], [31], [41, 42]]

    def test_execute_deletes_event_children_before_parent_and_commits(self):
        connection = FakeConnection(self.selected())

        result = run_retention_batch(lambda: connection, batch_size=100, dry_run=False)

        deletes = [
            query
            for query, _params in connection.cursor_value.executed
            if query.startswith("DELETE")
        ]
        self.assertLess(
            deletes.index("DELETE FROM security_event_detection WHERE security_event_id IN (%s,%s)"),
            deletes.index("DELETE FROM security_event WHERE id IN (%s,%s)"),
        )
        self.assertLess(
            deletes.index("DELETE FROM security_event_action WHERE security_event_id IN (%s,%s)"),
            deletes.index("DELETE FROM security_event WHERE id IN (%s,%s)"),
        )
        self.assertTrue(connection.committed)
        self.assertEqual(connection.rollbacks, 0)
        self.assertEqual(result.candidates["security_event_365d"], 2)
        self.assertEqual(result.deleted["security_event"], 2)

    def test_dry_run_selects_candidates_without_delete(self):
        connection = FakeConnection(self.selected())

        result = run_retention_batch(lambda: connection, dry_run=True)

        self.assertTrue(result.dry_run)
        self.assertEqual(result.total_candidates, 5)
        self.assertEqual(result.total_deleted, 0)
        self.assertEqual(connection.rollbacks, 1)
        self.assertFalse(connection.committed)
        self.assertFalse(
            any(query.startswith("DELETE") for query, _ in connection.cursor_value.executed)
        )

    def test_failure_rolls_back_whole_event_transaction(self):
        connection = FakeConnection(
            self.selected(), fail_on="DELETE FROM security_event_action"
        )

        with self.assertRaisesRegex(RuntimeError, "injected"):
            run_retention_batch(lambda: connection, dry_run=False)

        self.assertEqual(connection.rollbacks, 1)
        self.assertFalse(connection.committed)
        self.assertTrue(connection.closed)

    def test_batch_limits_are_enforced(self):
        with self.assertRaisesRegex(ValueError, "batch_size"):
            run_retention_batch(lambda: None, batch_size=0)
        with self.assertRaisesRegex(ValueError, "batch_size"):
            run_retention_batch(lambda: None, batch_size=MAX_BATCH_SIZE + 1)
        with self.assertRaisesRegex(ValueError, "max_batches"):
            run_retention_cleanup(lambda: None, max_batches=0)

    def test_active_workflows_are_excluded_from_retention(self):
        self.assertIn(
            "retry_status IN ('RECOVERED','DLQ','DISCARDED')",
            RETENTION_QUERIES["consumer_failure_90d"],
        )
        self.assertIn(
            "n.status IN ('PENDING','SENDING','FAILED')",
            RETENTION_QUERIES["security_event_365d"],
        )

    def test_systemd_timer_runs_bounded_execute_mode(self):
        root = Path(__file__).resolve().parents[1]
        service = (root / "observability/systemd/security-retention.service").read_text()
        timer = (root / "observability/systemd/security-retention.timer").read_text()
        self.assertIn("--execute --batch-size 1000 --max-batches 10", service)
        self.assertIn("Type=oneshot", service)
        self.assertIn("OnCalendar=", timer)
        self.assertIn("Persistent=true", timer)


if __name__ == "__main__":
    unittest.main()
