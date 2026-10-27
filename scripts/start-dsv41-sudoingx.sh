#!/bin/bash
set -euo pipefail

HEAD_IP="10.100.184.2"
WORKER_IP="10.100.184.1"
PORT="8888"

MODEL_DIR="/home/joseyarashio/models/dsv41-exl3"
RECIPE_DIR="/home/joseyarashio/dsv41_recipe"

echo "=== Starting DeepSeek-V4.1-Flash-EXL3-2.7bpw (sudoingX vLLM TP=2) ==="

# 1. Stop any other running models and drop caches
echo "[1/4] Stopping any running GLM-5.3, Bertholomus Zig, or previous sudoingX..."
cd /home/joseyarashio/GLM-5.3-Flash-EXL3-2x-DGX-Sparks-TensorFold && ./stop.sh 2>/dev/null || true
docker rm -f glm53-flash-tf dsv41-rank0 dsv41-serve 2>/dev/null || true
pkill -f "tf-dsv41-lanes" 2>/dev/null || true
pkill -f "tensorfold-native" 2>/dev/null || true
ssh -o BatchMode=yes joseyarashio@"$WORKER_IP" "docker rm -f glm53-flash-tf dsv41-rank1 dsv41-serve 2>/dev/null || true; pkill -f 'tf-dsv41-lanes' 2>/dev/null || true" 2>/dev/null || true

sudo sysctl -w vm.drop_caches=3 >/dev/null 2>&1 || true
ssh -o BatchMode=yes joseyarashio@"$WORKER_IP" "sudo -n sysctl -w vm.drop_caches=3 >/dev/null 2>&1 || true"
sleep 3

# 2. Launch sudoingX TP=2 serve
echo "[2/4] Launching sudoingX TP=2 on port $PORT..."
cd "$RECIPE_DIR"
HEAD="$HEAD_IP" WORKER="$WORKER_IP" \
PORT="$PORT" \
DOCKER_ENV="VLLM_ENGRAM_DISK_SPIN_MS=0" \
SERVED="dsv41 current" \
UTIL="0.85" \
MODEL_DIR="$MODEL_DIR" \
./scripts/launch/dsv41_tp2.sh up

echo "[3/4] Waiting for server to become healthy on port $PORT..."
COUNT=0
while [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/v1/models || true)" != "200" ]; do
  sleep 4
  COUNT=$((COUNT + 1))
  echo -n "."
  if [ $COUNT -gt 60 ]; then
    echo "Wait timed out, showing container logs:"
    docker logs --tail 25 dsv41-serve
    ssh -o BatchMode=yes joseyarashio@"$WORKER_IP" "docker logs --tail 25 dsv41-serve" 2>/dev/null || true
    exit 1
  fi
done
echo ""

# 3. Update OpenCodex provider dgx_spark
echo "[4/4] Updating OpenCodex provider dgx_spark..."
ocx provider edit dgx_spark --default-model dsv41 --base-url http://100.70.199.89:8889/v1 --context-window 262144 2>/dev/null || true
ocx agent subagents set "dgx_spark/dsv41" 2>/dev/null || true
ocx sync >/dev/null 2>&1 || true
ocx integration client enable --client hermes >/dev/null 2>&1 || true
ocx integration client enable --client omp >/dev/null 2>&1 || true

echo "=== DeepSeek-V4.1-Flash (sudoingX) is LIVE on port $PORT! ==="
