#!/bin/bash
set -euo pipefail

WORKER_IP="10.100.184.1"

echo "=== Switching to GLM-5.3-Flash-EXL3 (320B) ==="

# 1. Stop DeepSeek-V4.1 if running
echo "[1/4] Stopping any DeepSeek-V4.1 processes and containers..."
docker rm -f glm53-flash-tf dsv41-rank0 dsv41-serve 2>/dev/null || true
pkill -f "tf-dsv41-lanes" 2>/dev/null || true
pkill -f "tensorfold-native" 2>/dev/null || true
ssh -o BatchMode=yes joseyarashio@"$WORKER_IP" "docker rm -f glm53-flash-tf dsv41-rank1 dsv41-serve 2>/dev/null || true; pkill -f 'tf-dsv41-lanes' 2>/dev/null || true" 2>/dev/null || true
sudo -n sysctl -w vm.drop_caches=3 >/dev/null 2>&1 || true
ssh -o BatchMode=yes joseyarashio@"$WORKER_IP" "sudo -n sysctl -w vm.drop_caches=3 >/dev/null 2>&1 || true" 2>/dev/null || true
sleep 3

# 2. Start GLM-5.3 via its start script
echo "[2/4] Starting GLM-5.3-Flash-EXL3..."
cd /home/joseyarashio/GLM-5.3-Flash-EXL3-2x-DGX-Sparks-TensorFold
./start.sh restart
docker update --restart unless-stopped glm53-flash-tf >/dev/null 2>&1 || true
ssh -o BatchMode=yes joseyarashio@"$WORKER_IP" "docker update --restart unless-stopped glm53-flash-tf >/dev/null 2>&1 || true" 2>/dev/null || true

# 3. Update OpenCodex provider dgx_spark
echo "[3/4] Updating OpenCodex configuration..."
ocx provider edit dgx_spark --default-model GLM-5.3-Flash-EXL3 2>/dev/null || true
ocx agent subagents set "dgx_spark/GLM-5.3-Flash-EXL3" 2>/dev/null || true
ocx sync >/dev/null 2>&1 || true
ocx integration client enable --client hermes >/dev/null 2>&1 || true
ocx integration client enable --client omp >/dev/null 2>&1 || true

# 4. Verify health
echo "[4/4] Verifying health..."
curl -s http://127.0.0.1:8888/health
echo ""
echo "=== GLM-5.3-Flash-EXL3 is LIVE on port 8888! ==="
