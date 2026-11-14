#!/usr/bin/env bash
# Phase 2 v2 pipeline (after audit-driven fixes):
#   1) Run Phase 2 v2 Long-Thinking Synthesis (N=16 convs x 6 arms = 96 reqs, CONC=3, warmed caches)
#   2) Dual external audit (Claude Fable 5.2 + GPT-6 Astra)
#   3) Trigger Slack report cron job, then remove it (one-shot)
set -u
B=/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks
P2=$B/results/longctx_synthesis_v2_20261114
JOB_P2=${JOB_P2:-b5cb84a20334}
HERMES=/home/joseyarashio/.local/bin/hermes
export PATH=/home/joseyarashio/.local/bin:/usr/local/bin:/usr/bin:/bin

mkdir -p "$P2"; cd "$B"
log(){ echo "$(date '+%F %T') $*" | tee -a "$P2/runner.log"; }

log "=== Phase 2 v2 Full Run (N=16 CONC=3, 96 reqs + warmups) ==="
date -u +%FT%TZ > "$P2/START"
N=16 CONC=3 MAXTOK=32768 timeout 8h python3 "$B/run_longctx_synthesis.py" "$P2/results.jsonl" > "$P2/run.log" 2>&1
rc=$?
echo "rc=$rc" > "$P2/STATUS"
date -u +%FT%TZ > "$P2/END"
log "Phase 2 v2 finished rc=$rc rows=$(wc -l < "$P2/results.jsonl" 2>/dev/null || echo 0)"

log "=== Phase 2 v2 External Audit (Fable 5.2 + GPT-6 Astra) ==="
python3 "$B/run_external_audit.py" "$P2" "Phase 2 v2: Long-Context Synthesis (Long-Thinking), seeds de-duplicated, caches pre-warmed, binding budgets" "$B/run_longctx_synthesis.py" >> "$P2/runner.log" 2>&1
log "Phase 2 v2 Audit rc=$?"
"$HERMES" cron run "$JOB_P2" >> "$P2/runner.log" 2>&1 || true
"$HERMES" cron remove "$JOB_P2" >> "$P2/runner.log" 2>&1 || true
touch "$P2/DONE"
log "=== Pipeline completed ==="
