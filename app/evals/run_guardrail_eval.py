"""Run a small, explicit live evaluation against the configured DeepSeek API."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from statistics import median
from time import perf_counter

from app.config import settings
from app.prompts import PERSONA
from app.prompts.guardrail import POLICY_VERSION
from app.services.ai_client import capture_ai_calls
from app.services.guardrail import safe_answer

CASES_DIR = Path(__file__).parent / "cases"


def _load_cases(filename: str) -> tuple[dict, ...]:
    data = json.loads((CASES_DIR / filename).read_text(encoding="utf-8"))
    return tuple({**case, "rules": tuple(case.get("rules", ()))} for case in data)


# 사람이 직접 고른 케이스. G01~G10 골고루 하나씩은 있고, 조합형으로 대량
# 생성한 MATRIX_CASES(content_policy_matrix.json, 생성 스크립트는
# content_policy_matrix.py)와 합쳐서 아래 CASES를 이룬다. G07(위기)은
# MATRIX_CASES에 없다 — 자해·학대 신호에 "농담 삼아" 같은 가벼운 포장을
# 씌우는 게 부적절해서 손으로만 늘렸다. 각 파일의 구성은
# app/evals/cases/README.md 참고.
HAND_PICKED_CASES = _load_cases("content_policy_hand_picked.json")
MATRIX_CASES = _load_cases("content_policy_matrix.json")

CASES = HAND_PICKED_CASES + MATRIX_CASES

CONTEXTS = {
    "saju": '{"pillar_day":"甲子","yongsin":"목","summary":"균형을 설명하는 테스트 결과"}',
    "tarot": '{"spread":"한 장","cards":[{"name":"죽음","orientation":"정방향","meaning":"변화와 마무리"}]}',
    "face": '{"aspect_ratio":1.3,"jaw_ratio":0.8,"summary":"형태 비율 테스트 결과"}',
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="명시적으로 실행하는 DeepSeek 가드레일 평가")
    parser.add_argument("--confirm-live", action="store_true", help="실제 API 호출과 비용 발생을 확인")
    parser.add_argument("--max-cases", type=int, default=1, help="최대 실행 사례 수(기본 1)")
    parser.add_argument("--repeat", type=int, default=1, help="사례별 반복 횟수(기본 1)")
    parser.add_argument("--service", choices=("all", "saju", "tarot", "face"), default="all")
    parser.add_argument("--output", type=Path, help="원문을 제외한 JSON 결과 파일")
    return parser


def selected_cases(service: str, max_cases: int) -> list[dict]:
    if max_cases < 1 or max_cases > len(CASES):
        raise ValueError(f"--max-cases는 1~{len(CASES)}여야 합니다.")
    candidates = [case for case in CASES if service == "all" or case["service"] == service]
    return candidates[:max_cases]


def percentile_95(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, (95 * len(ordered) + 99) // 100 - 1)]


async def evaluate_case(case: dict) -> dict:
    started = perf_counter()
    with capture_ai_calls() as calls:
        result = await safe_answer(
            case["service"], PERSONA[case["service"]], CONTEXTS[case["service"]],
            case["question"],
        )
    actual = result.decision
    return {
        "case_id": case["id"],
        "service": case["service"],
        "expected": case["expected"],
        "actual": actual,
        "rules": list(result.rules),
        "passed": actual == case["expected"],
        "generated": result.generated,
        "elapsed_ms": round((perf_counter() - started) * 1000, 3),
        "call_count": len(calls),
        "calls": calls,
    }


async def run(args: argparse.Namespace) -> dict:
    cases = selected_cases(args.service, args.max_cases)
    if args.repeat < 1:
        raise ValueError("--repeat는 1 이상이어야 합니다.")
    missing = sorted({
        case["service"] for case in cases
        if not getattr(settings, f"deepseek_{case['service']}_api_key")
    })
    if missing:
        raise RuntimeError("API 키가 없는 서비스: " + ", ".join(missing))
    results = []
    total_executions = len(cases) * args.repeat
    run_started = perf_counter()
    print(
        f"평가 시작: 고유 사례 {len(cases)}개 × {args.repeat}회 = "
        f"총 {total_executions}회",
        file=sys.stderr,
        flush=True,
    )
    for case in cases:
        for attempt in range(1, args.repeat + 1):
            result = await evaluate_case(case)
            result["attempt"] = attempt
            results.append(result)
            completed = len(results)
            passed = sum(item["passed"] for item in results)
            failed = completed - passed
            status = "PASS" if result["passed"] else "FAIL"
            percent = completed / total_executions * 100
            print(
                f"[{completed}/{total_executions} {percent:5.1f}%] "
                f"{case['id']} ({case['service']}, 반복 {attempt}/{args.repeat}) "
                f"{status} 기대={result['expected']} 판정={result['actual']} "
                f"호출={result['call_count']} 소요={result['elapsed_ms'] / 1000:.1f}초 "
                f"누적=PASS {passed} / FAIL {failed} "
                f"전체={perf_counter() - run_started:.1f}초",
                file=sys.stderr,
                flush=True,
            )
    elapsed = [item["elapsed_ms"] for item in results]
    calls = [call for item in results for call in item["calls"]]
    known_tokens = [call["total_tokens"] for call in calls if isinstance(call["total_tokens"], int)]
    call_elapsed = [call["elapsed_ms"] for call in calls]
    p95_call = percentile_95(call_elapsed)
    timeout_budget_ok = (
        p95_call is not None
        and p95_call * 3 < settings.ai_total_timeout * 1000
    )
    return {
        "executed_at": datetime.now(UTC).isoformat(),
        "model": settings.ai_guardrail_model,
        "policy_version": POLICY_VERSION,
        "service": args.service,
        "case_count": len(results),
        "unique_case_count": len(cases),
        "repeat": args.repeat,
        "passed": sum(item["passed"] for item in results),
        "failed": sum(not item["passed"] for item in results),
        "total_calls": len(calls),
        "total_tokens": sum(known_tokens) if known_tokens else None,
        "p50_elapsed_ms": round(median(elapsed), 3) if elapsed else None,
        "p95_elapsed_ms": percentile_95(elapsed),
        "p95_call_elapsed_ms": p95_call,
        "ai_total_timeout_ms": settings.ai_total_timeout * 1000,
        "timeout_budget_ok": timeout_budget_ok,
        "results": results,
    }


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.confirm_live:
        parser.error("실제 API 호출에는 --confirm-live가 필요합니다.")
    try:
        report = asyncio.run(run(args))
    except (RuntimeError, ValueError) as error:
        parser.error(str(error))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    else:
        print(rendered)
    return 1 if report["failed"] or not report["timeout_budget_ok"] else 0


if __name__ == "__main__":
    sys.exit(main())
