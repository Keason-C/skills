---
name: review-loop
description: Review a change with an independent subagent using code-review-and-quality, fix the findings, and loop until APPROVE or the budget ends.
disable-model-invocation: true
---

# Review Loop

You own the change; an independent subagent reviews it. Reviews make the
change correct, not bigger.

## Before you start

- Confirm the review base (the commit the change is measured from) and the
  review scope (the paths or change under review) from the user; ask if
  either is unclear.
- Record the diff size against the base, untracked files included.
- Every reviewer gets the base, scope, and the change's intent; it sees no
  conversation history.

## Loop

1. Dispatch a fresh subagent every round. The reviewer reviews and you fix:
   it edits files only for the skill's temporary mutation checks and
   restores each one, leaves git state untouched, and starts no subagents of
   its own. Once it returns, confirm the working tree is unchanged and
   restore it if not.
   It first reads the code-review-and-quality skill
   (`~/.agents/skills/code-review-and-quality/SKILL.md` in Codex,
   `~/.claude/skills/code-review-and-quality/SKILL.md` in Claude Code),
   reviews by that standard, and replies with `VERDICT: APPROVE` or
   `CHANGES` plus its findings. Each finding carries severity, file:line,
   evidence, and a fix. It returns APPROVE whenever no Critical or Required
   finding remains.
2. Verify every finding yourself, then:
   - Critical / Required: apply the smallest fix that works.
   - Disagree: push back with evidence.
   - Optional, Nit, FYI, or out of scope: decline and list as a follow-up.
3. Run the checks, then compare the diff size with the recorded one. If
   review grew the diff, cut the extra first.
4. Go back to step 1 until a stop condition below is met.

## Boundaries

- **Rounds:** every round is a full review of the whole change as it stands
  after the previous round's fixes.
- **Budget:** 3 rounds. Extend to 5 only while an open Critical or Required
  finding involves security, permissions, auth, data loss, or concurrent state.
- **Agreement:** agree only when the evidence convinces you, never to end the
  loop.
- **Approved:** the reviewer returns APPROVE on the current change.
- **Not approved:** the budget ends, or the same finding comes back two rounds
  in a row and you rebut it with evidence both times. Stop, show both sides,
  and let the user decide. Budget end is not approval.
- **Commits:** commit your fixes on the current branch.

## Report

Open with `APPROVED` or `BLOCKED` on its own line, then rounds used, diff
size before and after, fixed / disputed / declined findings, and follow-ups.
