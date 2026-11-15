#!/usr/bin/env bash
# Plan A rerun: harness-only changes (sustained 20 s memory abort + long-context cap 2 x >80K, 450K tokens), production
# unchanged (proxy dbc02a5c). pilot -> full OmniScenario-1h with mem_sampler -> summary -> decode gate reps 3.
set -u
B=/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks
OUT="$B/results/scenario_planA_20261115"
mkdir -p "$OUT"
cd "$B"
log() { echo "$(date '+%F %T') $*" | tee -a "$OUT/runner.log"; }
log "=== plan A start (proxy sha $(sha256sum /home/joseyarashio/spark-fastfail-proxy/proxy.py | cut -c1-8)) ==="
python3 "$B/run_omni_scenario_1h.py" "$OUT/pilot" --pilot > "$OUT/pilot.log" 2>&1
log "pilot rc=$? ($(tail -n 1 "$OUT/pilot.log" | cut -c1-200))"
if grep -q '"kind": "ABORT"' "$OUT/pilot/events.jsonl"; then log "pilot aborted -> stop"; touch "$OUT/DONE"; exit 1; fi
python3 "$B/mem_sampler.py" "$OUT/mem" 9000 5 > "$OUT/mem_sampler.log" 2>&1 &
MS=$!
python3 "$B/run_omni_scenario_1h.py" "$OUT/scenario" > "$OUT/scenario.log" 2>&1
log "scenario rc=$? ($(tail -n 1 "$OUT/scenario.log" | cut -c1-200))"
python3 "$B/summarize_omni_scenario.py" "$OUT/scenario" > "$OUT/scenario_summary.log" 2>&1
python3 "$B/run_decode_gate.py" --reps 3 --label planA_post > "$OUT/decode_gate.log" 2>&1
log "decode gate rc=$? ($(tail -n 1 "$OUT/decode_gate.log" | cut -c1-160))"
sleep 300
touch "$OUT/mem/STOP"; wait $MS
touch "$OUT/DONE"
log "=== done ==="
