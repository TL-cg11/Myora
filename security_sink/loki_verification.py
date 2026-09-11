"""Read-only Loki content and retention verification."""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlencode
from urllib.request import urlopen

from security_sink.common import validate_masking_safety


MASKED_SELECTOR = '{pipeline="security-masked-logs",data_class="masked"}'
EXPECTED_LOG_FIELDS = frozenset(
    {
        "event_id",
        "request_id",
        "masking_policy_version",
        "masked_message",
        "body_hash",
        "safe_metadata",
    }
)


@dataclass(frozen=True)
class LokiVerificationResult:
    log_count: int
    retention_hours: int


def _fetch_text(url: str, timeout: float) -> str:
    with urlopen(url, timeout=timeout) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"Loki verification failed with HTTP {response.status}")
        return response.read().decode("utf-8")


def verify_loki_runtime(
    base_url: str,
    *,
    lookback_hours: int = 1,
    require_logs: bool = True,
    timeout: float = 5.0,
    now_ns: int | None = None,
    fetch_text: Callable[[str, float], str] = _fetch_text,
) -> LokiVerificationResult:
    base_url = base_url.rstrip("/")
    ready = fetch_text(base_url + "/ready", timeout).strip().lower()
    if ready != "ready":
        raise ValueError("Loki is not ready")

    rendered_config = fetch_text(base_url + "/config", timeout)
    retention_values = re.findall(
        r"(?m)^\s*retention_period:\s*(\d+)([dh])(?:0m0s)?\s*$",
        rendered_config,
    )
    retention_hours = {
        int(amount) * (24 if unit == "d" else 1)
        for amount, unit in retention_values
    }
    if 720 not in retention_hours:
        raise ValueError("Loki retention_period must be 720h (30 days)")
    if re.search(r"(?m)^\s*retention_enabled:\s*true\s*$", rendered_config) is None:
        raise ValueError("Loki compactor retention must be enabled")

    end_ns = now_ns if now_ns is not None else time.time_ns()
    query = urlencode(
        {
            "query": MASKED_SELECTOR,
            "start": end_ns - lookback_hours * 3_600_000_000_000,
            "end": end_ns,
            "limit": 5000,
            "direction": "backward",
        }
    )
    response = json.loads(
        fetch_text(base_url + "/loki/api/v1/query_range?" + query, timeout)
    )
    if response.get("status") != "success":
        raise ValueError("Loki query did not succeed")

    results = response.get("data", {}).get("result", [])
    log_count = 0
    for stream in results:
        labels = stream.get("stream", {})
        if labels.get("pipeline") != "security-masked-logs" or labels.get("data_class") != "masked":
            raise ValueError("Loki security stream is missing mandatory masking labels")
        for _timestamp, line in stream.get("values", []):
            document = json.loads(line)
            if set(document) != EXPECTED_LOG_FIELDS:
                raise ValueError("Loki security log contains unexpected fields")
            if not document.get("event_id") or not document.get("masking_policy_version"):
                raise ValueError("Loki security log is missing completion metadata")
            validate_masking_safety(
                document.get("masked_message"),
                document.get("safe_metadata"),
                document.get("request_id"),
            )
            log_count += 1

    if require_logs and log_count == 0:
        raise ValueError("No completed masked security logs found in Loki")
    return LokiVerificationResult(log_count=log_count, retention_hours=720)
