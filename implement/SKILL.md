---
name: implement
description: Take a task or spec end to end: implement (with simplify and spec review), review-loop in headless Codex, a PR with CI, spec retirement, then auto-merge with `--send` or wait for you to merge.
argument-hint: "[--send] <task text or spec path>"
disable-model-invocation: true
---

# Implement

Arguments: $ARGUMENTS

Mode: `--send` in the arguments means **send**; without it, **stop**. The
rest is the goal: inline text, or a path to a spec.

You own the work from the goal to its handoff.

## Before you start

- Confirm with the user the base (the commit before the change), the merge
  target branch, and the Codex review model and reasoning effort.
- Invoking this skill authorizes branching, committing, pushing, and opening
  a PR against the merge target for this task; send mode also authorizes
  merging. Branch first if you are on the merge target. If you work in a
  worktree, use it throughout.
- After this point, run to the end without asking.

## Phase 1: Implement

This phase is yours. Complete the user's task in full on your own judgment,
then commit this task's files.

## Phase 2: Simplify and spec review

1. **Simplify:** dispatch a subagent with this prompt and wait for its report:

       /simplify Base: <sha>. Scope: <paths or change>. Intent: <goal or spec path>. Apply the fixes, commit them on the current branch as one commit, and report what changed, including any behavior change.
2. **Spec review:** invoke the `spec-review` skill to check every requirement
   is implemented. The goal is the spec; when the user gave inline text, that
   text is the spec. Scale the number of independent subagents with the
   change size, splitting the requirements among them. Fix what they find
   before moving on.

## Phase 3: Review

1. **review-loop:** run headless Codex in the background and wait for its
   completion notice, never in the foreground:

       codex exec -C <dir> -m <model> -c model_reasoning_effort=<effort> "\$review-loop Base: <sha>. Scope: <paths or change>. Intent: <goal or spec path>. Merge target: <branch>. Proceed without asking."

   `<dir>` is the absolute path of the checkout you are working in. Claude
   Code and Codex manage worktrees separately, so pass the path explicitly
   and Codex works in your checkout rather than one of its own.
   `-m` alone picks the reviewers' model: review-loop's reviewer subagents
   inherit it. `review_model` applies only to Codex's built-in `/review`.
   Set a timer in the main conversation to check on it periodically. If it
   hangs, kill it; that counts as FAILED.
   Read its report and the resulting diff.
2. **Judge by the first line of review-loop's report:**
   - `APPROVED`: go to Phase 4.
   - `BLOCKED`: stop at Phase 3 and report why. A PR opened earlier stays
     draft.
   - FAILED (Codex errors, hangs, or its report opens with neither): rerun on the current
     code, up to 2 retries. Still failing: stop at Phase 3 and report why.

## Phase 4: PR and CI

1. **Open the PR:** rebase onto the latest merge target, commit only this
   task's files, and push. Open a **draft PR** the first time through this
   phase; later passes push to the same PR.
2. **Run CI:**
   - The repo has remote CI: wait for it on the PR.
   - No remote CI: run the front-end and back-end test suites locally.
3. **Read the result:**
   - Pass: mark the PR ready for review and go to Phase 5.
   - Fail, and the fix touches no logic (config, test data, environment):
     fix it and rerun CI, staying in Phase 4.
   - Fail, and the fix changes logic: fix it and go back to Phase 3.
   - Fail, and it cannot be fixed: stop, keep the PR draft, and report why.

## Phase 5: Retire the spec

Skip this phase when the goal was inline text.

1. Check the spec for business context or decisions that the repo's docs
   don't already hold. Add any you find to the docs where they belong; if
   there are none, move on.
2. Delete the spec, commit, and push to the PR. If the spec lives outside
   the repo, leave it and note it in the report.

## Phase 6: Merge or not

- **send:** merge once the merge gate passes. If it cannot pass, leave the
  PR open and report why, as in stop mode.
- **stop:** leave the PR open for the user to merge.

## Boundaries

- **Loop limit:** Phase 4 can send the work back to Phase 3 at most 3 times.
  If a fourth is needed, stop, keep the PR draft, and report why.
- **Merge gate (send):** CI is green, the branch is up to date with the merge
  target and mergeable, and no human review requests changes. Merge with the
  repo's usual method; never bypass branch protection.
- **Stop mode never merges**, enables auto-merge, or pushes to the merge
  target.

## Report

Mode (and why, if send mode did not merge), the phase it stopped at, PR link,
spec review result, review verdict and rounds, CI result, spec retirement
(docs updated, or nothing to add), merge commit if merged, and follow-ups.
