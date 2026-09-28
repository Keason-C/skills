# mattpocock-skills: project overrides

Read before running any skill named below. Where this file and the skill's own instructions disagree, this file wins.

## Shared rules

Store local supporting documents (specs, tickets, research, and teaching
material) under `.skills-doc/`, preserving each skill's subdirectory structure.
For local tickets, replace `.scratch/` with `.skills-doc/`:
`.skills-doc/<feature-slug>/issues/<NN>-<slug>.md`.
Implementation code follows the project's normal layout.
Keep project AGENTS.md pointers aligned with the actual document paths.

Triage labels identify who acts next:

- `ready-for-agent`: the next action can be performed by the agent.
- `ready-for-human`: the next action needs a user decision, missing information
  from the user, or an action only the user can perform.

Don't pick up an issue on your own initiative in a session
that is already doing something else.

## to-spec

- **Default triage label is `ready-for-human`**, overriding the `ready-for-agent` the skill's own instructions apply.
- Once the spec is published, ask the user whether it will be broken into tickets — the split is the user's call; run to-tickets only on a yes.
  - Answer is **yes** → leave the spec at the default `ready-for-human`; the tickets carry their own labels.
  - Answer is **no** → the spec itself is the work item; relabel it `ready-for-agent`.

## to-tickets

- Every ticket carries a `**Type:**` line right below `**Status:**`. Known types: `task`, `research`, `grilling`, `prototype` — coin a new type when a ticket fits none of these.
- Every ticket carries an `**Effort Level:**` line below `**Type:**`: choose `medium`, `high`, `xhigh`, or `max` and show it in the proposed ticket list.
- Every ticket carries an `**Owner:**` line below `**Effort Level:**`: `gpt` for backend-heavy work, `claude` for UI-heavy work; show it in the proposed ticket list. The owner builds the whole vertical slice, so the ticket stays verifiable on its own.

## grilling

Use the current question tool within its availability and batch limits. If no suitable tool is available, ask a concise question in chat. Resolve the current batch before opening another; preserve the questions that remain.

## implement

Apply YAGNI and minimum sufficient validation in place of implement's default full-suite testing requirement; finish when the requirements are met and the affected paths have been verified.
