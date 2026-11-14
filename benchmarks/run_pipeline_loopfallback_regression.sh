#!/usr/bin/env bash
# Full regression for the loop-fallback release (engine af133ae9 + proxy loop fallback):
# short-loop probe -> 30-question bank + perf/concurrency -> 1h OmniBench standard.
set -u
B=/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks
OUT="$B/results/loopfallback_regression_20261115"
mkdir -p "$OUT"
cd "$B"
log() { echo "$(date '+%F %T') $*" | tee -a "$OUT/runner.log"; }

log "=== loop-fallback full regression start (engine md5 $(md5sum /home/joseyarashio/TensorFold-dsv41-zig/out/native/bin/tensorfold-native | cut -c1-8), proxy md5 $(md5sum /home/joseyarashio/spark-fastfail-proxy/proxy.py | cut -c1-8)) ==="
log "--- [1/3] short-loop probe (10 prompts) ---"
python3 "$B/run_loop_guard_probe.py" loopfallback 10 > "$OUT/probe.log" 2>&1
log "probe rc=$? ($(tail -n 1 "$OUT/probe.log"))"

log "--- [2/3] 30-question bank + perf/concurrency ---"
python3 "$B/run_full_eval.py" stage2b2_p16_tokenmapfix_loopfallback > "$OUT/full_eval.log" 2>&1
log "full_eval rc=$?"

log "--- [3/3] OmniBench standard + 3600s multi-agent stress ---"
python3 "$B/run_omni_eval.py" --profile standard --duration 3600 \
  --output-report "$B/results/omni_eval_1hour_p16_tokenmapfix_loopfallback.json" > "$OUT/omni.log" 2>&1
log "omni rc=$?"
touch "$OUT/DONE"
log "=== loop-fallback full regression done ==="
