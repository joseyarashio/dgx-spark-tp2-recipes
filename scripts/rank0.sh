#!/bin/bash
set -euo pipefail
export TF_SEED_RANDOM=1
export TF_TOP_K_MAX=56
export TF_DS_PROMPT_ALIAS=1
export TF_FILL_CHUNKS=2
export TF_FILL_FIRST=2
export TF_FILL_CUT_IN=8192
export TF_DS_STREAMS=8
export TF_DS_WINDOW=2097152
export TF_LEARN_TTL_S=86400
DROP_REASONING_FLAG=""
if [ "${DROP_REASONING_HISTORY:-1}" = "1" ]; then
    DROP_REASONING_FLAG="--drop-reasoning-history --keep-last-n-reasoning 2"
fi
exec /home/joseyarashio/TensorFold-dsv41-zig/out/native/bin/tensorfold-native serve \
  /home/joseyarashio/models/DeepSeek-V4.1-Flash-1017-EXL3-2.9bpw \
  --host 0.0.0.0 --port 8888 --name DeepSeek-V4.1-Flash-1017-TF \
  --alias DeepSeek-V4.1-Flash-TF \
  --alias current \
  --context 1048576 --parallel 8 --thinking --max-tokens 32768 \
  $DROP_REASONING_FLAG \
  --prompt-cache-gib 2.5 \
  --learn --learn-dir /home/joseyarashio/.cache/dsv41-nvme-imprint --learn-gib 186.26 \
  --temperature 0.30 --top-p 0.95 --top-k 20 --backend cuda
