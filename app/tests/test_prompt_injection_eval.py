import unittest
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from io import StringIO
from unittest.mock import AsyncMock, patch

from app.evals import run_prompt_injection_eval as evaluator
from app.services.guardrail import SafeAnswer


class PromptInjectionEvalTests(unittest.IsolatedAsyncioTestCase):
    def test_default_cases_are_valid_and_cover_all_kinds(self):
        cases = evaluator.load_cases(evaluator.DEFAULT_CASES)
        self.assertEqual(len(cases), 240)
        self.assertEqual(
            {case["kind"] for case in cases},
            {"direct", "indirect", "output", "combined", "control"},
        )
        selected = evaluator.select_cases(cases, service="tarot", kind="direct", max_cases=2)
        self.assertEqual(len(selected), 2)
        self.assertTrue(all(case["service"] == "tarot" for case in selected))

    async def test_result_contains_metadata_without_prompt_or_answer(self):
        case = evaluator.load_cases(evaluator.DEFAULT_CASES)[0]
        with (
            patch.object(
                evaluator, "safe_answer",
                AsyncMock(return_value=SafeAnswer(
                    answer="제한 안내", question="[비공개]", generated=False,
                    decision="restrict", rules=("G11",),
                )),
            ),
            patch.object(evaluator, "capture_ai_calls") as capture,
        ):
            capture.return_value.__enter__.return_value = []
            capture.return_value.__exit__.return_value = False
            result = await evaluator.evaluate_case(case)
        self.assertTrue(result["passed"])
        self.assertNotIn("question", result)
        self.assertNotIn("answer", result)

    async def test_run_prints_progress_without_prompt_or_answer(self):
        case = evaluator.load_cases(evaluator.DEFAULT_CASES)[0]
        result = {
            "case_id": case["id"], "kind": case["kind"],
            "service": case["service"], "expected": case["expected"],
            "actual": "restrict", "rules": ["G11"], "generated": False,
            "rule_match": True, "generated_match": True,
            "forbidden_token_leak": False, "passed": True,
            "elapsed_ms": 1234.0, "call_count": 1, "calls": [],
        }
        with (
            patch.object(evaluator, "evaluate_case", AsyncMock(return_value=result)),
            patch.object(
                evaluator,
                "settings",
                replace(evaluator.settings, deepseek_tarot_api_key="fake"),
            ),
            redirect_stderr(StringIO()) as progress,
        ):
            await evaluator.run([case], repeat=1)
        output = progress.getvalue()
        self.assertIn("[1/1 100.0%]", output)
        self.assertIn("PASS", output)
        self.assertNotIn(case["question"], output)

    def test_live_confirmation_is_required(self):
        with redirect_stderr(StringIO()), self.assertRaises(SystemExit):
            evaluator.main(["--max-cases", "1"])

    def test_list_mode_does_not_require_api_key(self):
        with redirect_stdout(StringIO()):
            result = evaluator.main(["--kind", "indirect", "--max-cases", "2", "--list"])
        self.assertEqual(result, 0)


if __name__ == "__main__":
    unittest.main()
