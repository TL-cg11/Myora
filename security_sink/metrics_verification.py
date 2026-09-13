"""Read-only runtime verification for sink metrics and Prometheus retention."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable
from urllib.parse import urlencode
from urllib.request import urlopen


REQUIRED_METRICS = frozenset(
    {
        "luck_sink_messages_total",
        "luck_sink_failures_total",
        "luck_sink_retries_total",
        "luck_sink_dlq_total",
        "luck_sink_processing_duration_seconds",
        "luck_sink_commit_duration_seconds",
        "luck_sink_end_to_end_duration_seconds",
        "luck_consumer_lag_messages",
        "luck_consumer_oldest_message_age_seconds",
    }
)


def _fetch(url: str, timeout: float) -> str:
    with urlopen(url, timeout=timeout) as response:
        return response.read().decode()


@dataclass(frozen=True)
class MetricsVerification:
    targets: int
    prometheus_retention: str


def verify_metrics_runtime(
    prometheus_url: str,
    metric_targets: list[str],
    *,
    timeout: float = 5.0,
    fetch: Callable[[str, float], str] = _fetch,
) -> MetricsVerification:
    for target in metric_targets:
        rendered = fetch(target.rstrip("/") + "/metrics", timeout)
        missing = [name for name in REQUIRED_METRICS if name not in rendered]
        if missing:
            raise ValueError(f"metric target is missing required metrics: {sorted(missing)}")

    prometheus_url = prometheus_url.rstrip("/")
    flags = json.loads(fetch(prometheus_url + "/api/v1/status/flags", timeout))
    retention = flags.get("data", {}).get("storage.tsdb.retention.time")
    if retention != "30d":
        raise ValueError("Prometheus retention must be 30d")
    query_url = prometheus_url + "/api/v1/query?" + urlencode(
        {"query": 'up{job="luck-security-sinks"}'}
    )
    query = json.loads(fetch(query_url, timeout))
    results = query.get("data", {}).get("result", [])
    if len(results) != len(metric_targets) or any(item["value"][1] != "1" for item in results):
        raise ValueError("Prometheus is not scraping every security sink target")
    return MetricsVerification(len(metric_targets), retention)
