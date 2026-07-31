/**
 * zod mirror of the pydantic `TriageResult` model.
 *
 * This is hand-written rather than generated. A generated schema would be an
 * unreadable machine artefact, and the thing that actually protects us is not
 * generation but `test/schema-sync.test.ts`, which asserts field-by-field and
 * enum-by-enum that this file still matches `schema/triage_result.schema.json`.
 * Readable schema, same guarantee.
 */
import { z } from 'zod';

export const enumValues = {
  category: ['BILLING', 'REFUND', 'TECHNICAL', 'ACCOUNT', 'OTHER'],
  priority: ['P0', 'P1', 'P2', 'P3'],
  sentiment: ['ANGRY', 'FRUSTRATED', 'NEUTRAL', 'SATISFIED'],
  language: ['en', 'zh', 'other'],
  triageState: ['NEW', 'ENRICHED', 'CLASSIFIED', 'AUTO_RESOLVED', 'ESCALATED'],
  guardCode: [
    'AMOUNT_THRESHOLD',
    'LOW_CONFIDENCE',
    'PROMPT_INJECTION',
    'P0_ALWAYS_HUMAN',
    'MISSING_ORDER_EVIDENCE',
    'UNSUPPORTED_LANGUAGE',
    'REFUND_POLICY_OVERRIDE',
    'REFUND_POLICY_MISSING',
  ],
} as const;

export const CategorySchema = z.enum(enumValues.category);
export const PrioritySchema = z.enum(enumValues.priority);
export const SentimentSchema = z.enum(enumValues.sentiment);
export const LanguageSchema = z.enum(enumValues.language);
export const GuardCodeSchema = z.enum(enumValues.guardCode);
export const TriageStateSchema = z.enum(enumValues.triageState);

/** The plain object schema — exposes `.shape` for the sync test. */
export const TriageResultObject = z.strictObject({
  ticket_id: z.string().min(1).max(64),
  category: CategorySchema,
  priority: PrioritySchema,
  sentiment: SentimentSchema,
  confidence: z.number().min(0).max(1),
  recommended_action: z.string().min(1).max(500),
  escalated_to_human: z.boolean(),
  rationale: z.string().min(1).max(4000),
  final_state: TriageStateSchema,
  guards_triggered: z.array(GuardCodeSchema).default([]),
  injection_detected: z.boolean().default(false),
  language: LanguageSchema.default('en'),
});

/**
 * The object schema plus the two cross-field invariants pydantic enforces:
 * `final_state` must be terminal, and `escalated_to_human` must agree with it.
 * Without these, a hand-tampered JSON could claim `escalated_to_human: true`
 * next to `final_state: "AUTO_RESOLVED"` and pass a naive field-level check.
 */
export const TriageResultSchema = TriageResultObject.superRefine((value, ctx) => {
  if (value.final_state !== 'AUTO_RESOLVED' && value.final_state !== 'ESCALATED') {
    ctx.addIssue({
      code: 'custom',
      path: ['final_state'],
      message: `final_state must be a terminal state, got ${value.final_state}`,
    });
    return;
  }
  const expected = value.final_state === 'ESCALATED';
  if (value.escalated_to_human !== expected) {
    ctx.addIssue({
      code: 'custom',
      path: ['escalated_to_human'],
      message:
        `escalated_to_human must agree with final_state ` +
        `(final_state=${value.final_state}, escalated_to_human=${value.escalated_to_human})`,
    });
  }
});

export type TriageResult = z.infer<typeof TriageResultSchema>;

/** Parse and validate. Throws `ZodError` with structured issue paths on failure. */
export function parseTriageResult(raw: unknown): TriageResult {
  return TriageResultSchema.parse(raw);
}
