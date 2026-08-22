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

## implement

When an issue is done, leave a comment on it stating exactly which commits implemented it (list the commit hashes).

## teach-skills

Every file the teach skills generate goes under `.skills-doc/teach/` — nowhere else — and that folder must be git-ignored (add if missing).
