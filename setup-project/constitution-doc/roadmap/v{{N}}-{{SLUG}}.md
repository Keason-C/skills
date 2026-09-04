<!-- TEMPLATE — a fixture: it stays here blank, so the next version file always has a shape to follow. To start a version, COPY this file to `v<N>-<slug>.md` and fill in the copy: replace every {{...}} with real content, add or drop Phases as needed, and delete all <!-- --> comments, this line included. A version's Status is recorded in `../mission.md`'s version table, not here. -->

# v{{N}} — {{VERSION_NAME}}

## Charter

<!-- What capability this version delivers: scope boundary + what this version leaves out. One or two sentences. -->
{{VERSION_SCOPE}}

## Acceptance

<!-- Executable, observable actions and results — adjectives alone do not qualify. -->
{{VERSION_ACCEPTANCE}}

<!-- A Phase is one feature. Description says in one line what it delivers — no implementation detail. -->

## Phase-1: {{FEAT_NAME}}

Status: `{{planned|in-progress|awaiting-acceptance|closed}}`

Description: {{FEAT_DESC}}

Spec: {{SPEC_PATH|non-spec}}

## Phase-2: {{FEAT_NAME}}

Status: `{{planned|in-progress|awaiting-acceptance|closed}}`

Description: {{FEAT_DESC}}

Spec: {{SPEC_PATH|non-spec}}

## Phase-3: {{FEAT_NAME}}

Status: `{{planned|in-progress|awaiting-acceptance|closed}}`

Description: {{FEAT_DESC}}

Spec: {{SPEC_PATH|non-spec}}
