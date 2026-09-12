from __future__ import annotations

import unittest

from security_sink.performance import PerformanceSnapshot, assess, percentile_95


class PerformanceTargetTests(unittest.TestCase):
    def test_documented_targets_pass_at_boundaries(self) -> None:
        result = assess(
            PerformanceSnapshot(
                sustained_throughput=100,
                burst_throughput=300,
                db_p95_seconds=2,
                loki_p95_seconds=5,
                end_to_end_p95_seconds=10,
                consumer_lag=999,
                oldest_message_seconds=60,
            )
        )

        self.assertTrue(result.passed)
        self.assertEqual(result.lag_status, "NORMAL")

    def test_warning_and_critical_lag_are_classified(self) -> None:
        base = dict(
            sustained_throughput=100,
            burst_throughput=300,
            db_p95_seconds=1,
            loki_p95_seconds=1,
            end_to_end_p95_seconds=1,
        )
        warning = assess(
            PerformanceSnapshot(
                **base, consumer_lag=1_000, oldest_message_seconds=10
            )
        )
        critical = assess(
            PerformanceSnapshot(
                **base, consumer_lag=100, oldest_message_seconds=61
            )
        )

        self.assertFalse(warning.passed)
        self.assertEqual(warning.lag_status, "WARNING")
        self.assertFalse(critical.passed)
        self.assertEqual(critical.lag_status, "CRITICAL")

    def test_p95_uses_nearest_rank(self) -> None:
        self.assertEqual(percentile_95(list(range(1, 101))), 95)


if __name__ == "__main__":
    unittest.main()
