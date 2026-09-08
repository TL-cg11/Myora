"""Retry, DLQ, failure history, and durable buffer support for sink workers."""

from __future__ import annotations

import base64
import json
import os
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from security_sink.common import (
    INSERT_CONSUMPTION,
    KafkaMetadata,
    ProcessResult,
    sha256_hex,
    validate_masking_safety,
)


DLQ_TOPICS = {
    "luck.security-events": "luck.security-events.sink-dlq",
    "luck.masked-logs": "luck.masked-logs.sink-dlq",
}

UPSERT_FAILURE = """
INSERT INTO consumer_failure (
    consumer_group, source_topic, partition_number, message_offset,
    event_id, payload_hash, failure_stage, error_code, error_message,
    retry_count, retry_status
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
ON DUPLICATE KEY UPDATE
    event_id = VALUES(event_id),
    payload_hash = VALUES(payload_hash),
    failure_stage = VALUES(failure_stage),
    error_code = VALUES(error_code),
    error_message = VALUES(error_message),
    retry_count = VALUES(retry_count),
    retry_status = VALUES(retry_status),
    last_failed_at = CURRENT_TIMESTAMP(3)
""".strip()

MARK_RECOVERED = """
UPDATE consumer_failure
SET retry_status = 'RECOVERED', recovered_at = CURRENT_TIMESTAMP(3),
    last_failed_at = CURRENT_TIMESTAMP(3)
WHERE consumer_group = %s AND source_topic = %s
  AND partition_number = %s AND message_offset = %s
""".strip()


@dataclass(frozen=True)
class FailureDetails:
    stage: str
    code: str
    message: str
    permanent: bool


def classify_failure(exc: Exception) -> FailureDetails:
    if isinstance(exc, UnicodeDecodeError):
        return FailureDetails("schema_validation", "PAYLOAD_ENCODING", "payload is not UTF-8", True)
    if isinstance(exc, json.JSONDecodeError):
        return FailureDetails("schema_validation", "JSON_PARSE_FAILED", "payload is not valid JSON", True)
    if isinstance(exc, ValueError):
        text = str(exc)
        if "unmasked sensitive" in text:
            return FailureDetails(
                "masking_validation",
                "MASKING_SAFETY_FAILED",
                "payload did not pass masking safety validation",
                True,
            )
        return FailureDetails(
            "schema_validation",
            "CONTRACT_VALIDATION_FAILED",
            "payload did not match the supported contract",
            True,
        )
    return FailureDetails(
        "sink_processing",
        "TRANSIENT_SINK_FAILURE",
        f"temporary {type(exc).__name__} while processing message",
        False,
    )


