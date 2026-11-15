#!/bin/bash
# Hibana port S3 quality runner. Arms (ABBA-style): A1 off, B1 4:48:5, C1 4:32:5 (positive control), A2 off (A/A floor).
set -uo pipefail
B=/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks
OUT=$B/results/hibana_port/s3
mkdir -p $OUT
cd $B
arm() {  # name budget(or "") long(1/0)
  local name=$1 bud=$2 long=$3
  if [ -z "$bud" ]; then ./hs2_swap.sh out.hs3 "" "" > $OUT/$name.swap.log 2>&1
  else ./hs2_swap.sh out.hs3 "export TF_DS_MOE_BUDGET=$bud
export TF_DS_MOE_STATS=1" "export TF_DS_MOE_BUDGET=$bud\nexport TF_DS_MOE_STATS=1" > $OUT/$name.swap.log 2>&1; fi
  rm -f /home/joseyarashio/.cache/dsv41-expert-stats/moe_budget.r0.json
  python3 run_hs3_quality.py ${name}_gsm8k --set gsm8k --n 500 --conc 8 --max-tokens 768 >> $OUT/runner.log 2>&1
  cp /home/joseyarashio/.cache/dsv41-expert-stats/moe_budget.r0.json $OUT/${name}_gsm8k.moe_r0.json 2>/dev/null
  if [ "$long" = 1 ]; then
    python3 run_hs3_quality.py ${name}_aime --set aime --n 30 --conc 8 --thinking --max-tokens 12288 >> $OUT/runner.log 2>&1
    cp /home/joseyarashio/.cache/dsv41-expert-stats/moe_budget.r0.json $OUT/${name}_aime.moe_r0.json 2>/dev/null
  fi
  scp -q 10.100.184.1:/home/joseyarashio/.cache/dsv41-expert-stats/moe_budget.r1.json $OUT/${name}.moe_r1.json 2>/dev/null
  echo "$name done $(date +%T)" >> $OUT/runner.log
}
arm A1 "" 1
arm B1 4:48:5 1
arm C1 4:32:5 0
arm A2 "" 0
./hs2_swap.sh prod "" "" > $OUT/restore.swap.log 2>&1
echo "restored $(sha256sum /home/joseyarashio/TensorFold-dsv41-zig/out/native/bin/tensorfold-native | cut -c1-16)" >> $OUT/runner.log
echo DONE >> $OUT/runner.log
