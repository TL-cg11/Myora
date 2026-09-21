"""Push validated ``myohan.masked-logs`` messages to Loki."""

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


TOPIC = "myohan.masked-logs"


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
        self.push_batch([event])

    def push_batch(self, events: list[dict[str, Any]]) -> None:
        streams: dict[tuple[str, str, str], dict[str, Any]] = {}
        for event in events:
            key = (event["environment"], event["source_service"], event["source_type"])
            stream = streams.setdefault(
                key,
                {
                    "stream": {
                        "pipeline": "security-masked-logs",
                        "data_class": "masked",
                        "environment": key[0],
                        "source_service": key[1],
                        "source_type": key[2],
                    },
                    "values": [],
                },
            )
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
            stream["values"].append([_timestamp_ns(event["occurred_at"]), log_line])
        for stream in streams.values():
            stream["values"].sort(key=lambda item: int(item[0]))
        payload = {"streams": list(streams.values())}
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

    def processed_batch(self, metadata_items: list[KafkaMetadata]) -> set[tuple[Any, ...]]:
        if not metadata_items:
            return set()
        connection = self._connection_factory()
        try:
            conditions = []
            values: list[Any] = []
            for metadata in metadata_items:
                conditions.append(
                    "(consumer_group=%s AND topic_name=%s AND "
                    "partition_number=%s AND message_offset=%s)"
                )
                values.extend(metadata.identity_values())
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT consumer_group,topic_name,partition_number,message_offset "
                    "FROM kafka_consumption WHERE " + " OR ".join(conditions),
                    tuple(values),
                )
                return {tuple(row) for row in cursor.fetchall()}
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

    def record_processed_batch(
        self,
        items: list[tuple[KafkaMetadata, str, str]],
    ) -> None:
        if not items:
            return
        connection = self._connection_factory()
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.executemany(
                    INSERT_CONSUMPTION,
                    [
                        metadata.consumption_values(payload_hash, event_id)
                        for metadata, payload_hash, event_id in items
                    ],
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


class MaskedLogSink:
    def __init__(
        self,
        consumption: ConsumptionRepository,
        loki: LokiClient,
        *,
        after_loki_push: Callable[[KafkaMetadata], None] | None = None,
    ) -> None:
        self._consumption = consumption
        self._loki = loki
        self._after_loki_push = after_loki_push

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
        if self._after_loki_push is not None:
            self._after_loki_push(metadata)
        self._consumption.record_processed(metadata, payload_hash, event["event_id"])
        return ProcessResult(event_db_id=None)

    def replay_buffered(
        self, raw_value: bytes, metadata: KafkaMetadata
    ) -> None:
        event, _raw_bytes = self._validated_event(raw_value, metadata)
        self._loki.push(event)

    def handle_batch(
        self, items: list[tuple[bytes, KafkaMetadata]]
    ) -> list[ProcessResult]:
        prepared = [
            (*self._validated_event(raw_value, metadata), metadata)
            for raw_value, metadata in items
        ]
        consumed = self._consumption.processed_batch(
            [metadata for _event, _raw, metadata in prepared]
        )
        fresh = [
            (event, raw, metadata)
            for event, raw, metadata in prepared
            if metadata.identity_values() not in consumed
        ]
        if fresh:
            self._loki.push_batch([event for event, _raw, _metadata in fresh])
            if self._after_loki_push is not None:
                self._after_loki_push(fresh[-1][2])
            self._consumption.record_processed_batch(
                [
                    (metadata, sha256_hex(raw), event["event_id"])
                    for event, raw, metadata in fresh
                ]
            )
        return [
            ProcessResult(event_db_id=None, duplicate="offset")
            if metadata.identity_values() in consumed
            else ProcessResult(event_db_id=None)
            for _event, _raw, metadata in prepared
        ]

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
        validate_masking_safety(event)
        return event, raw_bytes
