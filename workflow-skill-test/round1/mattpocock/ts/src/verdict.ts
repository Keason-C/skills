/**
 * The Verdict, as TypeScript sees it.
 *
 * This schema mirrors the JSON Schema exported from the pydantic models in `schema/`. It is
 * strict on purpose: an unknown field means the two sides have drifted, and that is a failure,
 * not something to shrug off.
 */

import { z } from "zod";

export const CATEGORIES = ["BILLING", "REFUND", "TECHNICAL", "ACCOUNT", "OTHER"] as const;
export const PRIORITIES = ["P0_URGENT", "P1_HIGH", "P2_NORMAL", "P3_LOW"] as const;
export const SENTIMENTS = ["ANGRY", "FRUSTRATED", "NEUTRAL", "SATISFIED"] as const;
export const ACTIONS = [
  "AUTO_REFUND",
  "REQUEST_MORE_INFO",
  "ROUTE_TO_BILLING",
  "ROUTE_TO_TECH_SUPPORT",
  "ROUTE_TO_ACCOUNT_TEAM",
  "SEND_SELF_SERVE_GUIDE",
  "ESCALATE_TO_HUMAN",
] as const;
export const TERMINAL_STAGES = ["AUTO_RESOLVED", "ESCALATED"] as const;

export const VerdictSchema = z
  .strictObject({
    ticket_id: z.string().min(1).max(64),
    category: z.enum(CATEGORIES),
    priority: z.enum(PRIORITIES),
    sentiment: z.enum(SENTIMENTS),
    confidence: z.number().min(0).max(1),
    recommended_action: z.enum(ACTIONS),
    escalated_to_human: z.boolean(),
    injection_detected: z.boolean(),
    stage: z.enum(TERMINAL_STAGES),
    rationale: z.string().min(1).max(4000),
    guards_fired: z.array(z.string().min(1)),
  })
  .refine(
    (verdict) => verdict.escalated_to_human === (verdict.stage === "ESCALATED"),
    "escalated_to_human and stage disagree: a verdict is escalated in both places or neither",
  );

export type Verdict = z.infer<typeof VerdictSchema>;

export type ParseOutcome =
  | { readonly ok: true; readonly value: Verdict }
  | { readonly ok: false; readonly error: string };

/** Validate a Verdict, throwing on anything that does not conform. */
export function parseVerdict(input: unknown): Verdict {
  return VerdictSchema.parse(input);
}

/** Validate a Verdict, reporting the reason instead of throwing. */
export function safeParseVerdict(input: unknown): ParseOutcome {
  const result = VerdictSchema.safeParse(input);
  if (result.success) {
    return { ok: true, value: result.data };
  }
  const reasons = result.error.issues.map((issue) => {
    const path = issue.path.join(".");
    return path ? `${path}: ${issue.message}` : issue.message;
  });
  return { ok: false, error: reasons.join("; ") };
}

const LABEL_WIDTH = 12;

function row(label: string, value: string): string {
  return `${(label + ":").padEnd(LABEL_WIDTH)} ${value}`;
}

/** Render a Verdict for a support agent reading their terminal. */
export function formatVerdict(verdict: Verdict): string {
  const banners: string[] = [];
  if (verdict.injection_detected) {
    banners.push("!! INJECTION ATTEMPT — this ticket tried to instruct the triage system !!");
  }
  if (verdict.escalated_to_human) {
    banners.push(">> ESCALATED TO HUMAN — do not close without a person <<");
  } else {
    banners.push("-- AUTO-RESOLVED — no human action required --");
  }

  const lines = [
    `Ticket ${verdict.ticket_id}`,
    ...banners,
    "",
    row("Category", verdict.category),
    row("Priority", verdict.priority),
    row("Sentiment", verdict.sentiment),
    row("Confidence", verdict.confidence.toFixed(2)),
    row("Action", verdict.recommended_action),
    row(
      "Guards",
      verdict.guards_fired.length > 0 ? verdict.guards_fired.join(", ") : "none fired",
    ),
    "",
    "Rationale:",
    verdict.rationale,
  ];

  return lines.join("\n");
}
