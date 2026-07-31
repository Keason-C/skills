import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { parseTriageResult } from '../src/schema.js';

const valid = JSON.parse(
  readFileSync(fileURLToPath(new URL('./fixtures/valid-result.json', import.meta.url)), 'utf8'),
);

describe('zod validation of real pydantic output', () => {
  it('accepts a result produced by the python engine', () => {
    expect(() => parseTriageResult(valid)).not.toThrow();
  });

  it('returns a typed object with the expected category', () => {
    expect(parseTriageResult(valid).category).toBe('REFUND');
  });

  it('rejects a category outside the enum', () => {
    expect(() => parseTriageResult({ ...valid, category: 'SUPERURGENT' })).toThrow();
  });

  it('rejects a priority outside the enum', () => {
    expect(() => parseTriageResult({ ...valid, priority: 'P9' })).toThrow();
  });

  it('rejects a confidence above 1', () => {
    expect(() => parseTriageResult({ ...valid, confidence: 1.4 })).toThrow();
  });

  it('rejects a negative confidence', () => {
    expect(() => parseTriageResult({ ...valid, confidence: -0.1 })).toThrow();
  });

  it('rejects a missing required field', () => {
    const { rationale, ...missing } = valid;
    expect(() => parseTriageResult(missing)).toThrow();
  });

  it('rejects an unknown extra field', () => {
    expect(() => parseTriageResult({ ...valid, secret_flag: true })).toThrow();
  });

  it('rejects an empty recommended_action', () => {
    expect(() => parseTriageResult({ ...valid, recommended_action: '' })).toThrow();
  });

  it('rejects escalated_to_human contradicting final_state', () => {
    expect(() =>
      parseTriageResult({ ...valid, escalated_to_human: true, final_state: 'AUTO_RESOLVED' }),
    ).toThrow();
  });

  it('rejects a non-terminal final_state', () => {
    expect(() => parseTriageResult({ ...valid, final_state: 'CLASSIFIED' })).toThrow();
  });

  it('accepts a consistent escalated result', () => {
    expect(() =>
      parseTriageResult({ ...valid, escalated_to_human: true, final_state: 'ESCALATED' }),
    ).not.toThrow();
  });

  it('rejects an unknown guard code', () => {
    expect(() => parseTriageResult({ ...valid, guards_triggered: ['NOT_A_GUARD'] })).toThrow();
  });
});
