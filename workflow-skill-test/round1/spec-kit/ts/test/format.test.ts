/**
 * Presentation (task T062) and the CLI contract (task T059).
 *
 * FR-027 (nothing rendered on a validation failure) and FR-028 (no triage rule is
 * re-implemented here). The second is checked by reading this package's own source: a
 * threshold constant appearing in the TypeScript would mean a rule had leaked across the
 * boundary.
 */

import { readFileSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import { describe, expect, it } from "vitest";
import { formatResult } from "../src/format.js";
import { EXIT_ERROR, EXIT_INVALID, EXIT_OK, run } from "../src/cli.js";
import { triageResultSchema } from "../src/schema.generated.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const EXAMPLES = resolve(HERE, "../../examples");

function example(name: string) {
  return triageResultSchema.parse(JSON.parse(readFileSync(resolve(EXAMPLES, name), "utf8")));
}

describe("formatResult", () => {
  it("renders every headline field", () => {
    const result = example("result_technical.json");
    const output = formatResult(result);
    for (const value of [
      result.ticket_id,
      result.category,
      result.priority,
      result.sentiment,
      result.recommended_action,
      result.language,
    ]) {
      expect(output).toContain(value);
    }
  });

  it("marks an escalated result distinctly", () => {
    expect(formatResult(example("result_refund.json"))).toContain("ESCALATED TO HUMAN");
    expect(formatResult(example("result_technical.json"))).toContain("auto-resolved");
  });

  it("flags a detected injection", () => {
    expect(formatResult(example("result_injection.json"))).toContain("injection");
  });

  it("lists guard findings with their rule names", () => {
    const result = example("result_refund.json");
    const output = formatResult(result);
    expect(result.guard_findings?.length ?? 0).toBeGreaterThan(0);
    for (const finding of result.guard_findings ?? []) {
      expect(output).toContain(finding.rule);
    }
  });

  it("says so explicitly when no rule fired", () => {
    expect(formatResult(example("result_technical.json"))).toContain("none fired");
  });

  it("renders the state path", () => {
    expect(formatResult(example("result_technical.json"))).toContain("NEW -> ENRICHED");
  });

  it("reports the retry count", () => {
    expect(formatResult(example("result_technical.json"))).toContain("Classifier calls:");
  });
});

describe("cli", () => {
  const out: string[] = [];
  const err: string[] = [];
  const capture = () => {
    out.length = 0;
    err.length = 0;
    return {
      out: (m: string) => out.push(m),
      err: (m: string) => err.push(m),
    };
  };

  it("exits 0 and prints a summary for a genuine result", () => {
    const c = capture();
    const code = run([resolve(EXAMPLES, "result_technical.json")], c.out, c.err);
    expect(code).toBe(EXIT_OK);
    expect(out.join("\n")).toContain("T-1001");
    expect(err).toHaveLength(0);
  });

  it("exits 2 and renders NOTHING for an invalid result (FR-027)", () => {
    const path = resolve(tmpdir(), `triagebot-invalid-${process.pid}.json`);
    const doc = JSON.parse(readFileSync(resolve(EXAMPLES, "result_technical.json"), "utf8"));
    doc.confidence = 1.5;
    writeFileSync(path, JSON.stringify(doc), "utf8");

    const c = capture();
    const code = run([path], c.out, c.err);
    expect(code).toBe(EXIT_INVALID);
    expect(out).toHaveLength(0);
    expect(err.join("\n")).toContain("confidence");
  });

  it("exits 1 for a missing file", () => {
    const c = capture();
    expect(run([resolve(tmpdir(), "does-not-exist.json")], c.out, c.err)).toBe(EXIT_ERROR);
    expect(out).toHaveLength(0);
  });

  it("exits 1 for malformed JSON", () => {
    const path = resolve(tmpdir(), `triagebot-bad-${process.pid}.json`);
    writeFileSync(path, "{not json", "utf8");
    const c = capture();
    expect(run([path], c.out, c.err)).toBe(EXIT_ERROR);
  });

  it("exits 1 with usage when given no argument", () => {
    const c = capture();
    expect(run([], c.out, c.err)).toBe(EXIT_ERROR);
    expect(err.join("\n")).toContain("usage");
  });
});

describe("FR-028: no triage rule is re-implemented here", () => {
  const sources = ["../src/format.ts", "../src/cli.ts"].map((rel) =>
    readFileSync(resolve(HERE, rel), "utf8"),
  );

  it("contains no threshold constants", () => {
    for (const source of sources) {
      // 1000 (amount) and 0.6 (confidence) are decisions that belong to Python alone.
      expect(source).not.toMatch(/\b1000\b/);
      expect(source).not.toMatch(/0\.6\b/);
    }
  });

  it("never decides escalation for itself", () => {
    for (const source of sources) {
      expect(source).not.toMatch(/escalated_to_human\s*=/);
    }
  });
});
