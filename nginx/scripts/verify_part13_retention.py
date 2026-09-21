#!/usr/bin/env python3
"""Part 13-10 DB, Loki, notification-history, and timer verification."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from security_sink.loki_verification import verify_loki_runtime  # noqa: E402
from security_sink.retention import run_retention_cleanup, verify_retention  # noqa: E402
from security_sink.runtime import mysql_connection  # noqa: E402


FIXTURE_COUNTS = {
    "security_event": (
        "SELECT COUNT(*) FROM security_event "
        "WHERE event_id LIKE 'part13-retention-%'"
    ),
    "security_event_detection": (
        "SELECT COUNT(*) FROM security_event_detection d "
        "JOIN security_event e ON e.id=d.security_event_id "
        "WHERE e.event_id LIKE 'part13-retention-%'"
    ),
    "security_event_action": (
        "SELECT COUNT(*) FROM security_event_action a "
        "JOIN security_event e ON e.id=a.security_event_id "
        "WHERE e.event_id LIKE 'part13-retention-%'"
    ),
    "kafka_consumption": (
        "SELECT COUNT(*) FROM kafka_consumption "
        "WHERE consumer_group='part13-retention-fixture'"
    ),
    "consumer_failure": (
        "SELECT COUNT(*) FROM consumer_failure "
        "WHERE consumer_group='part13-retention-fixture'"
    ),
    "notification_log": (
        "SELECT COUNT(*) FROM notification_log "
        "WHERE dedup_key LIKE 'part13-retention-%'"
    ),
}


def fixture_counts() -> dict[str, int]:
    connection = mysql_connection()
    try:
        with connection.cursor() as cursor:
            result = {}
            for name, query in FIXTURE_COUNTS.items():
                cursor.execute(query)
                result[name] = int(cursor.fetchone()[0])
            return result
    finally:
        connection.close()


def systemctl_state(unit: str, operation: str) -> str:
    process = subprocess.run(
        ["systemctl", operation, unit],
        check=False,
        capture_output=True,
        text=True,
    )
    return (process.stdout or process.stderr).strip()


def batch_json(batch: Any) -> dict[str, Any]:
    return {
        "candidates": batch.candidates,
        "deleted": batch.deleted,
        "total_candidates": batch.total_candidates,
        "total_deleted": batch.total_deleted,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="execute bounded retention deletion after the dry-run",
    )
    parser.add_argument("--loki-url", default="http://127.0.0.1:3100")
    args = parser.parse_args()

    before = fixture_counts()
    dry_run = run_retention_cleanup(
        mysql_connection, batch_size=1000, max_batches=1, dry_run=True
    )[0]
    loki = verify_loki_runtime(args.loki_url, require_logs=False)
    timer = {
        "enabled": systemctl_state("security-retention.timer", "is-enabled"),
        "active": systemctl_state("security-retention.timer", "is-active"),
    }
    report: dict[str, Any] = {
        "mode": "execute" if args.execute else "dry-run",
        "timer": timer,
        "fixture_before": before,
        "dry_run": batch_json(dry_run),
        "loki": {
            "status": "ready",
            "retention_hours": loki.retention_hours,
            "masked_log_count": loki.log_count,
        },
    }

    if not args.execute:
        report["status"] = "ready-to-execute" if all(before.values()) else "fixture-missing"
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 0 if all(before.values()) else 1

    if not all(before.values()):
        report["status"] = "fixture-missing"
        print(json.dumps(report, ensure_ascii=False, sort_keys=True))
        return 1

    batches = run_retention_cleanup(
        mysql_connection, batch_size=1000, max_batches=10, dry_run=False
    )
    after = fixture_counts()
    overdue = verify_retention(mysql_connection).overdue
    report["execute_batches"] = [batch_json(batch) for batch in batches]
    report["fixture_after"] = after
    report["overdue_after"] = overdue
    passed = (
        all(value == 0 for value in after.values())
        and all(value == 0 for value in overdue.values())
        and timer == {"enabled": "enabled", "active": "active"}
    )
    report["status"] = "ok" if passed else "failed"
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
