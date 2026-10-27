#!/bin/bash
set -euo pipefail
export TF_SEED_RANDOM=1
export TF_TOP_K_MAX=56
export TF_DS_PROMPT_ALIAS=1
export TF_FILL_CHUNKS=2
export TF_FILL_FIRST=2
export TF_FILL_CUT_IN=4096
exec /home/joseyarashio/TensorFold-dsv41-zig/out/native/bin/tensorfold-native serve \
  /home/joseyarashio/models/DeepSeek-V4.1-Flash-1017-EXL3-2.9bpw \
  --host 0.0.0.0 --port 8888 --name DeepSeek-V4.1-Flash-1017-TF \
  --alias DeepSeek-V4.1-Flash-TF \
  --alias current \
  --context 1048576 --parallel 4 --thinking --max-tokens 32768 \
  --prompt-cache-gib 2.0 \
  --temperature 0.30 --top-p 0.95 --top-k 20 --backend cuda
