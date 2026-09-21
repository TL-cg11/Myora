#!/usr/bin/env bash
# 가드레일 안전성 효과 측정 5단계: --realistic-context로 실제 DB 리딩 컨텍스트를
# 써서 content/injection/indirect 각 전체×3회 대규모 실행.
# 백그라운드로 오래 돌리기 위한 스크립트. 진행 중 터미널을 꺼도(nohup) 계속 실행된다.
#
# 실행:
#   cd ~/luck-was
#   nohup bash scripts/run_stage5_realistic_safety_eval.sh > .local/evals/stage5-runner.log 2>&1 &
#   disown
#
# 진행 확인:
#   tail -f .local/evals/stage5-runner.log         # 전체 진행 로그
#   tail -f .local/evals/stage5-content.progress    # content 그룹 실시간 진행률만
#   cat .local/evals/stage5-DONE 2>/dev/null && echo "전부 완료"
#
# indirect 그룹은 context 자체가 숨겨진 지시문이 든 테스트 페이로드라
# --realistic-context를 붙이지 않는다(4단계와 동일하게 실행).

set -uo pipefail
cd "$(dirname "$0")/.."

OUT_DIR=.local/evals
mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR/stage5-DONE"

run_group() {
    local group="$1"
    local max_cases="$2"
    shift 2
    local extra_args=("$@")
    local out_json="$OUT_DIR/stage5-${group}-full${max_cases}-repeat3.json"
    local progress_log="$OUT_DIR/stage5-${group}.progress"

    echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] ${group} 그룹 시작 (max-cases=${max_cases}, repeat=3, args=${extra_args[*]:-없음}) ==="
    python -m app.evals.run_guardrail_safety_effect_eval \
        --confirm-live --group "${group}" --max-cases "${max_cases}" --repeat 3 \
        "${extra_args[@]}" \
        --output "${out_json}" \
        2> "${progress_log}"
    local status=$?

    if [ $status -eq 0 ] || [ $status -eq 1 ]; then
        echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] ${group} 그룹 완료 (종료코드 ${status}, 결과: ${out_json}) ==="
    else
        echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] ${group} 그룹 비정상 종료 (종료코드 ${status}) — 로그 확인: ${progress_log} ==="
    fi
    return $status
}

overall_status=0

run_group content 300 --realistic-context   || overall_status=1
run_group injection 180 --realistic-context || overall_status=1
run_group indirect 45                        || overall_status=1

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] 전체 3그룹 실행 종료 (overall_status=${overall_status}) ==="
echo "${overall_status}" > "$OUT_DIR/stage5-DONE"
