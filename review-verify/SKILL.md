---
name: review-verify
description: Two-axis code review of one issue's diff or a whole spec, every finding verified against the code, ending in a fix recommendation. Use only when explicitly requested.
---

# Review, then verify

Scope the diff, run the two-axis review, verify every finding, recommend. Recommendation only — fixes wait for the user's pick.

## 1. Scope

- **`issue <NN>`** — the ticket is the spec; the diff is that ticket's work, committed or not. Fixed point: the commit before the ticket's first commit, or `HEAD` when nothing is committed yet.
- **`spec`** — the feature's spec is the spec; the diff is the whole branch. Fixed point: the merge-base with the main branch.

`--since <ref>` overrides the fixed point. Use `git diff <fixed-point>` to include staged and unstaged tracked changes, and inspect relevant untracked files separately (`git ls-files --others --exclude-standard`); a tracked diff alone can be empty for new work. Restrict issue mode to the ticket's files and hunks using its work report or recorded baseline. If unrelated work cannot be separated, ask for the intended scope. Confirm the ref resolves and the combined review scope is non-empty.

## 2. Review

Resolve `code-review` from the current skill catalog and read its `SKILL.md`. Apply its two-axis review with this skill's fixed point, explicit spec, scoped diff command, and untracked files overriding its default scope and spec discovery. A supplied local ticket or spec needs no issue-tracker setup. Pass that exact scope to both reviewers so neither falls back to a committed-only comparison. Use the available subagent tools and their current schemas; inherit the session model unless the user specifies another supported model. Hold both reports verbatim as the input to the next step. If subagents are unavailable, review the axes separately and disclose that they were not independent.

## 3. Verify

Each finding is a **claim**. Rule on it from the code, never from the reviewer's quote: read the hunk in context, read the cited rule or spec line yourself, check for a recorded decision that already settles it. One verdict per finding:

- **confirmed** — the code shows the defect and the rule applies. Cite `file:line`.
- **false positive** — the code does not show it, or the rule is misread. Say which.
- **ruled** — real, but an earlier decision already chose it. Cite it.

Done when every finding on both axes has a verdict with evidence.

## 4. Recommend

Axes kept separate: **Fix** (confirmed, worst first, each with `file:line` and the one-line fix), **Skip** (false positives and ruled, one line each with the reason), counts per axis. Stop there.
