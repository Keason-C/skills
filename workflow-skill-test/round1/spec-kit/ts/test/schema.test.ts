/**
 * zod validation of triage results - scenarios V24-V26 (task T060).
 *
 * FR-026 (validate before displaying), FR-027 (reject and explain, never partially render),
 * SC-007 (a tampered file is rejected, with the offending field named, for every field).
 *
 * The fixtures are real output from the Python CLI, not hand-written objects: a hand-written
 * fixture only proves the schema accepts what we imagined, which is the failure mode this
 * whole generated-contract arrangement exists to prevent.
 */

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { triageResultSchema } from "../src/schema.generated.js";

const HERE = dirname(fileURLToPath(import.meta.url));
const EXAMPLES = resolve(HERE, "../../examples");

function loadExample(name: string): Record<string, unknown> {
  return JSON.parse(readFileSync(resolve(EXAMPLES, name), "utf8"));
}

const GENUINE = ["result_technical.json", "result_refund.json", "result_injection.json"];

describe("genuine results (V24)", () => {
  it.each(GENUINE)("accepts %s produced by the Python CLI", (name) => {
    const parsed = triageResultSchema.safeParse(loadExample(name));
    expect(parsed.success, JSON.stringify((parsed as never as { error?: unknown }).error)).toBe(
      true,
    );
  });

  it("exposes typed fields after validation", () => {
    const parsed = triageResultSchema.parse(loadExample("result_technical.json"));
    // If these were `any`, the "type-safe formatting" half of US6 would be unserved.
    expect(parsed.ticket_id).toBe("T-1001");
    expect(parsed.state_path[0]).toBe("NEW");
    expect(parsed.category).toBe("TECHNICAL");
  });

  it("covers both terminal states across the fixtures", () => {
    const states = GENUINE.map((name) => triageResultSchema.parse(loadExample(name)).state);
    expect(new Set(states)).toEqual(new Set(["AUTO_RESOLVED", "ESCALATED"]));
  });
});

describe("tampered results (V25, V26)", () => {
  const base = () => loadExample("result_technical.json");

  function expectRejected(mutate: (doc: Record<string, unknown>) => void, field: string) {
    const doc = base();
    mutate(doc);
    const parsed = triageResultSchema.safeParse(doc);
    expect(parsed.success).toBe(false);
    if (!parsed.success) {
      const paths = parsed.error.issues.map((issue) => issue.path.join("."));
      expect(paths.join(",")).toContain(field);
    }
  }

  it("rejects confidence above 1 and names the field (V25)", () => {
    expectRejected((doc) => (doc.confidence = 1.5), "confidence");
  });

  it("rejects negative confidence", () => {
    expectRejected((doc) => (doc.confidence = -0.1), "confidence");
  });

  it("rejects an unknown category (V26)", () => {
    expectRejected((doc) => (doc.category = "FINANCIAL"), "category");
  });

  it("rejects an unknown priority", () => {
    expectRejected((doc) => (doc.priority = "P9"), "priority");
  });

  it("rejects an unknown action", () => {
    expectRejected((doc) => (doc.recommended_action = "PAY_EVERYONE"), "recommended_action");
  });

  it("rejects an unknown state", () => {
    expectRejected((doc) => (doc.state = "PENDING"), "state");
  });

  it("rejects a missing required field", () => {
    expectRejected((doc) => delete doc.rationale, "rationale");
  });

  it("rejects a wrongly typed boolean", () => {
    expectRejected((doc) => (doc.escalated_to_human = "yes"), "escalated_to_human");
  });

  it("rejects an out-of-range llm_calls", () => {
    expectRejected((doc) => (doc.llm_calls = 7), "llm_calls");
  });

  it("rejects a non-integer llm_calls", () => {
    expectRejected((doc) => (doc.llm_calls = 1.5), "llm_calls");
  });

  it("rejects a too-short state path", () => {
    expectRejected((doc) => (doc.state_path = ["NEW"]), "state_path");
  });

  it("rejects an invalid state inside the path", () => {
    expectRejected(
      (doc) => (doc.state_path = ["NEW", "ENRICHED", "CLASSIFIED", "MADE_UP"]),
      "state_path",
    );
  });

  it("rejects an empty rationale", () => {
    expectRejected((doc) => (doc.rationale = ""), "rationale");
  });

  it("rejects an extra unknown property", () => {
    // `extra="forbid"` on the Python side must survive the crossing as `.strict()`.
    const doc = base();
    doc.approved_by_llm = true;
    expect(triageResultSchema.safeParse(doc).success).toBe(false);
  });

  it("rejects a malformed guard finding", () => {
    expectRejected(
      (doc) => (doc.guard_findings = [{ rule: "NOT_A_RULE", field: "x", final: "y", detail: "z" }]),
      "guard_findings",
    );
  });

  it("rejects a guard finding missing its detail", () => {
    expectRejected(
      (doc) => (doc.guard_findings = [{ rule: "AMOUNT_THRESHOLD", field: "x", final: "y" }]),
      "guard_findings",
    );
  });

  it("reports every problem at once, not just the first", () => {
    const doc = base();
    doc.confidence = 9;
    doc.category = "NOPE";
    const parsed = triageResultSchema.safeParse(doc);
    expect(parsed.success).toBe(false);
    if (!parsed.success) expect(parsed.error.issues.length).toBeGreaterThanOrEqual(2);
  });
});
