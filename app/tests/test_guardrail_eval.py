import unittest
from argparse import Namespace
from dataclasses import replace
from unittest.mock import AsyncMock, patch

from app.evals import run_guardrail_eval as evaluator


class GuardrailEvalTests(unittest.IsolatedAsyncioTestCase):
    def test_case_catalog_has_twenty_cases_per_service(self):
        self.assertEqual(len(evaluator.CASES), 60)
        for service in ("saju", "tarot", "face"):
            cases = [case for case in evaluator.CASES if case["service"] == service]
            self.assertEqual(len(cases), 20, service)
        self.assertEqual(len({case["id"] for case in evaluator.CASES}), 60)

    def test_case_selection_enforces_limit_and_service(self):
        selected = evaluator.selected_cases("tarot", 2)
        self.assertEqual([case["id"] for case in selected], ["LIVE-T-01", "LIVE-T-02"])
        with self.assertRaises(ValueError):
            evaluator.selected_cases("all", 0)

    async def test_evaluation_report_contains_only_metadata(self):
        args = Namespace(service="saju", max_cases=1, repeat=1, output=None, confirm_live=True)
        result = {
            "case_id": "LIVE-S-01", "service": "saju", "expected": "allow",
            "actual": "restrict", "rules": ["G04"], "passed": False,
            "generated": False, "elapsed_ms": 10.0, "call_count": 1,
            "calls": [{"phase": "input_check", "model": "test", "elapsed_ms": 10.0,
                       "success": True, "prompt_tokens": 1, "completion_tokens": 1,
                       "total_tokens": 2}],
        }
        with (
            patch.object(
                evaluator, "settings",
                replace(evaluator.settings, deepseek_saju_api_key="fake"),
            ),
            patch.object(evaluator, "evaluate_case", AsyncMock(return_value=result)),
        ):
            report = await evaluator.run(args)
        self.assertNotIn("question", str(report))
        self.assertNotIn("answer", str(report))
        self.assertEqual(report["total_calls"], 1)
        self.assertEqual(report["total_tokens"], 2)
        self.assertTrue(report["timeout_budget_ok"])


if __name__ == "__main__":
    unittest.main()
