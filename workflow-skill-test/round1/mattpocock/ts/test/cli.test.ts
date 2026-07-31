/** Slice 11 — the CLI shell: readable by default, `--json` for machines, non-zero on bad input. */

import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { runCli } from "../src/cli.js";

const VERDICTS = join(import.meta.dirname, "..", "..", "examples", "verdicts");
const AUTO_RESOLVED = join(VERDICTS, "TCK-2001.json");
const ESCALATED = join(VERDICTS, "TCK-2002.json");

describe("triagebot-view", () => {
  it("prints a readable verdict and exits zero", () => {
    const result = runCli([AUTO_RESOLVED]);

    expect(result.exitCode).toBe(0);
    expect(result.stdout).toContain("BILLING");
    expect(result.stderr).toBe("");
  });

  it("prints normalised JSON with --json", () => {
    const result = runCli([ESCALATED, "--json"]);

    expect(result.exitCode).toBe(0);
    expect(JSON.parse(result.stdout).ticket_id).toBe("TCK-2002");
  });

  it("exits non-zero with a clear message when the file is not a valid verdict", () => {
    const result = runCli([join(VERDICTS, "..", "tickets.json")]);

    expect(result.exitCode).not.toBe(0);
    expect(result.stderr).toContain("not a valid triage result");
    expect(result.stdout).toBe("");
  });

  it("exits non-zero when the file does not exist", () => {
    const result = runCli([join(VERDICTS, "nope.json")]);

    expect(result.exitCode).not.toBe(0);
    expect(result.stderr).toBeTruthy();
  });

  it("exits non-zero when no path is given", () => {
    const result = runCli([]);

    expect(result.exitCode).not.toBe(0);
    expect(result.stderr).toContain("usage");
  });
});
