#!/usr/bin/env python3
"""Run bounded security-monitoring retention cleanup."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from security_sink.retention import run_retention_cleanup
from security_sink.runtime import mysql_connection


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch-size", type=int, default=1_000)
    parser.add_argument("--max-batches", type=int, default=10)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="commit deletes; without this option the command is a dry-run",
    )
    args = parser.parse_args()

    results = run_retention_cleanup(
        mysql_connection,
        batch_size=args.batch_size,
        max_batches=args.max_batches,
        dry_run=not args.execute,
    )
    print(
        json.dumps(
            {
                "mode": "execute" if args.execute else "dry-run",
                "batches": [
                    {
                        "candidates": item.candidates,
                        "deleted": item.deleted,
                        "total_candidates": item.total_candidates,
                        "total_deleted": item.total_deleted,
                    }
                    for item in results
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
