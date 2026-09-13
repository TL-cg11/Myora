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

    def test_diagnostic_mode_is_run_id_scoped(self):
        root = Path(__file__).resolve().parents[1]
        script = (root / "scripts/run_part13_performance.py").read_text()
        self.assertIn('parser.add_argument("--diagnose-run-id")', script)
        self.assertIn('re.fullmatch(r"[0-9a-f]{12}"', script)
        self.assertIn("db_topic_stats(args.diagnose_run_id)", script)
        self.assertIn("db_event_count(args.diagnose_run_id)", script)
        self.assertIn("detected_at,created_at", script)
        self.assertIn('MASKED_TOPIC: None', script)
        self.assertIn("percentile_95(samples) if samples else None", script)

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
            "preflight_throughput_by_topic",
            "terminal_results_by_topic",
            "average_seconds_by_topic",
            "throughput_by_topic",
            "terminal_results_ok",
        ):
            self.assertIn(field, script)
        self.assertIn("result_counts", script)
        self.assertIn("histogram_p95_or_none", script)
        self.assertIn("db_phase_throughput", script)
        self.assertIn("MIN(processed_at),MAX(processed_at)", script)

    def test_server_wrapper_is_dry_run_by_default(self):
        root = Path(__file__).resolve().parents[1]
        wrapper = (root / "scripts/run-part13-11.sh").read_text()
        self.assertIn("requires_execute", wrapper)
        self.assertIn("systemctl restart luck-security-event-sink luck-masked-log-sink", wrapper)
        self.assertIn("luck_sink_commit_duration_seconds", wrapper)
        self.assertIn('run_part13_performance.py" --execute', wrapper)

        combined = (root / "scripts/run-part13-remaining.sh").read_text()
        self.assertIn('"13-11","13-12","13-13","13-14"', combined)
        self.assertIn("configuration_snapshot", combined)
        self.assertIn("production_configuration_modified", combined)
        self.assertIn('run-part13-11.sh" --execute', combined)


if __name__ == "__main__":
    unittest.main()
