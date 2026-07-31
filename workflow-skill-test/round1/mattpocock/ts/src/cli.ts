/**
 * `triagebot-view <verdict.json> [--json]`
 *
 * The shell is deliberately thin: `runCli` returns what it would have printed and the code it
 * would have exited with, so the behaviour is testable without spawning a process.
 */

import { readFileSync } from "node:fs";

import { formatVerdict, safeParseVerdict } from "./verdict.js";

export interface CliResult {
  readonly stdout: string;
  readonly stderr: string;
  readonly exitCode: number;
}

const USAGE = "usage: triagebot-view <path-to-verdict.json> [--json]";

export function runCli(argv: readonly string[]): CliResult {
  const wantsJson = argv.includes("--json");
  const paths = argv.filter((arg) => !arg.startsWith("--"));

  if (paths.length !== 1) {
    return { stdout: "", stderr: USAGE, exitCode: 2 };
  }

  let raw: string;
  try {
    raw = readFileSync(paths[0]!, "utf-8");
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    return { stdout: "", stderr: `cannot read ${paths[0]}: ${reason}`, exitCode: 2 };
  }

  let payload: unknown;
  try {
    payload = JSON.parse(raw);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    return { stdout: "", stderr: `${paths[0]} is not valid JSON: ${reason}`, exitCode: 2 };
  }

  const outcome = safeParseVerdict(payload);
  if (!outcome.ok) {
    return {
      stdout: "",
      stderr: `${paths[0]} is not a valid triage result — ${outcome.error}`,
      exitCode: 1,
    };
  }

  const stdout = wantsJson
    ? JSON.stringify(outcome.value, null, 2)
    : formatVerdict(outcome.value);
  return { stdout, stderr: "", exitCode: 0 };
}

export function main(argv: readonly string[]): void {
  const result = runCli(argv);
  if (result.stdout) {
    process.stdout.write(`${result.stdout}\n`);
  }
  if (result.stderr) {
    process.stderr.write(`${result.stderr}\n`);
  }
  process.exitCode = result.exitCode;
}
