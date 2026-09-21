"""AI_GUARDRAIL_POLICY.md의 G01~G11이 평가 케이스에서 최소 1번씩은
테스트되는지 정적으로 확인한다. 실제 API 호출은 하지 않는다(무료).

이 테스트는 "판정이 정확한지"가 아니라 "테스트 케이스가 그 규칙을
다루기는 하는지"만 본다 — 커버리지 회귀(누군가 케이스를 지우다가
어떤 규칙이 통째로 안 다뤄지게 되는 것)를 잡기 위한 안전망이다.
"""
import json
import unittest
from pathlib import Path

from app.evals.run_guardrail_eval import CASES

ALL_RULES = {f"G{n:02d}" for n in range(1, 12)}

INJECTION_CASES_PATH = (
    Path(__file__).resolve().parents[1] / "evals" / "cases" / "prompt_injection.json"
)


def _covered_rules() -> set[str]:
    covered: set[str] = set()
    for case in CASES:
        covered.update(case.get("rules", ()))

    injection_cases = json.loads(INJECTION_CASES_PATH.read_text(encoding="utf-8"))
    for case in injection_cases:
        covered.update(case.get("expected_rules_any", []))
    return covered


class GuardrailPolicyCoverageTests(unittest.TestCase):
    def test_every_policy_rule_has_at_least_one_case(self):
        covered = _covered_rules()
        missing = ALL_RULES - covered
        self.assertEqual(
            missing, set(),
            f"AI_GUARDRAIL_POLICY.md의 규칙 중 테스트 케이스가 하나도 없는 것: {sorted(missing)}. "
            "run_guardrail_eval.py의 CASES 또는 evals/cases/prompt_injection.json에 케이스를 추가하세요.",
        )

    def test_content_rules_have_a_reasonable_minimum_of_cases(self):
        """G01~G10은 결과가 통계적으로 의미 있으려면 최소 개수가 있어야 한다.

        1개짜리 케이스는 우연히 맞고 틀리고를 구분 못 한다. 정확한 기준치는
        없지만, 지금 가장 얇은 규칙 기준(4개)보다 아래로 떨어지면 회귀로 본다.
        """
        # G01~G06/G08~G10은 조합 생성으로 규칙당 30개 이상이다. G07(위기)만
        # 손으로 신중하게 늘려서 13개로 가장 적다 — 그 아래로 떨어지면 회귀.
        MIN_CASES_PER_RULE = 10
        counts: dict[str, int] = {rule: 0 for rule in ALL_RULES - {"G11"}}
        for case in CASES:
            for rule in case.get("rules", ()):
                if rule in counts:
                    counts[rule] += 1
        thin = {rule: n for rule, n in counts.items() if n < MIN_CASES_PER_RULE}
        self.assertEqual(
            thin, {},
            f"케이스가 {MIN_CASES_PER_RULE}개 미만인 규칙: {thin}. "
            "run_guardrail_eval.py의 CASES에 해당 규칙 케이스를 추가하세요.",
        )

    def test_content_rules_have_a_standalone_non_injection_case(self):
        """G02~G10은 인젝션 기법과 안 섞인 '단독' 케이스가 최소 1개는 있어야 한다.

        combined(인젝션+콘텐츠 위반) 케이스만 있으면, 인젝션 방어와
        콘텐츠 정책 방어 중 뭐가 실제로 막았는지 구분할 수 없다.
        """
        content_rules = ALL_RULES - {"G11"}
        standalone_covered: set[str] = set()
        for case in CASES:
            standalone_covered.update(case.get("rules", ()))
        missing = content_rules - standalone_covered
        self.assertEqual(
            missing, set(),
            f"인젝션과 안 섞인 단독 케이스가 없는 규칙: {sorted(missing)}. "
            "run_guardrail_eval.py의 CASES에 해당 규칙만 겨냥한 케이스를 추가하세요.",
        )


if __name__ == "__main__":
    unittest.main()
