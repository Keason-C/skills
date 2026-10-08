#!/usr/bin/env bash
# scale_ts.sh <project_dir(copy)> <out.json> : each scenario in its own process, 90s hard cap.
P=$1; OUT=$(realpath -m "$2")
mkdir -p "$P/hidden-scale"; cp /tmp/claude-0/bench/hidden/ts/scale/scale.test.ts "$P/hidden-scale/"
cat > "$P/scale.vitest.config.ts" <<'C'
import { defineConfig } from "vitest/config";
export default defineConfig({ test: { include: ["hidden-scale/**/*.test.ts"], testTimeout: 300000 } });
C
echo "{" > "$OUT.tmp"; first=1
for s in independent_20k_c4 chain_5k chain_5k_reverse_add fanout_1_to_10k_fail_cascade diamond_layers_200x20; do
  (cd "$P" && SCALE_ONLY=$s SCALE_OUT="$OUT.$s" timeout 90 npx vitest run --config scale.vitest.config.ts > "$OUT.$s.log" 2>&1)
  v=$(python3 -c "import json,sys;print(json.load(open('$OUT.$s')).get('$s','\"?\"'))" 2>/dev/null || echo '">90000"')
  [ $first = 1 ] || echo "," >> "$OUT.tmp"; first=0; printf '"%s": %s' "$s" "$v" >> "$OUT.tmp"; rm -f "$OUT.$s"
done
echo "}" >> "$OUT.tmp"; mv "$OUT.tmp" "$OUT"
rm -rf "$P/hidden-scale" "$P/scale.vitest.config.ts"
