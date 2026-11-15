#!/usr/bin/env bash
# Regression for the proxy thinking-switch fix (proxy.py sha 820be1d6, was e2039614):
# offline truth table -> live alias check -> loop-fallback functional check -> 30-question bank + perf/concurrency
# -> OmniBench smoke. The engine is unchanged; this only exercises the proxy's request rewrites and queue paths.
set -u
B=/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks
OUT="$B/results/thinkalias_fix_20261115"
mkdir -p "$OUT"
cd "$B"
log() { echo "$(date '+%F %T') $*" | tee -a "$OUT/runner.log"; }
log "=== thinkalias regression start (proxy sha $(sha256sum /home/joseyarashio/spark-fastfail-proxy/proxy.py | cut -c1-8)) ==="
/home/joseyarashio/spark-fastfail-proxy/.venv/bin/python "$B/test_proxy_thinking_switch.py" > "$OUT/truth_table.log" 2>&1
log "truth table rc=$? ($(tail -n 1 "$OUT/truth_table.log"))"
python3 "$B/run_loop_fallback_check.py" "$OUT/loop_fallback_check.jsonl" > "$OUT/loop_fallback_check.log" 2>&1
log "loop fallback check rc=$? ($(tail -n 1 "$OUT/loop_fallback_check.log"))"
python3 "$B/run_full_eval.py" stage2b2_p17_thinkalias > "$OUT/full_eval.log" 2>&1
log "full_eval rc=$?"
python3 "$B/run_omni_eval.py" --profile smoke --output-report "$B/results/omni_eval_smoke_thinkalias.json" > "$OUT/smoke.log" 2>&1
log "smoke rc=$?"
touch "$OUT/DONE"
log "=== thinkalias regression done ==="
