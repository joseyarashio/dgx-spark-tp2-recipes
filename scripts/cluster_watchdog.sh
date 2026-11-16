#!/bin/bash
# Health watchdog for the TP=2 serving pair on :8888. Run by spark-dsv41-cluster.timer (boot + every 5 min).
# Heals (start-dsv41.sh) when any of these holds, and no start-dsv41.sh is already running (manual restarts win):
#   1. /health stays non-200 for 60 s.
#   2. The pair is broken while rank0 /health is 200 (2026-11-16: rank1 crash-looped on ncclAllGather for 40 min
#      after Node2 rebooted, and the old check never fired):
#      a. rank1 on Node2 is not running, or its RestartCount grew since the last run. The ring is set up once at
#         start, so a restarted rank1 cannot rejoin the running rank0.
#      b. the engine is idle (running = waiting = 0) and a 1-token request gets no answer within PROBE_S, twice.
# HEALTH_URL / METRICS_URL / CHAT_URL / RANK1_INSPECT / DRY_RUN=1 exist for testing.
set -uo pipefail
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8888/health}"
METRICS_URL="${METRICS_URL:-http://127.0.0.1:8888/metrics}"
CHAT_URL="${CHAT_URL:-http://127.0.0.1:8888/v1/chat/completions}"
RANK1_INSPECT="${RANK1_INSPECT:-ssh -o BatchMode=yes -o ConnectTimeout=10 joseyarashio@10.100.184.1 docker inspect -f '{{.State.Status}}_{{.RestartCount}}_{{.State.StartedAt}}' dsv41-rank1}"
PROBE_S="${PROBE_S:-90}"
RANK0_STARTED="${RANK0_STARTED:-docker inspect -f '{{.State.StartedAt}}' dsv41-rank0}"
LOG="${LOG:-/home/joseyarashio/.cache/dsv41-1017-logs/cluster_watchdog.log}"
STATE="${STATE:-/home/joseyarashio/.cache/dsv41-1017-logs/cluster_watchdog.rank1}"
log() { echo "[$(date '+%F %T')] [WATCHDOG] $*" >> "$LOG"; }

heal() {
  log "$1. Triggering auto-heal (dry_run=${DRY_RUN:-0})..."
  [ "${DRY_RUN:-0}" = 1 ] && exit 0
  if /home/joseyarashio/start-dsv41.sh >> "$LOG" 2>&1; then
    log "Auto-heal completed."
    # record the new rank1 so its fresh RestartCount is the baseline for the next run
    eval "$RANK1_INSPECT" > "$STATE" 2>/dev/null || true
  else
    log "Auto-heal FAILED (exit $?)."; exit 1
  fi
  exit 0
}

if pgrep -f '[s]tart-dsv41.sh' >/dev/null; then
  log "start-dsv41.sh already running; skip."; exit 0
fi

# 1. /health
healthy=0
for i in {1..30}; do
  if [ "$(curl -s -m 5 -o /dev/null -w '%{http_code}' "$HEALTH_URL")" = 200 ]; then healthy=1; break; fi
  if pgrep -f '[s]tart-dsv41.sh' >/dev/null; then log "start-dsv41.sh already running; skip."; exit 0; fi
  sleep 2
done
[ "$healthy" = 1 ] || heal "$HEALTH_URL unhealthy for 60s"

# 2a. rank1 container on Node2
now="$(eval "$RANK1_INSPECT" 2>/dev/null)"
prev="$(cat "$STATE" 2>/dev/null || true)"
if [ -n "$now" ]; then
  echo "$now" > "$STATE"
  st="${now%%_*}"; rest="${now#*_}"; rc="${rest%%_*}"; started="${rest#*_}"
  prc=""; pstarted=""
  if [ -n "$prev" ]; then prest="${prev#*_}"; prc="${prest%%_*}"; pstarted="${prest#*_}"; fi
  if [ "$st" != running ]; then
    heal "rank1 container is $st (RestartCount $rc) while rank0 /health is 200"
  fi
  # A grown counter means docker restarted rank1 in place. start-dsv41.sh recreates the container, which resets
  # the counter to 0, so a manual restart never looks like growth. A rank1 that restarted *before* rank0 started
  # is fine: rebooting Node1 crashes rank1 (peer gone), docker restarts it, and the new rank0 then forms the ring
  # with it (2026-11-16 18:04). Only a restart after rank0 started leaves a rank1 that cannot rejoin.
  if [ -n "$prc" ] && [ "$rc" -gt "$prc" ] 2>/dev/null; then
    r0started="$(eval "$RANK0_STARTED" 2>/dev/null)"
    if [ -n "$r0started" ] && [[ "${started:0:19}" > "${r0started:0:19}" ]]; then
      heal "rank1 restarted after rank0 started (RestartCount $prc -> $rc, rank1 $started > rank0 $r0started) while rank0 /health is 200"
    fi
    log "rank1 RestartCount $prc -> $rc, but it started ($started) before rank0 ($r0started); ring formed after, no heal."
  fi
else
  log "rank1 inspect failed (Node2 unreachable or container missing); /health is 200, not healing on this alone."
fi

# 2b. end-to-end probe, started only when the engine is idle (so a busy engine never looks hung). A hung probe
#     stays counted as running, so the retry does not wait for idle again.
idle() {
  local m; m="$(curl -s -m 5 "$METRICS_URL")" || return 1
  echo "$m" | grep -q '^tensorfold:requests_running 0$' && echo "$m" | grep -q '^tensorfold:requests_waiting 0$'
}
probe() {
  [ "$(curl -s -m "$PROBE_S" -o /dev/null -w '%{http_code}' "$CHAT_URL" -H 'Content-Type: application/json' \
    -d '{"model":"DeepSeek-V4.1-Flash-1017-TF","messages":[{"role":"user","content":"ok"}],"max_tokens":1,"temperature":0,"chat_template_kwargs":{"enable_thinking":false}}')" = 200 ]
}
if idle; then
  probe && exit 0
  sleep 10
  probe && exit 0
  heal "1-token probe got no answer within ${PROBE_S}s twice (first sent while idle) and /health is 200"
fi
exit 0
