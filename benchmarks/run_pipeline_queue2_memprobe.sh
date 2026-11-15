#!/usr/bin/env bash
# Proxy queue reservation 1 -> 2 spots for P0/P1 (patch 0069) regression + Node1 memory measurement run.
# truth table -> full_eval (30q + perf + D) -> smoke -> OmniScenario-1h with mem_sampler (5 s) alongside.
set -u
B=/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks
OUT="$B/results/queue2_memprobe_20261115"
mkdir -p "$OUT"
cd "$B"
log() { echo "$(date '+%F %T') $*" | tee -a "$OUT/runner.log"; }
log "=== queue2 + memprobe start (proxy sha $(sha256sum /home/joseyarashio/spark-fastfail-proxy/proxy.py | cut -c1-8)) ==="
python3 "$B/mem_sampler.py" "$OUT/mem" 9000 5 > "$OUT/mem_sampler.log" 2>&1 &
MS=$!
/home/joseyarashio/spark-fastfail-proxy/.venv/bin/python "$B/test_proxy_thinking_switch.py" > "$OUT/truth_table.log" 2>&1
log "truth table rc=$? ($(tail -n 1 "$OUT/truth_table.log"))"
python3 "$B/run_full_eval.py" stage2b2_p17_queue2 > "$OUT/full_eval.log" 2>&1
log "full_eval rc=$? ($(grep 'Question Bank Overall' "$OUT/full_eval.log"))"
python3 "$B/run_omni_eval.py" --profile smoke --output-report "$B/results/omni_eval_smoke_queue2.json" > "$OUT/smoke.log" 2>&1
log "smoke rc=$?"
python3 "$B/run_omni_scenario_1h.py" "$OUT/scenario" > "$OUT/scenario.log" 2>&1
log "scenario rc=$?"
python3 "$B/summarize_omni_scenario.py" "$OUT/scenario" > "$OUT/scenario_summary.log" 2>&1
python3 "$B/run_decode_gate.py" --reps 3 --label queue2_post > "$OUT/decode_gate.log" 2>&1
log "decode gate rc=$? ($(tail -n 1 "$OUT/decode_gate.log" | cut -c1-120))"
sleep 600   # 10 min idle tail for the memory recovery curve
touch "$OUT/mem/STOP"; wait $MS
touch "$OUT/DONE"
log "=== done ==="
