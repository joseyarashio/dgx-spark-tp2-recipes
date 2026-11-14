#!/usr/bin/env bash
# Final gate for the PR #138 default build (out.pr138stop binary, run WITHOUT --loop-guard-stop):
# 30-question bank + perf/concurrency (run_full_eval), then the 1-hour standard OmniBench, same as the
# omni_eval_1hour_p16_tokenmapfix.json baseline.
set -u
B=/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks
OUT="$B/results/pr138_final_gate_20261114"
mkdir -p "$OUT"
cd "$B"
log() { echo "$(date '+%F %T') $*" | tee -a "$OUT/runner.log"; }

log "=== PR #138 final gate start (engine md5 $(md5sum /home/joseyarashio/TensorFold-dsv41-zig/out/native/bin/tensorfold-native | cut -c1-8)) ==="
log "--- [1/2] 30-question bank + perf/concurrency ---"
python3 "$B/run_full_eval.py" stage2b2_p16_tokenmapfix_pr138final > "$OUT/full_eval.log" 2>&1
log "full_eval rc=$?"

log "--- [2/2] OmniBench standard + 3600s multi-agent stress ---"
python3 "$B/run_omni_eval.py" --profile standard --duration 3600 \
  --output-report "$B/results/omni_eval_1hour_p16_tokenmapfix_pr138.json" > "$OUT/omni.log" 2>&1
log "omni rc=$?"
touch "$OUT/DONE"
log "=== PR #138 final gate done ==="
