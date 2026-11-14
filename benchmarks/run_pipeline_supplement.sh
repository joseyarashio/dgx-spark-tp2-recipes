#!/usr/bin/env bash
set -u
B=/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks
OUT="$B/results/longctx_supplement_20261114"
mkdir -p "$OUT"
cd "$B"

log() { echo "$(date '+%F %T') $*" | tee -a "$OUT/runner.log"; }

log "=== Phase 2 Supplement Pipeline Start ==="
date -u +%FT%TZ > "$OUT/START"

log "--- Running Suite S1 (85K budget controls + K0_warm, N=8, CONC=3) ---"
python3 "$B/run_longctx_supplement.py" --suite s1 --n-s1 8 --conc-s1 3 "$OUT" >> "$OUT/run_s1.log" 2>&1
log "S1 finished rc=$?"

log "--- Running Suite S2 (~200K + 5 tools x low/medium/high, N=8, CONC=2) ---"
python3 "$B/run_longctx_supplement.py" --suite s2 --n-s2 8 --conc-s2 2 "$OUT" >> "$OUT/run_s2.log" 2>&1
log "S2 finished rc=$?"

log "--- Running Suite S3b (conv_idx=11 loop capture, 4 reps x 2 arms) ---"
python3 "$B/run_longctx_supplement.py" --suite s3b "$OUT" >> "$OUT/run_s3b.log" 2>&1
log "S3b finished rc=$?"

log "--- Summarizing & Running Dual External Audit ---"
python3 "$B/summarize_and_audit_supplement.py" "$OUT" >> "$OUT/audit.log" 2>&1
log "Audit finished rc=$?"

date -u +%FT%TZ > "$OUT/END"
touch "$OUT/DONE"
log "=== Phase 2 Supplement Pipeline Completed ==="
