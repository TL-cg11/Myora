"""Persist validated ``luck.security-events`` messages in MariaDB."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable

from security_sink.common import (
    INSERT_CONSUMPTION,
    SELECT_CONSUMPTION_FOR_UPDATE,
    KafkaMetadata,
    ProcessResult,
    sha256_hex,
    validate_masking_safety,
)
from security_sink.notification_policy import DEFAULT_POLICY, NotificationPolicy, configured_channels, queue_rows
from security_sink.notifications import INSERT_NOTIFICATION
from scripts.mock_security_producer import validate


TOPIC = "luck.security-events"
CREATED_ACTOR_TYPE = "SYSTEM"
CREATED_ACTOR_ID = "security-event-sink"

INSERT_EVENT = """
INSERT INTO security_event (
    event_id, source_event_id, request_id, schema_version, occurred_at,
    detected_at, environment, source_service, source_type, event_name,
    risk_level, risk_score, detector_version, masking_policy_version,
    masked_excerpt, body_hash, safe_metadata
) VALUES (
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s,
    %s, %s, %s, %s,
    %s, %s, %s
)
""".strip()

INSERT_DETECTION = """
INSERT INTO security_event_detection (
    security_event_id, detection_id, rule_id, rule_version, category,
    entity_type, risk_level, confidence, match_count,
    evidence_fingerprint, locations_json
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
""".strip()

INSERT_CREATED_ACTION = """
INSERT INTO security_event_action (
    security_event_id, action_type, actor_type, actor_id, new_status
) VALUES (%s, 'CREATED', %s, %s, 'OPEN')
""".strip()

SELECT_EVENT = """
SELECT id FROM security_event WHERE event_id = %s LIMIT 1 FOR UPDATE
""".strip()


def _utc_datetime(value: str) -> datetime:
    """Convert a contract UTC timestamp to a naive UTC MariaDB DATETIME."""
    parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    return parsed.astimezone(timezone.utc).replace(tzinfo=None)


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


class SecurityEventRepository:
    """MariaDB transaction boundary for one security event message."""

    def __init__(
        self,
        connection_factory: Callable[[], Any],
        notification_policy: NotificationPolicy = DEFAULT_POLICY,
        notification_channels: tuple[str, ...] | None = None,
    ) -> None:
        self._connection_factory = connection_factory
        self._notification_policy = notification_policy
        self._notification_channels = notification_channels or configured_channels()

    def save(
        self,
        event: dict[str, Any],
        metadata: KafkaMetadata,
        payload_hash: str,
    ) -> ProcessResult:
        connection = self._connection_factory()
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute(
                    SELECT_CONSUMPTION_FOR_UPDATE, metadata.identity_values()
                )
                consumed = cursor.fetchone()
                if consumed:
                    connection.commit()
                    return ProcessResult(event_db_id=None, duplicate="offset")

                cursor.execute(SELECT_EVENT, (event["event_id"],))
                existing_event = cursor.fetchone()
                if existing_event:
                    security_event_id = int(existing_event[0])
                    cursor.execute(
                        INSERT_CONSUMPTION,
                        metadata.consumption_values(payload_hash, event["event_id"]),
                    )
                    connection.commit()
                    return ProcessResult(
                        event_db_id=security_event_id, duplicate="event_id"
                    )

                cursor.execute(INSERT_EVENT, self._event_values(event))
                security_event_id = int(cursor.lastrowid)

                for detection in event["detections"]:
                    cursor.execute(
                        INSERT_DETECTION,
                        self._detection_values(security_event_id, detection),
                    )

                cursor.execute(
                    INSERT_CREATED_ACTION,
                    (security_event_id, CREATED_ACTOR_TYPE, CREATED_ACTOR_ID),
                )
                for notification in queue_rows(
                    event, self._notification_channels, self._notification_policy
                ):
                    cursor.execute(INSERT_NOTIFICATION, notification)
                cursor.execute(
                    INSERT_CONSUMPTION,
                    metadata.consumption_values(payload_hash, event["event_id"]),
                )
            connection.commit()
            return ProcessResult(event_db_id=security_event_id)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    @staticmethod
    def _event_values(event: dict[str, Any]) -> tuple[Any, ...]:
        return (
            event["event_id"],
            event["source_event_id"],
            event.get("request_id"),
            event["schema_version"],
            _utc_datetime(event["occurred_at"]),
            _utc_datetime(event["detected_at"]),
            event["environment"],
            event["source_service"],
            event["source_type"],
            event.get("event_name"),
            event["risk_level"],
            event["risk_score"],
            event["detector_version"],
            event["masking_policy_version"],
            event.get("masked_excerpt"),
            event.get("body_hash"),
            _json(event.get("safe_metadata")),
        )

    @staticmethod
    def _detection_values(
        security_event_id: int, detection: dict[str, Any]
    ) -> tuple[Any, ...]:
        return (
            security_event_id,
            detection["detection_id"],
            detection["rule_id"],
            detection["rule_version"],
            detection["category"],
            detection["entity_type"],
            detection["risk_level"],
            detection["confidence"],
            detection["match_count"],
            detection.get("evidence_fingerprint"),
            _json(detection.get("locations_json")),
        )


class SecurityEventSink:
    """Validate and store one Kafka message value."""

    def __init__(self, repository: SecurityEventRepository) -> None:
        self._repository = repository

    def handle(
        self,
        raw_value: bytes | str | dict[str, Any],
        metadata: KafkaMetadata,
    ) -> ProcessResult:
        if metadata.topic != TOPIC:
            raise ValueError(f"unexpected topic for security event sink: {metadata.topic}")
        if isinstance(raw_value, dict):
            raw_bytes = json.dumps(
                raw_value, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            event = raw_value
        else:
            raw_bytes = raw_value.encode("utf-8") if isinstance(raw_value, str) else raw_value
            event = json.loads(raw_bytes.decode("utf-8"))
        if not isinstance(event, dict):
            raise ValueError("security event payload must be a JSON object")
        validate(TOPIC, event)
        validate_masking_safety(event)
        return self._repository.save(event, metadata, sha256_hex(raw_bytes))
