#!/bin/bash
set -euo pipefail

HEAD_IP="10.100.184.2"
WORKER_IP="10.100.184.1"
PORT="8888"
TF_PORT="29620"

IMAGE="tensorfold-glm53:v0.6.0"
MODEL_DIR="/home/joseyarashio/models/DeepSeek-V4.1-Flash-1017-EXL3-2.9bpw"
ENGRAM_DIR="/home/joseyarashio/dsv41-engram-1017"
KIT_DIR="/home/joseyarashio/dsv41-2m-kit"
TOKEN_MAP="/home/joseyarashio/.cache/dsv41-1017-rank-cache/dsv41_token_map.json"  # compressed Engram map (sha de40bcdd, matches kit engram.json); the kit file is identity

if [ ! -f "$KIT_DIR/vision/gate_bias_vl.safetensors" ]; then
  echo "ERROR: 1017 vision kit is not ready at $KIT_DIR"
  exit 1
fi
# Engram hashes token ids through this map; it must be the one kit engram.json was built with
# (an identity map silently corrupts the Engram rows: the model then "sees" __init__/async def as typos and loops).
python3 - "$TOKEN_MAP" "$KIT_DIR/engram.json" << 'PY'
import hashlib, json, sys
want = json.load(open(sys.argv[2]))["token_map_sha256"]
got = hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest()
if got != want:
    sys.exit(f"ERROR: token map {sys.argv[1]} sha {got[:16]} != engram.json token_map_sha256 {want[:16]}")
print(f"token map ok: {got[:16]} matches engram.json")
PY
ssh -o BatchMode=yes joseyarashio@"$WORKER_IP" "python3 -c 'import hashlib,json,sys; w=json.load(open(\"$KIT_DIR/engram.json\"))[\"token_map_sha256\"]; g=hashlib.sha256(open(\"$TOKEN_MAP\",\"rb\").read()).hexdigest(); sys.exit(0 if g==w else \"ERROR: node2 token map \"+g[:16]+\" != \"+w[:16])'" || exit 1
grep -q -- "--token-map $TOKEN_MAP " <(ssh -o BatchMode=yes joseyarashio@"$WORKER_IP" "tr '\n' ' ' < /home/joseyarashio/.cache/dsv41-1017-logs/rank1.sh") || { echo "ERROR: node2 rank1.sh --token-map is not $TOKEN_MAP"; exit 1; }
CACHE_DIR="/home/joseyarashio/.cache/dsv41-plusten-rank-cache/tf-ds-rank"
SERVED_NAME="DeepSeek-V4.1-Flash-1017-TF"

SERVER_BIN="/home/joseyarashio/TensorFold-dsv41-zig/out/native/bin/tensorfold-native"
LANES_BIN="/home/joseyarashio/TensorFold-dsv41-zig/out/bin/tf-dsv41-lanes"

echo "=== Starting DeepSeek-V4.1-Flash-1017-TF (Native Zig TP=2) ==="

if [ ! -f "$MODEL_DIR/config.json" ] || [ ! -f "$MODEL_DIR/model.safetensors.index.json" ]; then
  echo "ERROR: 1017 EXL3 checkpoint is not ready at $MODEL_DIR"
  exit 1
fi
python3 - "$MODEL_DIR" "$ENGRAM_DIR" << 'PY'
import json, os, sys
model, engram = sys.argv[1], sys.argv[2]
idx = json.load(open(os.path.join(model, "model.safetensors.index.json")))
missing = [n for n in set(idx["weight_map"].values()) if not os.path.isfile(os.path.join(model, n))]
cfg = json.load(open(os.path.join(model, "config.json")))
q = cfg.get("quantization_config") or {}
if q.get("quant_method") != "exl3" or q.get("codebook") != "mul1":
    sys.exit(f"ERROR: {model}/config.json is not EXL3 mul1")
need = {
    "model-00047-of-00048.safetensors": 101_535_150_936,
    "model-00048-of-00048.safetensors": 101_537_926_640,
}
bad = []
for name, size in need.items():
    path = os.path.join(engram, name)
    if not os.path.isfile(path) or os.path.getsize(path) != size:
        bad.append(name)
if missing or bad:
    sys.exit("ERROR: 1017 weights incomplete: shards " + ",".join(missing[:8]) + " engram " + ",".join(bad))
print(f"checkpoint ok: {len(set(idx['weight_map'].values()))} EXL3 shards, 1017 Engram 47+48")
PY

