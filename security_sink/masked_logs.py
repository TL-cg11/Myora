"""Push validated ``luck.masked-logs`` messages to Loki."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.request import Request, urlopen

from scripts.mock_security_producer import validate
from security_sink.common import (
    INSERT_CONSUMPTION,
    SELECT_CONSUMPTION,
    KafkaMetadata,
    ProcessResult,
    sha256_hex,
    validate_masking_safety,
)


TOPIC = "luck.masked-logs"


def _timestamp_ns(value: str) -> str:
    parsed = datetime.fromisoformat(value[:-1] + "+00:00").astimezone(timezone.utc)
    return str(int(parsed.timestamp()) * 1_000_000_000 + parsed.microsecond * 1_000)


def _default_transport(url: str, body: bytes, timeout: float) -> None:
    request = Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urlopen(request, timeout=timeout) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"Loki push failed with HTTP {response.status}")


class LokiClient:
    def __init__(
        self,
        base_url: str,
        *,
        timeout: float = 5.0,
        transport: Callable[[str, bytes, float], None] = _default_transport,
    ) -> None:
        self._push_url = base_url.rstrip("/") + "/loki/api/v1/push"
        self._timeout = timeout
        self._transport = transport

    def push(self, event: dict[str, Any]) -> None:
        log_line = json.dumps(
            {
                "event_id": event["event_id"],
                "request_id": event.get("request_id"),
                "masking_policy_version": event["masking_policy_version"],
                "masked_message": event["masked_message"],
                "body_hash": event.get("body_hash"),
                "safe_metadata": event.get("safe_metadata"),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
        payload = {
            "streams": [
                {
                    "stream": {
                        "environment": event["environment"],
                        "source_service": event["source_service"],
                        "source_type": event["source_type"],
                    },
                    "values": [[_timestamp_ns(event["occurred_at"]), log_line]],
                }
            ]
        }
        self._transport(
            self._push_url,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            ),
            self._timeout,
        )


class ConsumptionRepository:
    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self._connection_factory = connection_factory

    def is_processed(self, metadata: KafkaMetadata) -> bool:
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute(SELECT_CONSUMPTION, metadata.identity_values())
                return cursor.fetchone() is not None
        finally:
            connection.close()

    def record_processed(
        self,
        metadata: KafkaMetadata,
        payload_hash: str,
        event_id: str,
    ) -> None:
        connection = self._connection_factory()
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute(
                    INSERT_CONSUMPTION,
                    metadata.consumption_values(payload_hash, event_id),
                )
            connection.commit()
        except Exception as exc:
            connection.rollback()
            if getattr(exc, "args", ()) and exc.args[0] == 1062:
                if self.is_processed(metadata):
                    return
            raise
        finally:
            connection.close()


class MaskedLogSink:
    def __init__(
        self, consumption: ConsumptionRepository, loki: LokiClient
    ) -> None:
        self._consumption = consumption
        self._loki = loki

    def handle(
        self,
        raw_value: bytes | str | dict[str, Any],
        metadata: KafkaMetadata,
    ) -> ProcessResult:
        event, raw_bytes = self._validated_event(raw_value, metadata)

        if self._consumption.is_processed(metadata):
            return ProcessResult(event_db_id=None, duplicate="offset")

        payload_hash = sha256_hex(raw_bytes)
        self._loki.push(event)
        self._consumption.record_processed(metadata, payload_hash, event["event_id"])
        return ProcessResult(event_db_id=None)

    def replay_buffered(
        self, raw_value: bytes, metadata: KafkaMetadata
    ) -> None:
        event, _raw_bytes = self._validated_event(raw_value, metadata)
        self._loki.push(event)

    @staticmethod
    def _validated_event(
        raw_value: bytes | str | dict[str, Any], metadata: KafkaMetadata
    ) -> tuple[dict[str, Any], bytes]:
        if metadata.topic != TOPIC:
            raise ValueError(f"unexpected topic for masked log sink: {metadata.topic}")
        if isinstance(raw_value, dict):
            raw_bytes = json.dumps(
                raw_value, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            event = raw_value
        else:
            raw_bytes = raw_value.encode("utf-8") if isinstance(raw_value, str) else raw_value
            event = json.loads(raw_bytes.decode("utf-8"))
        if not isinstance(event, dict):
            raise ValueError("masked log payload must be a JSON object")
        validate(TOPIC, event)
        validate_masking_safety(event["masked_message"], event.get("safe_metadata"))
        return event, raw_bytes
