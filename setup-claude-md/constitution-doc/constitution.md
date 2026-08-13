<!-- TEMPLATE — when filling in: replace every {{...}} with real content and delete all <!-- --> comments, this line included. -->

# Mission

## Background

<!-- Where it hurts today: what is forced to be shared / duplicated / drifting, and at what cost. One paragraph of prose, no bullets. -->
{{BACKGROUND}}

## Target Audience

<!-- Who uses this. List human users and agents separately; for each, say what the delivered thing solves for them. -->

- **{{AUDIENCE_1}}** — {{AUDIENCE_1_DESC}}
- **{{AUDIENCE_2}}** — {{AUDIENCE_2_DESC}}

## Solution

<!-- What the deliverable is and how it works. One paragraph of prose covering the main chain, no implementation detail. -->
{{SOLUTION}}

## Goal

<!-- What the world looks like once this succeeds — verifiable statements. About 3 items. -->

- {{GOAL_1}}
- {{GOAL_2}}
- {{GOAL_3}}

# Roadmap

<roadmap-conventions>

- Each Phase is a **shippable version**, not a task tracker. A Phase carries a **Decision** (the ruling on how far this round goes before it ships) and **Acceptance Criteria** (verifiable acceptance conditions).
- Two levels only: directly under a Phase are **stages**, numbered `Stage-1` / `Stage-2` / `Stage-3`, one `###` subheading per stage, and **one stage maps to one spec** (living under `{{SPEC_DIR}}`, following the issue flow). Stages are never split further; task-level progress belongs to issues, not this file.
- A stage's body is a single `Description:` field line — one sentence on what the stage delivers, no implementation detail.
- Both Phases and stages carry a `Status:` line with values `planned` / `in-progress` / `awaiting-acceptance` / `closed`. **Closing (`closed`) requires user confirmation** — an agent may only advance a status to `awaiting-acceptance` and request acceptance, never close on its own.
- No more than three Phases on the books at once; add a new Phase only after an old one closes.

</roadmap-conventions>

<!-- Repeat the Phase block below as needed, three Phases at most. Stage count is flexible; 2–4 works well. -->

## Phase {{N}} — {{PHASE_NAME}}

Status: `{{planned|in-progress|awaiting-acceptance|closed}}`

### Decision

<!-- How far this round goes before it ships: scope boundary + what is explicitly out + the shipping criterion. One or two sentences. -->
{{PHASE_DECISION}}

### Acceptance Criteria

<!-- Executable, observable acceptance actions and outcomes — not adjectives. -->
{{PHASE_ACCEPTANCE}}

### Stage-1: {{STAGE_NAME}}

Status: `{{STATUS}}`

Description: {{STAGE_DESC}}

### Stage-2: {{STAGE_NAME}}

Status: `{{STATUS}}`

Description: {{STAGE_DESC}}

### Stage-3: {{STAGE_NAME}}

Status: `{{STATUS}}`

Description: {{STAGE_DESC}}

<!-- Ideas not yet on the books go on the single line below; delete the line if there are none. -->

Candidates (not on the books; revisit after a Phase closes): {{CANDIDATE}}
