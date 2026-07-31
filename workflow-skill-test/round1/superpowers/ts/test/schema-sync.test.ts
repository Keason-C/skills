/**
 * Proves the hand-written zod schema still matches the JSON Schema exported
 * from pydantic. This is what makes hand-writing the zod schema safe: if a
 * pydantic model changes and `scripts/export_schema.py` is re-run, these
 * assertions go red instead of the two sides quietly drifting apart.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { TriageResultObject, enumValues } from '../src/schema.js';

const jsonSchema = JSON.parse(
  readFileSync(
    fileURLToPath(new URL('../../schema/triage_result.schema.json', import.meta.url)),
    'utf8',
  ),
);

describe('zod schema stays in sync with the exported pydantic JSON Schema', () => {
  it('covers exactly the same fields', () => {
    expect(Object.keys(TriageResultObject.shape).sort()).toEqual(
      Object.keys(jsonSchema.properties).sort(),
    );
  });

  it('agrees on which fields are required', () => {
    const zodRequired = Object.entries(TriageResultObject.shape)
      .filter(([, field]) => !(field as { safeParse: (v: unknown) => { success: boolean } }).safeParse(undefined).success)
      .map(([name]) => name)
      .sort();
    expect(zodRequired).toEqual([...(jsonSchema.required as string[])].sort());
  });

  it('agrees on the Category domain', () => {
    expect(enumValues.category.slice().sort()).toEqual(
      [...(jsonSchema.$defs.Category.enum as string[])].sort(),
    );
  });

  it('agrees on the Priority domain', () => {
    expect(enumValues.priority.slice().sort()).toEqual(
      [...(jsonSchema.$defs.Priority.enum as string[])].sort(),
    );
  });

  it('agrees on the Sentiment domain', () => {
    expect(enumValues.sentiment.slice().sort()).toEqual(
      [...(jsonSchema.$defs.Sentiment.enum as string[])].sort(),
    );
  });

  it('agrees on the GuardCode domain', () => {
    expect(enumValues.guardCode.slice().sort()).toEqual(
      [...(jsonSchema.$defs.GuardCode.enum as string[])].sort(),
    );
  });

  it('agrees that extra properties are forbidden', () => {
    expect(jsonSchema.additionalProperties).toBe(false);
  });
});
