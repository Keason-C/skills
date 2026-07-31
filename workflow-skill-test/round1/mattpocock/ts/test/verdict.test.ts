/**
 * Slice 11 — a Verdict the Python side produced validates; a tampered one does not.
 *
 * The fixtures here are real output from `python scripts/triage_demo.py`, not hand-written
 * JSON — that is what makes this a cross-language contract test rather than a restatement
 * of the zod schema.
 */

import { readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { formatVerdict, parseVerdict, safeParseVerdict } from "../src/verdict.js";

const VERDICTS = join(import.meta.dirname, "..", "..", "examples", "verdicts");

function fixture(id: string): unknown {
  return JSON.parse(readFileSync(join(VERDICTS, `${id}.json`), "utf-8"));
}

const AUTO_RESOLVED = fixture("TCK-2001");
const ESCALATED = fixture("TCK-2002");
const INJECTED = fixture("TCK-2004");

describe("validating a Verdict", () => {
  it("accepts an auto-resolved verdict the Python side produced", () => {
    const verdict = parseVerdict(AUTO_RESOLVED);

    expect(verdict.ticket_id).toBe("TCK-2001");
    expect(verdict.category).toBe("BILLING");
    expect(verdict.escalated_to_human).toBe(false);
    expect(verdict.stage).toBe("AUTO_RESOLVED");
  });

  it("accepts an escalated verdict the Python side produced", () => {
    const verdict = parseVerdict(ESCALATED);

    expect(verdict.escalated_to_human).toBe(true);
    expect(verdict.stage).toBe("ESCALATED");
    expect(verdict.guards_fired.length).toBeGreaterThan(0);
  });

  it("accepts every verdict in the examples directory", () => {
    for (const id of ["TCK-2001", "TCK-2002", "TCK-2003", "TCK-2004", "TCK-2005", "TCK-2006"]) {
      expect(() => parseVerdict(fixture(id))).not.toThrow();
    }
  });

  it("rejects a tampered category", () => {
    expect(() => parseVerdict({ ...(AUTO_RESOLVED as object), category: "VIP" })).toThrow();
  });

  it("rejects a confidence outside zero to one", () => {
    expect(() => parseVerdict({ ...(AUTO_RESOLVED as object), confidence: 1.4 })).toThrow();
  });

  it("rejects a missing field", () => {
    const { rationale, ...withoutRationale } = AUTO_RESOLVED as Record<string, unknown>;
    void rationale;

    expect(() => parseVerdict(withoutRationale)).toThrow();
  });

  it("rejects an unexpected extra field", () => {
    expect(() =>
      parseVerdict({ ...(AUTO_RESOLVED as object), override_priority: "P3_LOW" }),
    ).toThrow();
  });

  it("rejects a non-terminal stage", () => {
    expect(() => parseVerdict({ ...(AUTO_RESOLVED as object), stage: "CLASSIFIED" })).toThrow();
  });

  it("rejects a verdict whose escalation flag contradicts its stage", () => {
    expect(() =>
      parseVerdict({ ...(AUTO_RESOLVED as object), escalated_to_human: true }),
    ).toThrow();
  });

  it("reports why an invalid verdict was rejected instead of throwing", () => {
    const outcome = safeParseVerdict({ ...(AUTO_RESOLVED as object), category: "VIP" });

    expect(outcome.ok).toBe(false);
    if (!outcome.ok) {
      expect(outcome.error).toContain("category");
    }
  });
});

describe("formatting a Verdict for a support agent", () => {
  it("shows the category, priority and action", () => {
    const output = formatVerdict(parseVerdict(AUTO_RESOLVED));

    expect(output).toContain("BILLING");
    expect(output).toContain("P3_LOW");
    expect(output).toContain("ROUTE_TO_BILLING");
  });

  it("makes escalation impossible to miss", () => {
    const output = formatVerdict(parseVerdict(ESCALATED));

    expect(output).toContain("ESCALATED TO HUMAN");
  });

  it("makes an injection attempt impossible to miss", () => {
    const output = formatVerdict(parseVerdict(INJECTED));

    expect(output).toContain("INJECTION ATTEMPT");
  });

  it("says nothing alarming about a clean auto-resolved ticket", () => {
    const output = formatVerdict(parseVerdict(AUTO_RESOLVED));

    expect(output).not.toContain("ESCALATED TO HUMAN");
    expect(output).not.toContain("INJECTION ATTEMPT");
    expect(output).toContain("AUTO-RESOLVED");
  });

  it("lists the guards that fired", () => {
    const output = formatVerdict(parseVerdict(ESCALATED));

    expect(output.toLowerCase()).toContain("refund-execution");
  });
});
