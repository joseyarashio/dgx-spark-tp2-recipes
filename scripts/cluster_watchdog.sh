#!/bin/bash
set -euo pipefail
# Watchdog loop for Spark Cluster port 8888
for i in {1..30}; do
  if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8888/health | grep -q 200; then
    exit 0
  fi
  sleep 2
done
# If port 8888 not healthy after 60s, trigger cluster recovery
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WATCHDOG] Port 8888 unhealthy. Triggering auto-heal..." >> /home/joseyarashio/.cache/dsv41-1017-logs/cluster_watchdog.log
/home/joseyarashio/start-dsv41.sh >> /home/joseyarashio/.cache/dsv41-1017-logs/cluster_watchdog.log 2>&1
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [WATCHDOG] Auto-heal completed successfully." >> /home/joseyarashio/.cache/dsv41-1017-logs/cluster_watchdog.log
