"""Performance target measurement and acceptance evaluation."""

from __future__ import annotations

import math
import time
from dataclasses import asdict, dataclass
from typing import Callable


@dataclass(frozen=True)
class PerformanceSnapshot:
    sustained_throughput: float
    burst_throughput: float
    db_p95_seconds: float
    loki_p95_seconds: float
    end_to_end_p95_seconds: float
    consumer_lag: int
    oldest_message_seconds: float


@dataclass(frozen=True)
class PerformanceAssessment:
    passed: bool
    checks: dict[str, bool]
    lag_status: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def percentile_95(samples: list[float]) -> float:
    if not samples:
        raise ValueError("latency samples must not be empty")
    ordered = sorted(samples)
    index = max(0, math.ceil(len(ordered) * 0.95) - 1)
    return ordered[index]


def measure_for_duration(
    operation: Callable[[int], None], duration_seconds: float
) -> tuple[float, float, int]:
    if duration_seconds <= 0:
        raise ValueError("duration_seconds must be positive")
    latencies: list[float] = []
    started = time.perf_counter()
    deadline = started + duration_seconds
    sequence = 0
    while time.perf_counter() < deadline:
        item_started = time.perf_counter()
        operation(sequence)
        latencies.append(time.perf_counter() - item_started)
        sequence += 1
    elapsed = time.perf_counter() - started
    return sequence / elapsed, percentile_95(latencies), sequence


def assess(snapshot: PerformanceSnapshot) -> PerformanceAssessment:
    checks = {
        "sustained_throughput": snapshot.sustained_throughput >= 100,
        "burst_throughput": snapshot.burst_throughput >= 300,
        "db_p95": snapshot.db_p95_seconds <= 2,
        "loki_p95": snapshot.loki_p95_seconds <= 5,
        "end_to_end_p95": snapshot.end_to_end_p95_seconds <= 10,
        "normal_lag": snapshot.consumer_lag < 1_000,
        "oldest_message": snapshot.oldest_message_seconds <= 60,
    }
    if snapshot.consumer_lag >= 5_000 or snapshot.oldest_message_seconds > 60:
        lag_status = "CRITICAL"
    elif snapshot.consumer_lag >= 1_000:
        lag_status = "WARNING"
    else:
        lag_status = "NORMAL"
    return PerformanceAssessment(
        passed=all(checks.values()), checks=checks, lag_status=lag_status
    )
