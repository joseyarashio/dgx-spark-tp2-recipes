#!/bin/bash
set -euo pipefail

HEAD_IP="10.100.184.2"
WORKER_IP="10.100.184.1"
PORT="8888"
TF_PORT="29620"

IMAGE="tensorfold-glm53:v0.6.0"
MODEL_DIR="/home/joseyarashio/models/DeepSeek-V4.1-Flash-1017-EXL3-2.7bpw-OOA"
ENGRAM_DIR="/home/joseyarashio/dsv41-engram-1017"
KIT_DIR="/home/joseyarashio/dsv41-1017-kit"
TOKEN_MAP="$KIT_DIR/dsv41_token_map.json"
CACHE_DIR="/home/joseyarashio/.cache/dsv41-ooa-rank-cache/tf-ds-rank"
SERVED_NAME="DeepSeek-V4.1-Flash-1017-TF"

echo "=== Starting DeepSeek-V4.1-Flash-1017-TF (OOA Hybrid 2.7bpw TP=2) ==="

docker rm -f glm53-flash-tf dsv41-rank0 dsv41-serve 2>/dev/null || true
pkill -f "[t]f-dsv41-lanes" 2>/dev/null || true
pkill -f "[t]ensorfold-native" 2>/dev/null || true
ssh -o BatchMode=yes joseyarashio@"$WORKER_IP" "docker rm -f glm53-flash-tf dsv41-rank1 dsv41-serve 2>/dev/null || true; pkill -f '[t]f-dsv41-lanes' 2>/dev/null || true" 2>/dev/null || true
sleep 3
sync
sudo -n sysctl -w vm.drop_caches=3 >/dev/null 2>&1 || true
sudo -n sysctl -w vm.compact_memory=1 >/dev/null 2>&1 || true
ssh -o BatchMode=yes joseyarashio@"$WORKER_IP" "sync; sudo -n sysctl -w vm.drop_caches=3 >/dev/null 2>&1 || true; sudo -n sysctl -w vm.compact_memory=1 >/dev/null 2>&1 || true" 2>/dev/null || true
sleep 1

LOGS_DIR="/home/joseyarashio/.cache/dsv41-ooa-logs"
mkdir -p "$LOGS_DIR"
ssh -o BatchMode=yes joseyarashio@"$WORKER_IP" "mkdir -p '$LOGS_DIR'"

# Generate rank scripts
cat << EOF > "$LOGS_DIR/rank1.sh"
#!/bin/bash
set -euo pipefail
export TF_DS_PROMPT_ALIAS=1
exec /home/joseyarashio/TensorFold-dsv41-zig/out/bin/tf-dsv41-lanes \
  $MODEL_DIR \
  $CACHE_DIR \
  1 2 $HEAD_IP $TF_PORT \
  $KIT_DIR \
  --engram $ENGRAM_DIR \
  --token-map $TOKEN_MAP \
  --vision-bias $KIT_DIR/vision/gate_bias_vl.safetensors \
  --pool 1048576 --rdma rocep1s0f1,roceP2p1s0f1 \
  --graphs 1 --side 1 --prefetch 1 --aio 1
EOF
chmod +x "$LOGS_DIR/rank1.sh"
scp -o BatchMode=yes "$LOGS_DIR/rank1.sh" joseyarashio@"$WORKER_IP":"$LOGS_DIR/rank1.sh"

cat << EOF > "$LOGS_DIR/rank0.sh"
#!/bin/bash
set -euo pipefail
export TF_SEED_RANDOM=1
export TF_TOP_K_MAX=56
export TF_DS_PROMPT_ALIAS=1
export TF_FILL_CHUNKS=2
export TF_FILL_FIRST=2
export TF_FILL_CUT_IN=4096
exec /home/joseyarashio/TensorFold-dsv41-zig/out/native/bin/tensorfold-native serve \
  $MODEL_DIR \
  --host 0.0.0.0 --port $PORT --name $SERVED_NAME \
  --alias DeepSeek-V4.1-Flash-TF \
  --alias current \
  --context 1048576 --parallel 4 --thinking --max-tokens 32768 \
  --prompt-cache-gib 2.0 \
  --temperature 0.30 --top-p 0.95 --top-k 20 --backend cuda
