#!/usr/bin/env python3
"""Benchmark local sink contract/mapping code without Kafka, MariaDB, or Loki I/O."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.mock_security_producer import validate  # noqa: E402
from security_sink.performance import measure_for_duration  # noqa: E402


def load_fixture(name: str) -> dict[str, Any]:
    with (ROOT / "fixtures" / name).open(encoding="utf-8") as handle:
        return json.load(handle)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=5.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    security = load_fixture("luck.security-events.normal.json")
    masked = load_fixture("luck.masked-logs.normal.json")
    db_rate, db_p95, db_count = measure_for_duration(
        lambda _sequence: validate("myohan.security-events", security), args.duration
    )
    loki_rate, loki_p95, loki_count = measure_for_duration(
        lambda _sequence: validate("myohan.masked-logs", masked), args.duration
    )
    core_rate = min(db_rate, loki_rate)
    checks = {
        "core_rate_over_sustained_target": core_rate >= 100,
        "core_rate_over_burst_target": core_rate >= 300,
        "security_core_p95_under_db_budget": db_p95 <= 2,
        "masked_core_p95_under_loki_budget": loki_p95 <= 5,
    }
    passed = all(checks.values())
    print(
        json.dumps(
            {
                "scope": "local-core-no-network-io",
                "duration_seconds_per_sink": args.duration,
                "security_event_count": db_count,
                "masked_log_count": loki_count,
                "core_measurements": {
                    "minimum_throughput_per_second": core_rate,
                    "security_event_p95_seconds": db_p95,
                    "masked_log_p95_seconds": loki_p95,
                },
                "core_assessment": {"passed": passed, "checks": checks},
                "operational_targets_not_measured": [
                    "MariaDB latency",
                    "Loki HTTP latency",
                    "end-to-end visibility",
                    "Kafka consumer lag",
                    "oldest Kafka message age",
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
