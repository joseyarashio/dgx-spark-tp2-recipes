#!/bin/bash
# Health watchdog for the TP=2 serving pair on :8888. Run by spark-dsv41-cluster.timer (boot + every 5 min).
# Heals only when /health stays non-200 for 60 s and no start-dsv41.sh is already running (manual restarts win).
# HEALTH_URL / DRY_RUN=1 exist for testing.
set -uo pipefail
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8888/health}"
LOG=/home/joseyarashio/.cache/dsv41-1017-logs/cluster_watchdog.log
for i in {1..30}; do
  if [ "$(curl -s -m 5 -o /dev/null -w '%{http_code}' "$HEALTH_URL")" = 200 ]; then
    exit 0
  fi
  if pgrep -f '[s]tart-dsv41.sh' >/dev/null; then
    echo "[$(date '+%F %T')] [WATCHDOG] start-dsv41.sh already running; skip." >> "$LOG"
    exit 0
  fi
  sleep 2
done
echo "[$(date '+%F %T')] [WATCHDOG] $HEALTH_URL unhealthy for 60s. Triggering auto-heal (dry_run=${DRY_RUN:-0})..." >> "$LOG"
[ "${DRY_RUN:-0}" = 1 ] && exit 0
if /home/joseyarashio/start-dsv41.sh >> "$LOG" 2>&1; then
  echo "[$(date '+%F %T')] [WATCHDOG] Auto-heal completed." >> "$LOG"
else
  echo "[$(date '+%F %T')] [WATCHDOG] Auto-heal FAILED (exit $?)." >> "$LOG"; exit 1
fi
