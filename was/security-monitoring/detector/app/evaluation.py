# 합성 정답 데이터와 실제 결과를 비교해 규칙별 정확도와 마스킹 성공 여부를 평가한다.
"""Rule-presence metrics per log, plus exact masking checks; not span-level NER metrics."""
import argparse
import json
from pathlib import Path

from .engine import process_log


# 로그별 규칙 존재 여부와 기대 마스킹 결과를 비교한다. 개별 구간 정확도 평가는 아니다.
def evaluate(dataset: dict) -> dict:
    counts = {}
    errors = []
    for index, case in enumerate(dataset["cases"], 1):
        result = process_log(case["input"])
        expected = case["expected"]
        actual = set(result.masked_log.detected_rules) if result.masked_log else set()
        wanted = set(expected["rules"])
        # 정답과 실제에 모두 있으면 TP, 실제에만 있으면 FP, 정답에만 있으면 FN이다.
        for rule in wanted | actual:
            stat = counts.setdefault(rule, {"tp": 0, "fp": 0, "fn": 0})
            stat["tp" if rule in wanted and rule in actual else "fp" if rule in actual else "fn"] += 1
        match = result.failure is None and actual == wanted
        if result.masked_log is not None:
            if "masked_body" in expected:
                match &= result.masked_log.body_masked == expected["masked_body"]
            if "masked_attributes" in expected:
                match &= result.masked_log.attributes == expected["masked_attributes"]
            for key in ("risk_level", "risk_score"):
                if key in expected:
                    match &= getattr(result.masked_log, key) == expected[key]
        if not match:
            # Do not include case payloads or names from untrusted datasets.
            errors.append(index)

    # Precision=TP/(TP+FP), Recall=TP/(TP+FN), F1을 계산한다. 분모 0은 None이다.
    def metrics(stat):
        tp, fp, fn = stat["tp"], stat["fp"], stat["fn"]
        return {**stat, "precision": tp / (tp + fp) if tp + fp else None,
                "recall": tp / (tp + fn) if tp + fn else None,
                "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None}

    # micro 지표는 규칙별 지표의 평균이 아니라 전체 TP/FP/FN을 합친 뒤 계산한다.
    total = {key: sum(s[key] for s in counts.values()) for key in ("tp", "fp", "fn")}
    return {"dataset_version": dataset["dataset_version"], "metric_unit": "rule presence per log",
            "cases": len(dataset["cases"]), "passed_cases": len(dataset["cases"]) - len(errors),
            "failed_case_numbers": errors, "micro": metrics(total),
            "rules": {rule: metrics(stat) for rule, stat in sorted(counts.items())}}


# 명령행 인자를 해석하고 처리 결과에 맞는 종료 코드를 반환한다.
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixtures", type=Path, default=Path(__file__).resolve().parents[1] / "tests/fixtures/cases.json")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = evaluate(json.loads(args.fixtures.read_text(encoding="utf-8")))
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as stream:
            stream.write(rendered + "\n")
    print(rendered)
    return 1 if report["failed_case_numbers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
