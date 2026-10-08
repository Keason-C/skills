#!/usr/bin/env bash
P=$1; OUT=$(realpath -m "$2")
mkdir -p "$P/hidden-repro"; cp /tmp/claude-0/bench/hidden/ts/repro/repro.test.ts "$P/hidden-repro/"
cat > "$P/repro.vitest.config.ts" <<'C'
import { defineConfig } from "vitest/config";
export default defineConfig({ test: { include: ["hidden-repro/**/*.test.ts"], testTimeout: 600000 } });
C
(cd "$P" && REPRO_OUT="$OUT" timeout 900 npx vitest run --config repro.vitest.config.ts > "$OUT.log" 2>&1)
rm -rf "$P/hidden-repro" "$P/repro.vitest.config.ts"; cat "$OUT"; echo
