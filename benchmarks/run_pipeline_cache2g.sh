#!/usr/bin/env bash
# Engine restart with --prompt-cache-gib 2.0 (was 2.5) + MALLOC_ARENA_MAX=4 on rank0, then the full check:
# idle baseline -> OmniScenario-1h (standard front: full_eval + OmniBench standard, thinking matrix, main load) with
# mem_sampler alongside -> summary -> decode gate reps 3 -> 10 min idle tail. Rollback: rank0.sh.bak.before-cache2g.
set -u
B=/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks
OUT="$B/results/cache2g_20261115"
mkdir -p "$OUT"
cd "$B"
log() { echo "$(date '+%F %T') $*" | tee -a "$OUT/runner.log"; }
memline() { echo "n1 $(awk '/MemAvailable/{printf "%.2f", $2/1048576}' /proc/meminfo) GiB, n2 $(ssh -o BatchMode=yes 192.168.10.149 "awk '/MemAvailable/{printf \"%.2f\", \$2/1048576}' /proc/meminfo") GiB"; }
log "=== cache2g start; before restart: $(memline) ==="
python3 "$B/mem_sampler.py" "$OUT/mem" 12000 5 > "$OUT/mem_sampler.log" 2>&1 &
MS=$!
/home/joseyarashio/start-dsv41.sh > "$OUT/restart.log" 2>&1
RC=$?
log "restart rc=$RC ($(tail -n 1 "$OUT/restart.log"))"
if [ $RC -ne 0 ]; then touch "$OUT/mem/STOP"; wait $MS; touch "$OUT/DONE"; exit 1; fi
docker logs dsv41-rank0 2>&1 | grep -E "CUDA sm_121|serving" > "$OUT/engine_banner.log"
docker exec dsv41-rank0 sh -c 'tr "\0" "\n" < /proc/1/environ | grep MALLOC' >> "$OUT/engine_banner.log" 2>&1
sleep 60
log "after restart idle 60 s: $(memline)"
python3 "$B/run_omni_scenario_1h.py" "$OUT/scenario" > "$OUT/scenario.log" 2>&1
log "scenario rc=$? ($(tail -n 1 "$OUT/scenario.log" | cut -c1-200))"
python3 "$B/summarize_omni_scenario.py" "$OUT/scenario" > "$OUT/scenario_summary.log" 2>&1
python3 "$B/run_decode_gate.py" --reps 3 --label cache2g_post > "$OUT/decode_gate.log" 2>&1
log "decode gate rc=$? ($(tail -n 1 "$OUT/decode_gate.log" | cut -c1-160))"
sleep 600
log "idle tail end: $(memline)"
touch "$OUT/mem/STOP"; wait $MS
touch "$OUT/DONE"
log "=== done ==="
