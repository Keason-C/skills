// AUTOMATICALLY GENERATED - DO NOT EDIT.
//
// Source:    schema/triage_result.schema.json (itself generated from the pydantic models)
// Generator: ts/scripts/generate-zod.mjs
// Regenerate: npm run gen
//
// Editing this file by hand would recreate the second-source-of-truth problem the
// generator exists to prevent. test/generated.test.ts fails the build if it is stale.

import { z } from "zod";

export const actionKindSchema = z.enum(["ANSWER_QUESTION", "REQUEST_INFO", "APPROVE_REFUND", "DENY_REFUND", "ISSUE_STORE_CREDIT", "RESET_CREDENTIALS", "INVESTIGATE_TECHNICAL", "ROUTE_TO_HUMAN"]);
export type ActionKind = z.infer<typeof actionKindSchema>;

export const categorySchema = z.enum(["BILLING", "REFUND", "TECHNICAL", "ACCOUNT", "OTHER"]);
export type Category = z.infer<typeof categorySchema>;

export const guardRuleSchema = z.enum(["AMOUNT_THRESHOLD", "LOW_CONFIDENCE", "REFUND_POLICY", "PROMPT_INJECTION", "TERMINAL_ACTION", "PRIORITY_DERIVATION", "UNSUPPORTED_LANGUAGE"]);
export type GuardRule = z.infer<typeof guardRuleSchema>;

export const guardFindingSchema = z.object({
  "detail": z.string().min(1).max(1000),
  "field": z.string().min(1).max(64),
  "final": z.string().min(1).max(64),
  "proposed": z.string().nullable().optional(),
  "rule": guardRuleSchema,
}).strict();
export type GuardFinding = z.infer<typeof guardFindingSchema>;

export const languageSchema = z.enum(["EN", "ZH", "OTHER"]);
export type Language = z.infer<typeof languageSchema>;

export const prioritySchema = z.enum(["P0", "P1", "P2", "P3"]);
export type Priority = z.infer<typeof prioritySchema>;

export const sentimentSchema = z.enum(["ANGRY", "FRUSTRATED", "NEUTRAL", "POSITIVE"]);
export type Sentiment = z.infer<typeof sentimentSchema>;

export const triageStateSchema = z.enum(["NEW", "ENRICHED", "CLASSIFIED", "AUTO_RESOLVED", "ESCALATED"]);
export type TriageState = z.infer<typeof triageStateSchema>;

export const triageResultSchema = z.object({
  "category": categorySchema,
  "confidence": z.number().min(0).max(1),
  "escalated_to_human": z.boolean(),
  "guard_findings": z.array(guardFindingSchema).optional(),
  "injection_detected": z.boolean(),
  "language": languageSchema,
  "llm_calls": z.number().int().min(1).max(2),
  "priority": prioritySchema,
  "rationale": z.string().min(1).max(4000),
  "recommended_action": actionKindSchema,
  "retried": z.boolean(),
  "sentiment": sentimentSchema,
  "state": triageStateSchema,
  "state_path": z.array(triageStateSchema).min(4),
  "ticket_id": z.string().min(1).max(64),
}).strict();
export type TriageResult = z.infer<typeof triageResultSchema>;
