/**
 * Validate a TriageBot result file, then format it (task T059).
 *
 * Order matters and is the whole point: validate first, render second. On failure nothing is
 * rendered at all (FR-027) - a partially displayed result is worse than no result, because
 * it looks authoritative.
 *
 * Exit codes (contracts/README.md §3):
 *   0  valid; summary on stdout
 *   2  failed zod validation; per-field issues on stderr
 *   1  file unreadable or not JSON
 */

import { readFileSync } from "node:fs";
import { formatResult } from "./format.js";
import { triageResultSchema } from "./schema.generated.js";

export const EXIT_OK = 0;
export const EXIT_ERROR = 1;
export const EXIT_INVALID = 2;

export function run(argv: string[], out = console.log, err = console.error): number {
  const path = argv[0];
  if (!path) {
    err("usage: npm run cli -- <result.json>");
    return EXIT_ERROR;
  }

  let raw: string;
  try {
    raw = readFileSync(path, "utf8");
  } catch (error) {
    err(`error: cannot read ${path}: ${(error as Error).message}`);
    return EXIT_ERROR;
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch (error) {
    err(`error: ${path} is not valid JSON: ${(error as Error).message}`);
    return EXIT_ERROR;
  }

  const validated = triageResultSchema.safeParse(parsed);
  if (!validated.success) {
    err(`error: ${path} is not a valid triage result`);
    for (const issue of validated.error.issues) {
      const location = issue.path.length > 0 ? issue.path.join(".") : "<root>";
      err(`  ${location}: ${issue.message}`);
    }
    return EXIT_INVALID;
  }

  out(formatResult(validated.data));
  return EXIT_OK;
}

const invokedDirectly = process.argv[1]?.endsWith("cli.ts") || process.argv[1]?.endsWith("cli.js");
if (invokedDirectly) {
  process.exit(run(process.argv.slice(2)));
}
