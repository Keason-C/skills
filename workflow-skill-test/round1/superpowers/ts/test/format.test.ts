import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

import { run } from '../src/cli.js';
import { formatHuman, formatJson } from '../src/format.js';
import { parseTriageResult } from '../src/schema.js';

const validPath = fileURLToPath(new URL('./fixtures/valid-result.json', import.meta.url));
const invalidPath = fileURLToPath(new URL('./fixtures/invalid-result.json', import.meta.url));
const valid = parseTriageResult(JSON.parse(readFileSync(validPath, 'utf8')));

describe('formatting', () => {
  it('shows the category in human output', () => {
    expect(formatHuman(valid)).toContain(valid.category);
  });

  it('shows the priority in human output', () => {
    expect(formatHuman(valid)).toContain(valid.priority);
  });

  it('shows the recommended action in human output', () => {
    expect(formatHuman(valid)).toContain(valid.recommended_action);
  });

  it('marks escalated tickets loudly', () => {
    const escalated = { ...valid, escalated_to_human: true, final_state: 'ESCALATED' as const };
    expect(formatHuman(escalated)).toContain('ESCALATED TO HUMAN');
  });

  it('does not shout escalation on an auto-resolved ticket', () => {
    expect(formatHuman(valid)).not.toContain('ESCALATED TO HUMAN');
  });

  it('marks detected injection loudly', () => {
    expect(formatHuman({ ...valid, injection_detected: true })).toContain(
      'PROMPT INJECTION DETECTED',
    );
  });

  it('lists the guards that fired', () => {
    expect(formatHuman(valid)).toContain('REFUND_POLICY_OVERRIDE');
  });

  it('emits canonical json', () => {
    expect(JSON.parse(formatJson(valid)).ticket_id).toBe(valid.ticket_id);
  });
});

describe('cli', () => {
  it('exits 0 for a valid file', () => {
    expect(run([validPath]).exitCode).toBe(0);
  });

  it('prints a human-readable report for a valid file', () => {
    expect(run([validPath]).stdout).toContain('TriageBot');
  });

  it('emits parseable json with --json', () => {
    const result = run([validPath, '--json']);
    expect(result.exitCode).toBe(0);
    expect(() => JSON.parse(result.stdout)).not.toThrow();
  });

  it('exits 1 for an invalid file', () => {
    expect(run([invalidPath]).exitCode).toBe(1);
  });

  it('prints the zod error path for an invalid file', () => {
    expect(run([invalidPath]).stdout).toContain('category');
  });

  it('exits 1 when no file argument is given', () => {
    expect(run([]).exitCode).toBe(1);
  });

  it('exits 1 when the file does not exist', () => {
    expect(run(['./definitely-not-here.json']).exitCode).toBe(1);
  });

  it('exits 1 when the file is not valid json', () => {
    const notJson = fileURLToPath(new URL('../package.json', import.meta.url)).replace(
      'package.json',
      'tsconfig.json',
    );
    // tsconfig.json contains comments-free JSON, so use a file that is valid
    // JSON but the wrong shape — it must fail validation, not crash.
    expect(run([notJson]).exitCode).toBe(1);
  });
});
