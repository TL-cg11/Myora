#!/usr/bin/env bash
# 가드레일 안전성 효과 측정 4단계 대규모 실행 (content/injection/indirect 각 전체×3회).
# 백그라운드로 오래 돌리기 위한 스크립트. 진행 중 터미널을 꺼도(nohup) 계속 실행된다.
#
# 실행:
#   cd ~/luck-was
#   nohup bash scripts/run_stage4_safety_eval.sh > .local/evals/stage4-runner.log 2>&1 &
#   disown
#
# 진행 확인:
#   tail -f .local/evals/stage4-runner.log        # 전체 진행 로그
#   tail -f .local/evals/stage4-content.progress   # content 그룹 실시간 진행률만
#   cat .local/evals/stage4-DONE 2>/dev/null && echo "전부 완료"
#
# 중간에 서버 접속이 끊겨도 nohup+disown 덕분에 계속 돌아간다. 다시 접속해서
# 위 tail 명령어로 진행 상황만 확인하면 된다.

set -uo pipefail
cd "$(dirname "$0")/.."

OUT_DIR=.local/evals
mkdir -p "$OUT_DIR"
rm -f "$OUT_DIR/stage4-DONE"

run_group() {
    local group="$1"
    local max_cases="$2"
    local out_json="$OUT_DIR/stage4-${group}-full${max_cases}-repeat3.json"
    local progress_log="$OUT_DIR/stage4-${group}.progress"

    echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] ${group} 그룹 시작 (max-cases=${max_cases}, repeat=3) ==="
    python -m app.evals.run_guardrail_safety_effect_eval \
        --confirm-live --group "${group}" --max-cases "${max_cases}" --repeat 3 \
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

run_group content 300   || overall_status=1
run_group injection 180 || overall_status=1
run_group indirect 45   || overall_status=1

echo "=== [$(date '+%Y-%m-%d %H:%M:%S')] 전체 3그룹 실행 종료 (overall_status=${overall_status}) ==="
echo "${overall_status}" > "$OUT_DIR/stage4-DONE"
