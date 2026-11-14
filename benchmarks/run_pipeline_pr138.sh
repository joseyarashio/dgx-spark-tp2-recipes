#!/usr/bin/env bash
# PR #138 live gate: short-loop probe -> long-loop live re-run -> 30-question bank + perf/concurrency (run_full_eval).
set -u
B=/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks
OUT="$B/results/pr138_live_20261114"
mkdir -p "$OUT"
cd "$B"
log() { echo "$(date '+%F %T') $*" | tee -a "$OUT/runner.log"; }

log "=== PR #138 live gate start ==="
log "--- [1/3] short-loop probe (10 prompts) ---"
python3 "$B/run_loop_guard_probe.py" pr138 10 > "$OUT/probe.log" 2>&1
log "probe rc=$? ($(tail -n 1 "$OUT/probe.log"))"

log "--- [2/3] long-loop live re-run (conv1 high x3, conv11 max x3) ---"
python3 "$B/run_pr138_live_check.py" "$OUT/live.jsonl" > "$OUT/live.log" 2>&1
log "live rc=$?"

log "--- [3/3] 30-question bank + perf/concurrency (run_full_eval pr138) ---"
python3 "$B/run_full_eval.py" stage2b2_p16_tokenmapfix_pr138 > "$OUT/full_eval.log" 2>&1
log "full_eval rc=$?"

touch "$OUT/DONE"
log "=== PR #138 live gate done ==="
