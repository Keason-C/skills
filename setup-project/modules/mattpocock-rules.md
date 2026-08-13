# mattpocock-skills

Every file this skill set generates goes under `.skills-doc/`, never the repo root; keep the project CLAUDE.md pointing at the real paths.

## Issues

Don't pick up an issue on your own initiative in a session that is already doing something else.

## to-spec

- **Default triage label is `ready-for-human`**, overriding the `ready-for-agent` the skill's own instructions apply.
- Once the spec is published, ask the user whether it will be broken into tickets. Don't run to-tickets on your own initiative — the split is the user's call.
  - Answer is **yes** → leave the spec at the default `ready-for-human`; the tickets carry their own labels.
  - Answer is **no** → the spec itself is the work item; relabel it `ready-for-agent`.

## grilling

Put questions to the user through Claude Code's built-in question tool (`AskUserQuestion`) — don't ask in plain chat text. The tool accepts at most 4 questions per call, so a wider round goes out as consecutive calls — batch it, don't trim it.

## TDD dual-subagent (addendum to the tdd skill)

**Purpose**: prevent one agent from writing both the tests and the implementation — when an agent writes tests and then fixes its own code, the tests overfit to the implementation and lose their power as a constraint.

**Trigger**: whenever TDD triggers, including indirectly via implement or other skills.

**Roles**: two Opus subagents execute; the main session orchestrates:

- Tester owns test files, Implementer owns implementation code; neither may modify files in the other's scope. Either side reports BLOCKED for the main session to adjudicate when it believes something in the other's scope is wrong (a bad test, an implementation that can't satisfy the tests, etc.).
- Both agents load the tdd skill on dispatch and may read the codebase, but neither sees the other's diff. They hand over via documents under `.skills-doc/tdd-pair/<feature>/` (must be git-ignored; add if missing); each returns only a short status (DONE / BLOCKED / NEEDS_CONTEXT) plus a test summary.
- The main session accepts each slice: against the slice's baseline, verify each agent touched only its own files (untracked included), re-run RED and GREEN, review both diffs against the tdd skill's anti-patterns; commit each accepted slice before starting the next.

**Lifecycle**: reuse the same subagent pair across slices, ping-pong style; swap in a fresh Tester once its tests show coupling to the implementation. Delete the handover folder once code-review is clean.

**Final review**: via mattpocock-skills:code-review (see the code-review section below for the model-tier rule).

## implement

When an issue is done, leave a comment on it stating exactly which commits implemented it (list the commit hashes).

## code-review

Whenever mattpocock-skills:code-review runs, its reviewers run at the main session's model tier — whether the main session reviews itself or dispatches subagents — and the main session adjudicates the findings.

## teach-skills

Every file the teach skills generate goes under `.skills-doc/teach/` — nowhere else — and that folder must be git-ignored (add if missing).
