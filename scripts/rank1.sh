#!/bin/bash
set -euo pipefail
export TF_DS_PROMPT_ALIAS=1
export TF_DS_STREAMS=8
exec /home/joseyarashio/TensorFold-dsv41-zig/out/bin/tf-dsv41-lanes \
  /home/joseyarashio/models/DeepSeek-V4.1-Flash-1017-EXL3-2.9bpw \
  /home/joseyarashio/.cache/dsv41-plusten-rank-cache/tf-ds-rank \
  1 2 10.100.184.2 29620 \
  /home/joseyarashio/dsv41-2m-kit \
  --engram /home/joseyarashio/dsv41-engram-1017 \
  --token-map /home/joseyarashio/.cache/dsv41-1017-rank-cache/dsv41_token_map.json \
  --vision-bias /home/joseyarashio/dsv41-2m-kit/vision/gate_bias_vl.safetensors \
  --pool 2097152 --rdma rocep1s0f1,roceP2p1s0f1 \
  --graphs 1 --side 1 --prefetch 1 --aio 1 \
  --streams 8
