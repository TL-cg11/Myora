#!/usr/bin/env python3
"""Evaluate observed sink metrics against the documented v1 targets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from security_sink.performance import PerformanceSnapshot, assess  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sustained-throughput", type=float, required=True)
    parser.add_argument("--burst-throughput", type=float, required=True)
    parser.add_argument("--db-p95-seconds", type=float, required=True)
    parser.add_argument("--loki-p95-seconds", type=float, required=True)
    parser.add_argument("--end-to-end-p95-seconds", type=float, required=True)
    parser.add_argument("--consumer-lag", type=int, required=True)
    parser.add_argument("--oldest-message-seconds", type=float, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    snapshot = PerformanceSnapshot(
        sustained_throughput=args.sustained_throughput,
        burst_throughput=args.burst_throughput,
        db_p95_seconds=args.db_p95_seconds,
        loki_p95_seconds=args.loki_p95_seconds,
        end_to_end_p95_seconds=args.end_to_end_p95_seconds,
        consumer_lag=args.consumer_lag,
        oldest_message_seconds=args.oldest_message_seconds,
    )
    assessment = assess(snapshot)
    print(
        json.dumps(
            {"snapshot": snapshot.__dict__, "assessment": assessment.as_dict()},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if assessment.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
