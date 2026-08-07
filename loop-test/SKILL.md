---
name: loop-test
description: The user's acceptance loop — iterate test → find bugs → fix → re-test until one full pass finds zero bugs. ONLY use when the user explicitly invokes this skill or names it. Do NOT load automatically based on task type, topic, or routing — explicit user invocation is required.
---

# Loop Test — opt-in

This skill defines the acceptance loop below; it applies only when the user has explicitly invoked this skill.

<loop-test>
Purpose: verify work by looping test → fix until a full clean pass, instead of a single test run.

Loop protocol:
1. Run the full relevant test scope (unit/integration tests covering the changed behavior). If no automated tests exist, first write a minimal test harness for the changed behavior, then proceed.
2. If any test fails or a bug is discovered, diagnose the root cause and fix the code, then go back to step 1.
3. Exit only when one complete iteration passes with zero failures and zero newly discovered bugs.

Rules:
- Fix the code, not the tests: never weaken, skip, or delete a test to make it pass. Change a test only when the test itself is provably wrong, and state that explicitly.
- After every fix, re-run the full scope — a fix can break something else; never conclude from the previously failing test alone.
- Stall guard: if the same failure persists after 3 fix attempts, or the loop reaches 10 total iterations, stop and report the blocker to the user instead of looping further.
- Optional adversarial testing: based on task difficulty, spawn subagents to attack the work (edge cases, hostile inputs, attempts to break it); any bug they find enters the same fix loop. Skip for simple tasks.
- Report briefly per iteration (what failed, root cause, what was changed) and at the end (iterations run, bugs fixed, final status).
- Composes with /fable-lead: when both are active, fixing follows fable-lead's difficulty routing; the loop itself is led by the lead model.
</loop-test>
