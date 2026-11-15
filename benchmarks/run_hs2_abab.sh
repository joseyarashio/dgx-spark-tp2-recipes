#!/bin/bash
# Hibana port S2 ABAB: A = budget off (same hs2 build), B = TF_DS_MOE_BUDGET=4:48:5. Same binaries both arms: only the env.
# Each arm: swap + restart + decode gate --reps 2. Results in results/hibana_port/s2_abab/.
set -uo pipefail
B=/home/joseyarashio/dgx-spark-tp2-recipes/benchmarks
OUT=$B/results/hibana_port/s2_abab
mkdir -p $OUT
cd $B
CAND="${CAND:-4:48:5}"
for arm in A1 B1 A2 B2; do
  case $arm in
    A*) ./hs2_swap.sh out.hs2 "" "" > $OUT/$arm.swap.log 2>&1 ;;
    B*) ./hs2_swap.sh out.hs2 "export TF_DS_MOE_BUDGET=$CAND" "export TF_DS_MOE_BUDGET=$CAND" > $OUT/$arm.swap.log 2>&1 ;;
  esac
  python3 run_decode_gate.py --reps 2 --label hs2_abab_$arm > $OUT/$arm.gate.log 2>&1
  echo "$arm $(tail -1 $OUT/$arm.gate.log | cut -c1-260)" >> $OUT/summary.txt
done
./hs2_swap.sh prod "" "" > $OUT/restore.swap.log 2>&1
echo "restored: $(sha256sum /home/joseyarashio/TensorFold-dsv41-zig/out/native/bin/tensorfold-native | cut -c1-16)" >> $OUT/summary.txt
echo DONE >> $OUT/summary.txt
