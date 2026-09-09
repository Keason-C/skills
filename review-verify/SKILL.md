---
name: review-verify
description: Two-axis code review of one issue's diff or a whole spec, every finding verified against the code, ending in a fix recommendation. Runs only when the user types /review-verify.
disable-model-invocation: true
argument-hint: "issue <NN> | spec [--since <ref>]"
---

# Review, then verify

Scope the diff, run the two-axis review, verify every finding, recommend. Recommendation only — fixes wait for the user's pick.

## 1. Scope

- **`issue <NN>`** — the ticket is the spec; the diff is that ticket's work, committed or not. Fixed point: the commit before the ticket's first commit, or `HEAD` when nothing is committed yet.
- **`spec`** — the feature's spec is the spec; the diff is the whole branch. Fixed point: the merge-base with the main branch.

`--since <ref>` overrides the fixed point. Diff command is `git diff <fixed-point>` — two-dot, so the working tree counts. Confirm the ref resolves and the diff is non-empty.

## 2. Review

Invoke `mattpocock-skills:code-review` with the fixed point, the spec, and the diff command above (its default drops the working tree). Hold both reports verbatim as the input to the next step.

## 3. Verify

Each finding is a **claim**. Rule on it from the code, never from the reviewer's quote: read the hunk in context, read the cited rule or spec line yourself, check for a recorded decision that already settles it. One verdict per finding:

- **confirmed** — the code shows the defect and the rule applies. Cite `file:line`.
- **false positive** — the code does not show it, or the rule is misread. Say which.
- **ruled** — real, but an earlier decision already chose it. Cite it.

Done when every finding on both axes has a verdict with evidence.

## 4. Recommend

Axes kept separate: **Fix** (confirmed, worst first, each with `file:line` and the one-line fix), **Skip** (false positives and ruled, one line each with the reason), counts per axis. Stop there.
