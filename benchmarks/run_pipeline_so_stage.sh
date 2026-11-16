#!/usr/bin/env bash
# S5 structured output (bertholomus #48/#49/#50 on p17, rank0 out.so md5 3378db64) full regression, no restart:
# idle baseline -> OmniScenario-1h (standard front: full_eval 30-q bank + OmniBench standard, thinking matrix, main load)
# with mem_sampler -> summary -> decode gate reps 3 -> 10 min idle tail.
# Rollback: cp ~/.cache/dsv41-1017-logs/rank0.sh.bak.before-so rank0.sh && ~/start-dsv41.sh
set -u
PY=/home/joseyarashio/spark-fastfail-proxy/.venv/bin/python  # has httpx; /usr/bin/python3 does not
B=/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks
OUT="$B/results/so_stage_20261116"
mkdir -p "$OUT"
cd "$B"
log() { echo "$(date '+%F %T') $*" | tee -a "$OUT/runner.log"; }
memline() { echo "n1 $(awk '/MemAvailable/{printf "%.2f", $2/1048576}' /proc/meminfo) GiB, n2 $(ssh -o BatchMode=yes 192.168.10.149 "awk '/MemAvailable/{printf \"%.2f\", \$2/1048576}' /proc/meminfo") GiB"; }
log "=== so-stage start; engine $(docker exec dsv41-rank0 sh -c 'md5sum $(readlink /proc/1/exe)' | cut -c1-8); $(memline) ==="
"$PY" "$B/mem_sampler.py" "$OUT/mem" 12000 5 > "$OUT/mem_sampler.log" 2>&1 &
MS=$!
"$PY" "$B/run_omni_scenario_1h.py" "$OUT/scenario" > "$OUT/scenario.log" 2>&1
log "scenario rc=$? ($(tail -n 1 "$OUT/scenario.log" | cut -c1-200))"
"$PY" "$B/summarize_omni_scenario.py" "$OUT/scenario" > "$OUT/scenario_summary.log" 2>&1
"$PY" "$B/run_decode_gate.py" --reps 3 --label so_stage_post > "$OUT/decode_gate.log" 2>&1
log "decode gate rc=$? ($(tail -n 1 "$OUT/decode_gate.log" | cut -c1-160))"
sleep 600
log "idle tail end: $(memline)"
touch "$OUT/mem/STOP"; wait $MS
touch "$OUT/DONE"
log "=== done ==="