# 1. Stop GLM-5.3 or any DeepSeek if running. Does not touch the 0909 weight dirs.
echo "[1/5] Stopping any running GLM-5.3 or previous DeepSeek..."
cd /home/joseyarashio/GLM-5.3-Flash-EXL3-2x-DGX-Sparks-TensorFold && ./stop.sh 2>/dev/null || true
docker rm -f glm53-flash-tf dsv41-rank0 dsv41-serve 2>/dev/null || true
pkill -f "[t]f-dsv41-lanes" 2>/dev/null || true
pkill -f "[t]ensorfold-native" 2>/dev/null || true
ssh -o BatchMode=yes joseyarashio@"$WORKER_IP" "docker rm -f glm53-flash-tf dsv41-rank1 dsv41-serve 2>/dev/null || true; pkill -f '[t]f-dsv41-lanes' 2>/dev/null || true" 2>/dev/null || true
sleep 3
sync
sudo -n sysctl -w vm.drop_caches=3 >/dev/null 2>&1 || true
sudo -n sysctl -w vm.compact_memory=1 >/dev/null 2>&1 || true
ssh -o BatchMode=yes joseyarashio@"$WORKER_IP" "sync; sudo -n sysctl -w vm.drop_caches=3 >/dev/null 2>&1 || true; sudo -n sysctl -w vm.compact_memory=1 >/dev/null 2>&1 || true" 2>/dev/null || true
mkdir -p "$CACHE_DIR"
ssh -o BatchMode=yes joseyarashio@"$WORKER_IP" "mkdir -p '$CACHE_DIR'"
sleep 1

# 2. Launch Rank 1 on Worker
echo "[2/5] Launching Rank 1 on Worker ($WORKER_IP)..."
ssh -o BatchMode=yes joseyarashio@"$WORKER_IP" "
  docker run -d --restart unless-stopped --name dsv41-rank1 \
    --cpuset-cpus='5-9,15-19' \
    --gpus all --network host --ipc host --ulimit memlock=-1 --ulimit stack=67108864 \
    --cap-add IPC_LOCK --device /dev/infiniband \
    -v /home/joseyarashio:/home/joseyarashio \
    -e TF_DS_REPLAY_FLOOR=1 \
    -e TF_DS_STREAMS=8 \
    -e NCCL_IB_HCA=rocep1s0f1,roceP2p1s0f1 \
    -e NCCL_IB_GID_INDEX=3 \
    -e NCCL_SOCKET_IFNAME=enp1s0f1np1 \
    -e TF_RDMA_GID_INDEX=3 \
    --entrypoint /opt/nvidia/nvidia_entrypoint.sh \
    $IMAGE \
    /bin/bash -lc /home/joseyarashio/.cache/dsv41-1017-logs/rank1.sh
"
sleep 2

# 3. Launch Rank 0 on Head
echo "[3/5] Launching Rank 0 on Head ($HEAD_IP)..."
docker run -d --restart unless-stopped --name dsv41-rank0 \
  --cpuset-cpus='5-9,15-19' \
  --gpus all --network host --ipc host --ulimit memlock=-1 --ulimit stack=67108864 \
  --cap-add IPC_LOCK --device /dev/infiniband \
  -v /home/joseyarashio:/home/joseyarashio \
  -e TF_DS_REPLAY_FLOOR=1 \
  -e TF_DS_STREAMS=8 \
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
  /bin/bash -lc /home/joseyarashio/.cache/dsv41-1017-logs/rank0.sh

echo "[4/5] Waiting for server to become healthy on port $PORT..."
COUNT=0
while [ "$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:$PORT/health || true)" != "200" ]; do
  sleep 4
  COUNT=$((COUNT + 1))
  echo -n "."
  if [ $COUNT -gt 90 ]; then
    echo "Wait timed out, showing container logs:"
    docker logs --tail 25 dsv41-rank0
    ssh -o BatchMode=yes joseyarashio@"$WORKER_IP" "docker logs --tail 25 dsv41-rank1" 2>/dev/null || true
    exit 1
  fi
done
echo ""

IDS="$(curl -sf http://127.0.0.1:$PORT/v1/models | python3 -c 'import sys,json; print("\n".join(m["id"] for m in json.load(sys.stdin)["data"]))')"
printf '%s\n' "$IDS" | grep -qx "$SERVED_NAME" || { echo "ERROR: port $PORT is not serving $SERVED_NAME"; echo "$IDS"; exit 1; }
printf '%s\n' "$IDS" | grep -qx "DeepSeek-V4.1-Flash-TF" || { echo "ERROR: 0909 model id alias missing"; echo "$IDS"; exit 1; }

# 4. Keep OpenCodex on the 0909 model id. This server answers that name as an alias.
echo "[5/5] Updating OpenCodex provider dgx_spark..."
ocx provider edit dgx_spark --default-model DeepSeek-V4.1-Flash-TF 2>/dev/null || true
ocx agent subagents set "dgx_spark/DeepSeek-V4.1-Flash-TF" 2>/dev/null || true
ocx sync >/dev/null 2>&1 || true
ocx integration client enable --client hermes >/dev/null 2>&1 || true
ocx integration client enable --client omp >/dev/null 2>&1 || true

echo "=== $SERVED_NAME is LIVE on port $PORT! ==="
