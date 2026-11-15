#!/bin/bash
# Hibana port S2: swap both ranks to a candidate build (and optional env), restart the pair, verify hashes and env.
# usage: hs2_swap.sh <out-prefix> "<rank0 extra env lines>" "<rank1 env assignments for rank1.sh>"
#   out-prefix: e.g. $PFX (rank0 tensorfold-native and rank1 tf-dsv41-lanes come from it); "prod" restores production
set -euo pipefail
ENG=/home/joseyarashio/TensorFold-dsv41-zig
LOGS=/home/joseyarashio/.cache/dsv41-1017-logs
W=10.100.184.1
PFX="$1"; R0ENV="${2:-}"; R1ENV="${3:-}"
docker rm -f dsv41-rank0 >/dev/null 2>&1 || true
ssh -o BatchMode=yes $W 'docker rm -f dsv41-rank1 >/dev/null 2>&1 || true'
sleep 3
pgrep -x tensorfold-nati >/dev/null && { echo "rank0 still running"; exit 1; }
cp $LOGS/rank0.sh.bak.before-hs1 $LOGS/rank0.sh
ssh -o BatchMode=yes $W "cp $LOGS/rank1.sh.bak.before-hs2 $LOGS/rank1.sh" 2>/dev/null || true
if [ "$PFX" = "prod" ]; then
  cp $ENG/out/native/bin/tensorfold-native.bak.before-hs1 $ENG/out/native/bin/tensorfold-native
  ssh -o BatchMode=yes $W "cp $ENG/out/bin/tf-dsv41-lanes.bak.before-hs2 $ENG/out/bin/tf-dsv41-lanes 2>/dev/null || true"
else
  cp $ENG/$PFX/native/bin/tensorfold-native $ENG/out/native/bin/tensorfold-native
  rsync -a $ENG/$PFX/bin/tf-dsv41-lanes $W:$ENG/out/bin/tf-dsv41-lanes
  if [ -n "$R0ENV" ]; then
    printf '%s\n' "$R0ENV" > /tmp/hs2_r0env
    sed -i '/^export TF_SEED_RANDOM=1$/r /tmp/hs2_r0env' $LOGS/rank0.sh
  fi
  if [ -n "$R1ENV" ]; then
    ssh -o BatchMode=yes $W "sed -i 's|^export TF_DS_STREAMS=8$|export TF_DS_STREAMS=8\n$R1ENV|' $LOGS/rank1.sh"
  fi
fi
echo "rank0 bin: $(sha256sum $ENG/out/native/bin/tensorfold-native | cut -c1-16)"
echo "rank1 bin: $(ssh $W sha256sum $ENG/out/bin/tf-dsv41-lanes | cut -c1-16)"
echo "rank0.sh env: $(grep -E 'MOE_BUDGET|EXPERT_STATS' $LOGS/rank0.sh || echo none)"
echo "rank1.sh env: $(ssh $W "grep -E 'MOE_BUDGET|EXPERT_STATS' $LOGS/rank1.sh" || echo none)"
setsid /home/joseyarashio/start-dsv41.sh > $LOGS/restart_hs2_$(date +%H%M%S).log 2>&1
curl -sf localhost:8888/health >/dev/null && echo HEALTHY
docker logs dsv41-rank0 2>&1 | grep -i -E 'moe budget|expert stats|MoeBudget|error' | head -5
ssh $W "docker logs dsv41-rank1 2>&1 | grep -i -E 'moe budget|MoeBudget|error' | head -5"
