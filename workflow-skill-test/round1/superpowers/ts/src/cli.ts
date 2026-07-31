#!/usr/bin/env -S npx tsx
/**
 * triagebot-view <file.json> [--json]
 *
 * `run()` returns its output instead of printing it so the whole CLI is
 * testable without capturing process streams or spawning a subprocess.
 */
import { readFileSync } from 'node:fs';
import { z } from 'zod';

import { formatHuman, formatJson } from './format.js';
import { parseTriageResult } from './schema.js';

export interface CliResult {
  stdout: string;
  exitCode: number;
}

const USAGE = 'usage: triagebot-view <file.json> [--json]';

export function run(argv: string[]): CliResult {
  const wantJson = argv.includes('--json');
  const positional = argv.filter((arg) => !arg.startsWith('--'));

  if (positional.length !== 1) {
    return { stdout: USAGE, exitCode: 1 };
  }
  const path = positional[0]!;

  let raw: unknown;
  try {
    raw = JSON.parse(readFileSync(path, 'utf8'));
  } catch (error) {
    return { stdout: `Could not read JSON from ${path}: ${(error as Error).message}`, exitCode: 1 };
  }

  try {
    const result = parseTriageResult(raw);
    return { stdout: wantJson ? formatJson(result) : formatHuman(result), exitCode: 0 };
  } catch (error) {
    if (error instanceof z.ZodError) {
      const issues = error.issues
        .map((issue) => `  ${issue.path.join('.') || '(root)'}: ${issue.message}`)
        .join('\n');
      return { stdout: `Invalid triage result in ${path}:\n${issues}`, exitCode: 1 };
    }
    throw error;
  }
}

// Only run when invoked directly, so importing this module in tests is inert.
if (process.argv[1] && import.meta.url === `file://${process.argv[1]}`) {
  const result = run(process.argv.slice(2));
  console.log(result.stdout);
  process.exit(result.exitCode);
}
