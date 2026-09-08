#!/usr/bin/env python3
"""Verify both sink /metrics endpoints and Prometheus scrape/retention."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from security_sink.metrics_verification import verify_metrics_runtime  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prometheus-url", default="http://127.0.0.1:9090")
    parser.add_argument(
        "--metrics-target",
        action="append",
        default=[],
        help="Repeat for each sink metrics URL",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    targets = args.metrics_target or [
        "http://100.66.77.55:9108",
        "http://100.66.77.55:9109",
    ]
    result = verify_metrics_runtime(args.prometheus_url, targets)
    print(
        json.dumps(
            {
                "status": "ok",
                "targets": result.targets,
                "prometheus_retention": result.prometheus_retention,
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
