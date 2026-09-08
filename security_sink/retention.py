"""Verification and bounded cleanup for security-monitoring retention data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


MAX_BATCH_SIZE = 10_000

RETENTION_QUERIES = {
    "security_event_365d": (
        "SELECT COUNT(*) FROM security_event e "
        "WHERE e.detected_at < UTC_TIMESTAMP(3) - INTERVAL 365 DAY "
        "AND NOT EXISTS (SELECT 1 FROM notification_log n "
        "WHERE n.event_id = e.event_id "
        "AND n.status IN ('PENDING','SENDING','FAILED'))"
    ),
    "kafka_consumption_14d": (
        "SELECT COUNT(*) FROM kafka_consumption "
        "WHERE processed_at < UTC_TIMESTAMP(3) - INTERVAL 14 DAY"
    ),
    "consumer_failure_90d": (
        "SELECT COUNT(*) FROM consumer_failure "
        "WHERE last_failed_at < UTC_TIMESTAMP(3) - INTERVAL 90 DAY "
        "AND retry_status IN ('RECOVERED','DLQ','DISCARDED')"
    ),
    "notification_log_90d": (
        "SELECT COUNT(*) FROM notification_log "
        "WHERE updated_at < UTC_TIMESTAMP(3) - INTERVAL 90 DAY "
        "AND status IN ('SENT','SUPPRESSED')"
    ),
}

_SELECT_IDS = {
    "notification_log_90d": (
        "SELECT id FROM notification_log "
        "WHERE updated_at < UTC_TIMESTAMP(3) - INTERVAL 90 DAY "
        "AND status IN ('SENT','SUPPRESSED') "
        "ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED"
    ),
    "consumer_failure_90d": (
        "SELECT id FROM consumer_failure "
        "WHERE last_failed_at < UTC_TIMESTAMP(3) - INTERVAL 90 DAY "
        "AND retry_status IN ('RECOVERED','DLQ','DISCARDED') "
        "ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED"
    ),
    "kafka_consumption_14d": (
        "SELECT id FROM kafka_consumption "
        "WHERE processed_at < UTC_TIMESTAMP(3) - INTERVAL 14 DAY "
        "ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED"
    ),
    "security_event_365d": (
        "SELECT e.id FROM security_event e "
        "WHERE e.detected_at < UTC_TIMESTAMP(3) - INTERVAL 365 DAY "
        "AND NOT EXISTS (SELECT 1 FROM notification_log n "
        "WHERE n.event_id = e.event_id "
        "AND n.status IN ('PENDING','SENDING','FAILED')) "
        "ORDER BY e.id LIMIT %s FOR UPDATE SKIP LOCKED"
    ),
}

_TABLE_BY_POLICY = {
    "notification_log_90d": "notification_log",
    "consumer_failure_90d": "consumer_failure",
    "kafka_consumption_14d": "kafka_consumption",
}


@dataclass(frozen=True)
class RetentionVerification:
    overdue: dict[str, int]

    @property
    def passed(self) -> bool:
        return all(count == 0 for count in self.overdue.values())


@dataclass(frozen=True)
class RetentionBatchResult:
    candidates: dict[str, int]
    deleted: dict[str, int]
    dry_run: bool

    @property
    def total_candidates(self) -> int:
        return sum(self.candidates.values())

    @property
    def total_deleted(self) -> int:
        return sum(self.deleted.values())


def _validated_batch_size(batch_size: int) -> int:
    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(f"batch_size must be between 1 and {MAX_BATCH_SIZE}")
    return batch_size


def _select_ids(cursor: Any, policy: str, batch_size: int) -> list[int]:
    cursor.execute(_SELECT_IDS[policy], (batch_size,))
    return [int(row[0]) for row in cursor.fetchall()]


def _delete_ids(
    cursor: Any, table: str, ids: list[int], *, column: str = "id"
) -> int:
    if not ids:
        return 0
    placeholders = ",".join(["%s"] * len(ids))
    cursor.execute(
        f"DELETE FROM {table} WHERE {column} IN ({placeholders})", tuple(ids)
    )
    return int(cursor.rowcount)


def run_retention_batch(
    connection_factory: Callable[[], Any],
    *,
    batch_size: int = 1_000,
    dry_run: bool = True,
) -> RetentionBatchResult:
    """Inspect or delete one bounded batch for every retention policy."""

    batch_size = _validated_batch_size(batch_size)
    connection = connection_factory()
    candidates: dict[str, int] = {}
    deleted: dict[str, int] = {}
    try:
        connection.begin()
        with connection.cursor() as cursor:
            selected: dict[str, list[int]] = {}
            for policy in _SELECT_IDS:
                ids = _select_ids(cursor, policy, batch_size)
                selected[policy] = ids
                candidates[policy] = len(ids)

            if dry_run:
                connection.rollback()
                return RetentionBatchResult(candidates, deleted, True)

            for policy, table in _TABLE_BY_POLICY.items():
                deleted[table] = _delete_ids(cursor, table, selected[policy])

            event_ids = selected["security_event_365d"]
            deleted["security_event_detection"] = _delete_ids(
                cursor,
                "security_event_detection",
                event_ids,
                column="security_event_id",
            )
            deleted["security_event_action"] = _delete_ids(
                cursor,
                "security_event_action",
                event_ids,
                column="security_event_id",
            )
            deleted["security_event"] = _delete_ids(cursor, "security_event", event_ids)
        connection.commit()
        return RetentionBatchResult(candidates, deleted, False)
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def run_retention_cleanup(
    connection_factory: Callable[[], Any],
    *,
    batch_size: int = 1_000,
    max_batches: int = 10,
    dry_run: bool = True,
) -> list[RetentionBatchResult]:
    if max_batches < 1:
        raise ValueError("max_batches must be at least 1")
    results: list[RetentionBatchResult] = []
    for _ in range(max_batches):
        result = run_retention_batch(
            connection_factory, batch_size=batch_size, dry_run=dry_run
        )
        results.append(result)
        if dry_run or result.total_candidates == 0:
            break
    return results


def verify_retention(connection_factory: Callable[[], Any]) -> RetentionVerification:
    connection = connection_factory()
    try:
        overdue: dict[str, int] = {}
        with connection.cursor() as cursor:
            for policy, query in RETENTION_QUERIES.items():
                cursor.execute(query)
                overdue[policy] = int(cursor.fetchone()[0])
        return RetentionVerification(overdue)
    finally:
        connection.close()
