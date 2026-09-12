from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


class Part13PerformanceRunnerTests(unittest.TestCase):
    def test_default_mode_is_non_mutating_and_reports_load(self):
        root = Path(__file__).resolve().parents[1]
        process = subprocess.run(
            [sys.executable, str(root / "scripts/run_part13_performance.py")],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(process.returncode, 0, process.stderr)
        report = json.loads(process.stdout)
        self.assertEqual(report["status"], "dry-run")
        self.assertEqual(report["messages_total"], 49_000)
        self.assertTrue(report["requires_execute"])

    def test_runner_uses_actual_topics_and_all_acceptance_inputs(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "scripts/run_part13_performance.py").read_text()
        self.assertIn('SECURITY_TOPIC = "myohan.security-events"', script)
        self.assertIn('MASKED_TOPIC = "myohan.masked-logs"', script)
        for field in (
            "sustained_throughput",
            "burst_throughput",
            "db_p95_seconds",
            "loki_p95_seconds",
            "end_to_end_p95_seconds",
            "consumer_lag",
            "oldest_message_seconds",
        ):
            self.assertIn(field, script)


if __name__ == "__main__":
    unittest.main()
