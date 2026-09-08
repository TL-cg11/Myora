#!/usr/bin/env python3
"""Verify masked security logs and retention against a running Loki."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from security_sink.loki_verification import verify_loki_runtime  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--loki-url", default="http://127.0.0.1:3100")
    parser.add_argument("--lookback-hours", type=int, default=1)
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args()
    result = verify_loki_runtime(
        args.loki_url,
        lookback_hours=args.lookback_hours,
        require_logs=not args.allow_empty,
    )
    print(
        json.dumps(
            {
                "status": "ok",
                "masked_log_count": result.log_count,
                "retention_hours": result.retention_hours,
            },
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
