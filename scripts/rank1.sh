#!/bin/bash
set -euo pipefail
export TF_DS_PROMPT_ALIAS=1
exec /home/joseyarashio/TensorFold-dsv41-zig/out/bin/tf-dsv41-lanes \
  /home/joseyarashio/models/DeepSeek-V4.1-Flash-1017-EXL3-2.9bpw \
  /home/joseyarashio/.cache/dsv41-1017-rank-cache/tf-ds-rank \
  1 2 10.100.184.2 29620 \
  /home/joseyarashio/dsv41-1017-kit \
  --engram /home/joseyarashio/dsv41-engram-1017 \
  --token-map /home/joseyarashio/dsv41-1017-kit/dsv41_token_map.json \
  --vision-bias /home/joseyarashio/dsv41-1017-kit/vision/gate_bias_vl.safetensors \
  --pool 1048576 --rdma rocep1s0f1,roceP2p1s0f1 \
  --graphs 1 --side 1 --prefetch 1 --aio 1