class FailureRepository:
    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self._connection_factory = connection_factory

    def record(
        self,
        metadata: KafkaMetadata,
        *,
        event_id: str | None,
        payload_hash: str,
        details: FailureDetails,
        retry_count: int,
        status: str,
    ) -> None:
        connection = self._connection_factory()
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute(
                    UPSERT_FAILURE,
                    metadata.identity_values()
                    + (
                        event_id,
                        payload_hash,
                        details.stage,
                        details.code,
                        details.message[:1000],
                        retry_count,
                        status,
                    ),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def mark_recovered(self, metadata: KafkaMetadata) -> None:
        connection = self._connection_factory()
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute(MARK_RECOVERED, metadata.identity_values())
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()


class TerminalConsumptionRepository:
    def __init__(self, connection_factory: Callable[[], Any]) -> None:
        self._connection_factory = connection_factory

    def record_dlq(
        self,
        metadata: KafkaMetadata,
        payload_hash: str,
        event_id: str | None,
    ) -> None:
        connection = self._connection_factory()
        try:
            connection.begin()
            with connection.cursor() as cursor:
                cursor.execute(
                    INSERT_CONSUMPTION,
                    metadata.consumption_values(payload_hash, event_id, "DLQ"),
                )
            connection.commit()
        except Exception as exc:
            connection.rollback()
            if not (getattr(exc, "args", ()) and exc.args[0] == 1062):
                raise
        finally:
            connection.close()


class DlqPublisher:
    """Publish a sanitized failure envelope without the source payload."""

    def __init__(self, send: Callable[[str, str | None, bytes], None]) -> None:
        self._send = send

    def publish(
        self,
        metadata: KafkaMetadata,
        *,
        payload_hash: str,
        schema_version: str | None,
        details: FailureDetails,
        retry_count: int,
    ) -> None:
        safe_key = metadata.key
        try:
            validate_masking_safety(safe_key)
        except ValueError:
            safe_key = (
                "sha256:" + sha256_hex(metadata.key.encode("utf-8"))
                if metadata.key is not None
                else None
            )
        envelope = {
            "source_topic": metadata.topic,
            "partition": metadata.partition,
            "offset": metadata.offset,
            "message_key": safe_key,
            "payload_hash": payload_hash,
            "schema_version": schema_version,
            "error_code": details.code,
            "error_message": details.message,
            "failure_stage": details.stage,
            "retry_count": retry_count,
            "failed_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        }
        self._send(
            DLQ_TOPICS[metadata.topic],
            safe_key,
            json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8"),
        )


@dataclass(frozen=True)
class BufferedMessage:
    path: Path
    metadata: KafkaMetadata
    raw_value: bytes


class FilesystemBuffer:
    """Atomically spool already-validated masked logs for later Loki replay."""

    def __init__(self, directory: Path, *, max_bytes: int = 1_073_741_824) -> None:
        self.directory = directory
        self.max_bytes = max_bytes

    def store(self, metadata: KafkaMetadata, raw_value: bytes) -> Path:
        self.directory.mkdir(parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        identity = "|".join(map(str, metadata.identity_values()))
        filename = sha256_hex(identity.encode("utf-8")) + ".json"
        target = self.directory / filename
        document = {
            "metadata": asdict(metadata),
            "raw_value_base64": base64.b64encode(raw_value).decode("ascii"),
        }
        rendered = json.dumps(
            document, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        existing_size = target.stat().st_size if target.exists() else 0
        used_bytes = sum(path.stat().st_size for path in self.directory.glob("*.json"))
        if used_bytes - existing_size + len(rendered) > self.max_bytes:
            raise OSError("masked log filesystem buffer size limit exceeded")
        fd, temporary_name = tempfile.mkstemp(
            prefix=".pending-", suffix=".tmp", dir=self.directory
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(rendered.decode("utf-8"))
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary_name, 0o600)
            os.replace(temporary_name, target)
        except Exception:
            try:
                os.unlink(temporary_name)
            except FileNotFoundError:
                pass
            raise
        return target

    def entries(self) -> list[BufferedMessage]:
        if not self.directory.exists():
            return []
        entries: list[BufferedMessage] = []
        for path in sorted(self.directory.glob("*.json")):
            with path.open(encoding="utf-8") as handle:
                document = json.load(handle)
            entries.append(
                BufferedMessage(
                    path=path,
                    metadata=KafkaMetadata(**document["metadata"]),
                    raw_value=base64.b64decode(document["raw_value_base64"], validate=True),
                )
            )
        return entries

    @staticmethod
    def acknowledge(entry: BufferedMessage) -> None:
        entry.path.unlink()


class ResilientProcessor:
    def __init__(
        self,
        failures: FailureRepository,
        terminal_consumption: TerminalConsumptionRepository,
        dlq: DlqPublisher,
        *,
        max_retries: int = 5,
        max_delay_seconds: float = 30,
        sleeper: Callable[[float], None] = time.sleep,
        buffer: FilesystemBuffer | None = None,
    ) -> None:
        self._failures = failures
        self._terminal_consumption = terminal_consumption
        self._dlq = dlq
        self._max_retries = max_retries
        self._max_delay_seconds = max_delay_seconds
        self._sleeper = sleeper
        self._buffer = buffer

    def execute(
        self,
        operation: Callable[[], ProcessResult],
        raw_value: bytes,
        metadata: KafkaMetadata,
    ) -> ProcessResult:
        payload_hash = sha256_hex(raw_value)
        event_id, schema_version = self._safe_identifiers(raw_value)
        retry_count = 0
        had_failure = False
        failure_history_missing = False
        last_details: FailureDetails | None = None
        while True:
            try:
                result = operation()
                if had_failure:
                    try:
                        if failure_history_missing and last_details is not None:
                            self._failures.record(
                                metadata,
                                event_id=event_id,
                                payload_hash=payload_hash,
                                details=last_details,
                                retry_count=retry_count,
                                status="RETRYING",
                            )
                        self._failures.mark_recovered(metadata)
                    except Exception:
                        # Successful sink processing must not be repeated only
                        # because the auxiliary failure history is unavailable.
                        pass
                return result
            except Exception as exc:
                details = classify_failure(exc)
                last_details = details
                had_failure = True
                if details.permanent or retry_count >= self._max_retries:
                    if self._buffer is not None and not details.permanent:
                        self._buffer.store(metadata, raw_value)
                    self._dlq.publish(
                        metadata,
                        payload_hash=payload_hash,
                        schema_version=schema_version,
                        details=details,
                        retry_count=retry_count,
                    )
                    self._failures.record(
                        metadata,
                        event_id=event_id,
                        payload_hash=payload_hash,
                        details=details,
                        retry_count=retry_count,
                        status="DLQ",
                    )
                    self._terminal_consumption.record_dlq(
                        metadata, payload_hash, event_id
                    )
                    return ProcessResult(event_db_id=None, duplicate="dlq")

                retry_count += 1
                try:
                    self._failures.record(
                        metadata,
                        event_id=event_id,
                        payload_hash=payload_hash,
                        details=details,
                        retry_count=retry_count,
                        status="RETRYING",
                    )
                except Exception:
                    # The failed dependency may itself be MariaDB. Continue
                    # retrying the primary operation and persist on recovery.
                    failure_history_missing = True
                self._sleeper(min(2 ** (retry_count - 1), self._max_delay_seconds))

    @staticmethod
    def _safe_identifiers(raw_value: bytes) -> tuple[str | None, str | None]:
        try:
            payload = json.loads(raw_value.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None, None
        if not isinstance(payload, dict):
            return None, None
        event_id = payload.get("event_id")
        schema_version = payload.get("schema_version")
        return (
            event_id if isinstance(event_id, str) and len(event_id) <= 64 else None,
            schema_version
            if isinstance(schema_version, str) and len(schema_version) <= 16
            else None,
        )