EOF
chmod +x "$LOGS_DIR/rank0.sh"

echo "[2/5] Launching Rank 1 on Worker ($WORKER_IP)..."
ssh -o BatchMode=yes joseyarashio@"$WORKER_IP" "
  docker run -d --restart unless-stopped --name dsv41-rank1 \
    --gpus all --network host --ipc host --ulimit memlock=-1 --ulimit stack=67108864 \
    --cap-add IPC_LOCK --device /dev/infiniband \
    -v /home/joseyarashio:/home/joseyarashio \
    -e TF_DS_REPLAY_FLOOR=1 \
    -e NCCL_IB_HCA=rocep1s0f1,roceP2p1s0f1 \
    -e NCCL_IB_GID_INDEX=3 \
    -e NCCL_SOCKET_IFNAME=enp1s0f1np1 \
    -e TF_RDMA_GID_INDEX=3 \
    --entrypoint /opt/nvidia/nvidia_entrypoint.sh \
    $IMAGE \
    /bin/bash -lc $LOGS_DIR/rank1.sh
"
sleep 2

echo "[3/5] Launching Rank 0 on Head ($HEAD_IP)..."
docker run -d --restart unless-stopped --name dsv41-rank0 \
  --gpus all --network host --ipc host --ulimit memlock=-1 --ulimit stack=67108864 \
  --cap-add IPC_LOCK --device /dev/infiniband \
  -v /home/joseyarashio:/home/joseyarashio \
  -e TF_DS_REPLAY_FLOOR=1 \
  -e TF_TP_WORLD=2 \
  -e TF_TP_MASTER=$HEAD_IP \
  -e TF_TP_PORT=$TF_PORT \
  -e TF_DS_RANK_CACHE=$CACHE_DIR \
  -e TF_DS_KIT=$KIT_DIR \
  -e TENSORFOLD_CUDA_KERNELS=$KIT_DIR/aot \
  -e TF_DS_ENGRAM=$ENGRAM_DIR \
  -e TF_DS_TOKEN_MAP=$TOKEN_MAP \
  -e TF_RDMA_DEVICES=rocep1s0f0,roceP2p1s0f0 \
  -e TF_RDMA_GID_INDEX=3 \
  -e TF_DS_GRAPHS=1 \
  -e TF_DS_HC_SIDE=1 \
  -e TF_DS_L2_PREFETCH=1 \
  -e TF_DS_ENGRAM_AIO=1 \
  -e TF_SEED_RANDOM=1 \
  -e TF_TOP_K_MAX=56 \
  -e NCCL_IB_HCA=rocep1s0f0,roceP2p1s0f0 \
  -e NCCL_IB_GID_INDEX=3 \
  -e NCCL_SOCKET_IFNAME=enp1s0f0np0 \
  --entrypoint /opt/nvidia/nvidia_entrypoint.sh \
  $IMAGE \
  /bin/bash -lc $LOGS_DIR/rank0.sh

echo "[4/5] Waiting for server to become healthy on port $PORT..."
COUNT=0
while [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/health || true)" != "200" ]; do
  sleep 3
  COUNT=$((COUNT + 1))
  echo -n "."
  if [ $COUNT -gt 60 ]; then
    echo "Wait timed out, showing container logs:"
    docker logs --tail 25 dsv41-rank0
    ssh -o BatchMode=yes joseyarashio@"$WORKER_IP" "docker logs --tail 25 dsv41-rank1" 2>/dev/null || true
    exit 1
  fi
done
echo ""
echo "=== DeepSeek-V4.1-Flash-1017-TF (OOA Hybrid) is LIVE on port $PORT! ==="
