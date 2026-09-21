"""Explicit one-shot crash checkpoints for controlled operational tests."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

from security_sink.common import KafkaMetadata


def crash_once(
    marker_env: str,
    checkpoint: str,
    metadata: KafkaMetadata,
    *,
    terminate: Callable[[int], None] = os._exit,
) -> None:
    """Terminate once after atomically creating a payload-free marker file."""
    marker_value = os.getenv(marker_env)
    if not marker_value:
        return

    marker = Path(marker_value)
    marker.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return

    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(
            {
                "checkpoint": checkpoint,
                "consumer_group": metadata.consumer_group,
                "topic": metadata.topic,
                "partition": metadata.partition,
                "offset": metadata.offset,
            },
            handle,
            separators=(",", ":"),
        )
        handle.flush()
        os.fsync(handle.fileno())
    terminate(137)
