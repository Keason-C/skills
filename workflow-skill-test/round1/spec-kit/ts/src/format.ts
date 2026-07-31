/**
 * Presentation for a validated triage result (task T058).
 *
 * This module re-implements no triage rule (FR-028). It never recomputes a priority, never
 * decides whether something should have escalated, never second-guesses a guard. It receives
 * a value that has already passed zod validation and renders it. Every judgement visible in
 * the output was made in Python.
 */

import type { GuardFinding, TriageResult } from "./schema.generated.js";

const VERDICT_LABEL: Record<string, string> = {
  AUTO_RESOLVED: "auto-resolved",
  ESCALATED: "ESCALATED TO HUMAN",
};

function formatConfidence(value: number): string {
  return `${(value * 100).toFixed(0)}%`;
}

function formatFinding(finding: GuardFinding): string {
  const change =
    finding.proposed === null || finding.proposed === undefined
      ? `set ${finding.field} = ${finding.final}`
      : `${finding.field}: ${finding.proposed} -> ${finding.final}`;
  return `    - [${finding.rule}] ${change}\n      ${finding.detail}`;
}

/** Render a validated result as a human-readable summary. */
export function formatResult(result: TriageResult): string {
  const lines: string[] = [];

  const verdict = VERDICT_LABEL[result.state] ?? result.state;
  lines.push(`Ticket ${result.ticket_id} - ${verdict}`);
  lines.push("=".repeat(Math.max(24, `Ticket ${result.ticket_id} - ${verdict}`.length)));
  lines.push(`  Category:    ${result.category}`);
  lines.push(`  Priority:    ${result.priority}`);
  lines.push(`  Sentiment:   ${result.sentiment}`);
  lines.push(`  Confidence:  ${formatConfidence(result.confidence)}`);
  lines.push(`  Action:      ${result.recommended_action}`);
  lines.push(`  Language:    ${result.language}`);

  if (result.injection_detected) {
    lines.push("  ⚠ Prompt injection detected - handled as a security event.");
  }

  lines.push(
    `  Classifier calls: ${result.llm_calls}${result.retried ? " (retried once)" : ""}`,
  );
  lines.push(`  State path:  ${result.state_path.join(" -> ")}`);

  const findings = result.guard_findings ?? [];
  if (findings.length === 0) {
    lines.push("  Deterministic rules: none fired.");
  } else {
    lines.push(`  Deterministic rules that fired (${findings.length}):`);
    for (const finding of findings) lines.push(formatFinding(finding));
  }

  lines.push("  Rationale:");
  for (const line of result.rationale.split("\n")) lines.push(`    ${line}`);

  return lines.join("\n");
}
