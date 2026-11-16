#!/usr/bin/env bash
# S7: split the 2026-11-15 change (--prompt-cache-gib 2.5->2.0 + MALLOC_ARENA_MAX=4) into its two parts, on p18.
# Arm A (reference, already measured): cache 2.0 + MALLOC_ARENA_MAX=4 = results/so_stage_20261116.
# Arm B: cache 2.0, MALLOC_ARENA_MAX unset          -> effect of the malloc arena cap alone
# Arm C: cache 2.5 + MALLOC_ARENA_MAX=4             -> effect of the cache budget alone (2.0 is the owner's floor)
# Each arm: rank0.sh variant -> restart (start-dsv41.sh) -> 60 s idle -> OmniScenario-1h + mem_sampler -> summary
# -> decode gate reps 3 -> 10 min idle tail. Then restore arm A (rank0.sh.bak.before-s7) and restart.
set -u
PY=/home/joseyarashio/spark-fastfail-proxy/.venv/bin/python
B=/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks
R=/home/joseyarashio/.cache/dsv41-1017-logs
TOP="$B/results/s7_split_20261116"
mkdir -p "$TOP"
log() { echo "$(date '+%F %T') $*" | tee -a "$TOP/runner.log"; }
memline() { echo "n1 $(awk '/MemAvailable/{printf "%.2f", $2/1048576}' /proc/meminfo) GiB, n2 $(ssh -o BatchMode=yes 192.168.10.149 "awk '/MemAvailable/{printf \"%.2f\", \$2/1048576}' /proc/meminfo") GiB"; }
restart() {
  "$1" > "$2" 2>&1
  local rc=$?
  log "restart rc=$rc ($(tail -n 1 "$2"))"
  return $rc
}
cp -p "$R/rank0.sh" "$R/rank0.sh.bak.before-s7"
log "=== S7 start; arm A saved as rank0.sh.bak.before-s7 (sha $(sha256sum "$R/rank0.sh" | cut -c1-8)); $(memline) ==="

for ARM in B C; do
  OUT="$TOP/arm_$ARM"; mkdir -p "$OUT"
  cp -p "$R/rank0.sh.bak.before-s7" "$R/rank0.sh"
  if [ "$ARM" = B ]; then
    sed -i 's/^export MALLOC_ARENA_MAX=4 .*$/# S7 arm B: MALLOC_ARENA_MAX unset/' "$R/rank0.sh"
  else
    sed -i 's/--prompt-cache-gib 2.0/--prompt-cache-gib 2.5/' "$R/rank0.sh"
  fi
  diff "$R/rank0.sh.bak.before-s7" "$R/rank0.sh" > "$OUT/rank0.diff"
  log "arm $ARM rank0.sh diff: $(tr '\n' ' ' < "$OUT/rank0.diff" | cut -c1-200)"
  log "arm $ARM before restart: $(memline)"
  "$PY" "$B/mem_sampler.py" "$OUT/mem" 6000 5 > "$OUT/mem_sampler.log" 2>&1 &
  MS=$!
  if ! restart /home/joseyarashio/start-dsv41.sh "$OUT/restart.log"; then
    log "arm $ARM restart FAILED -> restoring arm A"; touch "$OUT/mem/STOP"; wait $MS; break
  fi
  docker exec dsv41-rank0 sh -c 'tr "\0" "\n" < /proc/1/environ | grep -E "MALLOC|^TF_DS_WINDOW"; tr "\0" " " < /proc/1/cmdline | grep -o -- "--prompt-cache-gib [0-9.]*"' > "$OUT/engine_env.log" 2>&1
  log "arm $ARM engine: $(tr '\n' ' ' < "$OUT/engine_env.log")"
  sleep 60
  log "arm $ARM idle 60 s: $(memline)"
  "$PY" "$B/run_omni_scenario_1h.py" "$OUT/scenario" > "$OUT/scenario.log" 2>&1
  log "arm $ARM scenario rc=$? ($(tail -n 1 "$OUT/scenario.log" | cut -c1-200))"
  "$PY" "$B/summarize_omni_scenario.py" "$OUT/scenario" > "$OUT/scenario_summary.log" 2>&1
  "$PY" "$B/run_decode_gate.py" --reps 3 --label "s7_arm_$ARM" > "$OUT/decode_gate.log" 2>&1
  log "arm $ARM decode gate rc=$? ($(tail -n 1 "$OUT/decode_gate.log" | cut -c1-160))"
  sleep 600
  log "arm $ARM idle tail end: $(memline)"
  docker logs --tail 5000 dsv41-rank0 2>&1 | grep "prompt cache:" | tail -1 > "$OUT/prompt_cache_last.log"
  touch "$OUT/mem/STOP"; wait $MS
done

cp -p "$R/rank0.sh.bak.before-s7" "$R/rank0.sh"
log "restoring arm A (sha $(sha256sum "$R/rank0.sh" | cut -c1-8))"
restart /home/joseyarashio/start-dsv41.sh "$TOP/restore_restart.log"
sleep 30
log "restored: $(memline); engine $(docker exec dsv41-rank0 sh -c 'md5sum $(readlink /proc/1/exe)' | cut -c1-8)"
touch "$TOP/DONE"
log "=== S7 done ==="
