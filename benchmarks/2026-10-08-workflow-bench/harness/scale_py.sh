#!/usr/bin/env bash
# scale_py.sh <impl_dir> <out.json>
OUT=$2; echo "{" > $OUT.tmp; first=1
for s in chain_100k sum_100k_edits range_index_2k_formulas fanout_20k insert_rows_50k copy_block_100x50; do
  r=$(timeout 120 python3 -I /tmp/claude-0/bench/hidden/py/scale/scale_py.py "$1" $s 2>/dev/null | tail -1)
  [ -z "$r" ] && r='"fail/timeout" "?"'
  set -- "$1" "$2"; m=$(echo $r | cut -d' ' -f1); tot=$(echo $r | cut -d' ' -f2)
  [ $first = 1 ] || echo "," >> $OUT.tmp; first=0; printf '"%s": [%s, %s]' $s "$m" "$tot" >> $OUT.tmp
done; echo "}" >> $OUT.tmp; mv $OUT.tmp $OUT; cat $OUT
