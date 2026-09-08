#!/usr/bin/env python3
"""Report overdue rows for documented security-monitoring retention policies."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from security_sink.retention import verify_retention  # noqa: E402
from security_sink.runtime import mysql_connection  # noqa: E402


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    result = verify_retention(mysql_connection)
    print(
        json.dumps(
            {"status": "ok" if result.passed else "overdue", "overdue": result.overdue},
            separators=(",", ":"),
        )
    )
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
