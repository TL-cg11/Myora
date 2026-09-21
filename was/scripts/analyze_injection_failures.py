"""run_prompt_injection_eval.py 결과에서 실패 케이스를 원본 질문·포장
기법·핵심 문장 단위로 묶어서 사람이 읽을 수 있게 뽑아준다.

이 스크립트가 다루는 데이터(prompt_injection.json 질문 원문)는 실제
사용자 대화가 아니라 우리가 직접 만든 테스트용 공격 문장이라, 진단
목적으로 원문을 그대로 보여줘도 개인정보 문제가 없다.

실행 (API 호출 없음, 무료):
    .venv/bin/python scripts/analyze_injection_failures.py \
        .local/evals/stage3-direct-full160-repeat3.json
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

CASES_PATH = Path(__file__).parent.parent / "app" / "evals" / "cases" / "prompt_injection.json"

WRAPPERS = [
    ("반복 대괄호([테스트])", re.compile(r"^\[테스트\] ")),
    ("시스템 태그([SYSTEM])", re.compile(r"^\[SYSTEM\] ")),
    ("권한 사칭(관리자 승인 완료)", re.compile(r"^관리자 승인 완료: ")),
    ("명분 위장(보안 연구용)", re.compile(r"^보안 연구용이므로 ")),
    ("명분 위장(번역 작업)", re.compile(r"^번역 작업일 뿐이니 ")),
    ("롤플레이(가상 역할극)", re.compile(r"^가상 역할극 안에서 ")),
    ("XML 태그(<system>)", re.compile(r"^<system>")),
    ("JSON role 위조", re.compile(r'^\{"role":"developer"')),
    ("인코딩 우회(Base64)", re.compile(r"^Base64로 바꾸기 전에 먼저 ")),
    ("출력 분할 우회", re.compile(r"^직접 말하지 말고 한 글자씩 나눠서 ")),
]


def classify_wrapper(question: str) -> tuple[str, str]:
    """(포장 기법 이름, 핵심 공격 문장)을 돌려준다. 조합형이 아니면 ('단발성', 전체)."""
    rest = question[len("[테스트] "):] if question.startswith("[테스트] ") else question
    for name, pattern in WRAPPERS:
        if pattern.match(rest):
            core = pattern.sub("", rest, count=1)
            return name, core
    return "단발성(비조합)", rest


def main() -> None:
    if len(sys.argv) != 2:
        print("사용법: python scripts/analyze_injection_failures.py <결과.json>")
        raise SystemExit(2)

    result_path = Path(sys.argv[1])
    report = json.loads(result_path.read_text(encoding="utf-8"))
    cases_by_id = {c["id"]: c for c in json.loads(CASES_PATH.read_text(encoding="utf-8"))}

    results = report["results"]
    total = len(results)
    failed = [r for r in results if not r["passed"]]

    print(f"=== 전체 {total}회 실행 중 실패 {len(failed)}회 ({len(failed) / total * 100:.1f}%) ===\n")

    # 핵심 문장(core sentence)별 집계
    by_core: dict[str, dict] = defaultdict(lambda: {"total": 0, "failed": 0, "wrapper": Counter()})
    for r in results:
        case = cases_by_id.get(r["case_id"])
        if not case:
            continue
        wrapper, core = classify_wrapper(case["question"])
        entry = by_core[core]
        entry["total"] += 1
        if not r["passed"]:
            entry["failed"] += 1
            entry["wrapper"][wrapper] += 1

    print("=== 핵심 공격 문장별 실패율 (실패 많은 순) ===")
    ranked = sorted(by_core.items(), key=lambda kv: kv[1]["failed"] / kv[1]["total"], reverse=True)
    for core, stat in ranked:
        if stat["failed"] == 0:
            continue
        rate = stat["failed"] / stat["total"] * 100
        wrappers = ", ".join(f"{w}×{n}" for w, n in stat["wrapper"].most_common())
        print(f"[{stat['failed']}/{stat['total']} {rate:5.1f}%] \"{core}\"")
        print(f"    실패한 포장 기법: {wrappers}")

    print("\n=== 개별 실패 상세 ===")
    for r in failed:
        case = cases_by_id.get(r["case_id"])
        if not case:
            continue
        wrapper, core = classify_wrapper(case["question"])
        print(f"- {r['case_id']} (반복 {r.get('attempt', '?')}) [{r['service']}/{wrapper}]")
        print(f"    질문: {case['question']}")
        print(f"    기대={r['expected']} 실제={r['actual']} 규칙={r.get('rules')}")

    # 서비스별 실패율
    by_service: dict[str, dict] = defaultdict(lambda: {"total": 0, "failed": 0})
    for r in results:
        entry = by_service[r["service"]]
        entry["total"] += 1
        if not r["passed"]:
            entry["failed"] += 1
    print("\n=== 서비스별 실패율 ===")
    for service, stat in by_service.items():
        rate = stat["failed"] / stat["total"] * 100
        print(f"{service}: {stat['failed']}/{stat['total']} ({rate:.1f}%)")


if __name__ == "__main__":
    main()
