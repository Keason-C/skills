#!/usr/bin/env bash
# fuzz_ts.sh <project_dir(copy, will be modified)> <out.json>
set -e
P=$1; OUT=$(realpath -m "$2")
mkdir -p "$P/hidden-fuzz"; cp /tmp/claude-0/bench/hidden/ts/fuzz/fuzz.test.ts "$P/hidden-fuzz/"
cat > "$P/fuzz.vitest.config.ts" <<'C'
import { defineConfig } from "vitest/config";
export default defineConfig({ test: { include: ["hidden-fuzz/**/*.test.ts"], testTimeout: 600000 } });
C
cd "$P" && FUZZ_OUT="$OUT" FUZZ_SEEDS=${FUZZ_SEEDS:-400} npx vitest run --config fuzz.vitest.config.ts > "$OUT.log" 2>&1 || true
rm -rf "$P/hidden-fuzz" "$P/fuzz.vitest.config.ts"
