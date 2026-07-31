/** Rendering of a validated triage result. Presentation only — no validation. */
import type { TriageResult } from './schema.js';

const LABEL_WIDTH = 20;

function row(label: string, value: string): string {
  return `${(label + ':').padEnd(LABEL_WIDTH)}${value}`;
}

/**
 * Human-readable report. The two things an operator must not miss — a human
 * hand-off and a detected injection attempt — are banner lines at the top
 * rather than fields buried in the body.
 */
export function formatHuman(result: TriageResult): string {
  const lines: string[] = [];
  lines.push(`TriageBot result — ticket ${result.ticket_id}`);
  lines.push('='.repeat(60));

  if (result.escalated_to_human) {
    lines.push('!! ESCALATED TO HUMAN — this ticket was not auto-resolved.');
  }
  if (result.injection_detected) {
    lines.push('!! PROMPT INJECTION DETECTED — the ticket text tried to steer the agent.');
  }
  if (result.escalated_to_human || result.injection_detected) {
    lines.push('-'.repeat(60));
  }

  lines.push(row('Category', result.category));
  lines.push(row('Priority', result.priority));
  lines.push(row('Sentiment', result.sentiment));
  lines.push(row('Confidence', result.confidence.toFixed(2)));
  lines.push(row('Final state', result.final_state));
  lines.push(row('Language', result.language));
  lines.push(row('Recommended action', result.recommended_action));
  lines.push(
    row('Guards triggered', result.guards_triggered.length ? result.guards_triggered.join(', ') : '(none)'),
  );
  lines.push('');
  lines.push('Rationale:');
  lines.push(`  ${result.rationale}`);

  return lines.join('\n');
}

/** Canonical JSON: keys sorted so output is diffable across runs. */
export function formatJson(result: TriageResult): string {
  const sorted = Object.fromEntries(
    Object.entries(result).sort(([a], [b]) => a.localeCompare(b)),
  );
  return JSON.stringify(sorted, null, 2);
}
