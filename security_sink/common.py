"""Shared Kafka message metadata and consumption SQL."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any


SELECT_CONSUMPTION = """
SELECT id FROM kafka_consumption
WHERE consumer_group = %s AND topic_name = %s
  AND partition_number = %s AND message_offset = %s
LIMIT 1
""".strip()

SELECT_CONSUMPTION_FOR_UPDATE = SELECT_CONSUMPTION + " FOR UPDATE"

INSERT_CONSUMPTION = """
INSERT INTO kafka_consumption (
    consumer_group, topic_name, partition_number, message_offset,
    message_key, payload_hash, event_id, processing_status
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
""".strip()


@dataclass(frozen=True)
class KafkaMetadata:
    consumer_group: str
    topic: str
    partition: int
    offset: int
    key: str | None = None

    def __post_init__(self) -> None:
        if not self.consumer_group:
            raise ValueError("consumer_group must not be empty")
        if not self.topic:
            raise ValueError("topic must not be empty")
        if self.partition < 0 or self.offset < 0:
            raise ValueError("Kafka partition and offset must not be negative")
        if self.key is not None and len(self.key) > 128:
            raise ValueError("Kafka message key is longer than 128 characters")

    def identity_values(self) -> tuple[Any, ...]:
        return (self.consumer_group, self.topic, self.partition, self.offset)

    def consumption_values(
        self,
        payload_hash: str,
        event_id: str | None,
        status: str = "PROCESSED",
    ) -> tuple[Any, ...]:
        return self.identity_values() + (self.key, payload_hash, event_id, status)


@dataclass(frozen=True)
class ProcessResult:
    event_db_id: int | None
    duplicate: str | None = None


def sha256_hex(raw_value: bytes) -> str:
    return hashlib.sha256(raw_value).hexdigest()


def decode_message_key(value: bytes | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            value = value.decode("utf-8")
        except UnicodeDecodeError:
            return "sha256:" + sha256_hex(value)
    if len(value) > 128:
        return "sha256:" + sha256_hex(value.encode("utf-8"))
    return value


_SENSITIVE_PATTERNS = (
    re.compile(r"\b\d{6}-[1-4]\d{6}\b"),
    re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
    re.compile(r"\b01[016789]-?\d{3,4}-?\d{4}\b"),
    re.compile(r"\b(?:\d[ -]?){12,18}\d\b"),
    re.compile(r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b", re.IGNORECASE),
    re.compile(r"\b(?:AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_-]{20,}|gh[pousr]_[0-9A-Za-z]{20,})\b"),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}\b", re.IGNORECASE),
    re.compile(
        r"\b(?:authorization|api[_-]?key|secret[_-]?key)\s*[:=]\s*(?!\[[A-Z_]+\])\S+",
        re.IGNORECASE,
    ),
    re.compile(
        r"https?://(?:localhost|127\.0\.0\.1|10(?:\.\d{1,3}){3}|"
        r"192\.168(?:\.\d{1,3}){2}|172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2})"
        r"(?::\d+)?(?:[/\w.?=&%-]*)?",
        re.IGNORECASE,
    ),
    re.compile(
        r"https?://(?:100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])(?:\.\d{1,3}){2}|"
        r"169\.254(?:\.\d{1,3}){2}|\[?::1\]?|"
        r"[a-z0-9-]+\.(?:internal|local|lan)|[a-z0-9-]+(?=[:/]))"
        r"(?::\d+)?(?:[/\w.?=&%-]*)?",
        re.IGNORECASE,
    ),
)


def validate_masking_safety(*values: Any) -> None:
    rendered = "\n".join(
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        for value in values
        if value is not None
    )
    if any(pattern.search(rendered) for pattern in _SENSITIVE_PATTERNS):
        raise ValueError("payload contains unmasked sensitive information")
