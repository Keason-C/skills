---
name: setup-project
disable-model-invocation: true
description: Set up or refresh project documentation and stack conventions in AGENTS.md and docs/, with independently selectable documents and modules.
---

# Set up project

Set up project documents and module snapshots using the user's choices. For targeted updates, inspect and present only the affected templates, modules, and project snapshots. A full setup covers the document options and selectable modules below.

Use the project's language preference, then the session's; ask if neither is known. Render `{{USER_LANGUAGE}}` in the language module accordingly. Agent-facing templates stay English.

## Workflow

1. **Inspect.** Check the relevant documents, module blocks, and selection evidence. Existing mission and tech-stack documents remain in use. Compare module snapshots with rendered templates, including language and document paths. Resolve supporting skills from the current catalog when needed.
2. **Propose.** Present missing document/module choices and differences from existing snapshots. Show the draft additions, edits, and moves. Group unchanged items in a short status note. Apply choices already made in the session; ask only about unresolved ones using the available question tool or concise chat.
3. **Apply.** Write the authorized changes under the rules below. Create selected missing documents from `templates/`; preserve existing authored content. Update module blocks in place and leave surrounding content intact. Update `AGENTS.md` directly.
4. **Check and report.** Verify each selected module has one block in its designated host, selected documents exist, and the file index covers documents in use. Report changes and moves; identify newly created templates that still need project content.

Re-run this skill to refresh snapshots. Users can remove a module by deleting its marker block.

## Documents

| Option | Path | Purpose |
| --- | --- | --- |
| `mission` | `docs/mission.md` | Project background, audience, solution, goals, scope, and acceptance criteria |
| `tech-stack` | `docs/tech-stack.md` | Technical choices, rationale, deployment, alternatives, and project conventions |

The two documents are independent choices. A document is **in use** if it exists or the user selects it for creation. Copy selected missing documents from their templates; placeholders and optional sections are starting points for project authoring. An unselected missing document stays absent. Existing document bodies are not template snapshots.

This skill uses the `docs/` layout. If active project instructions still use `constitution-doc/`, report the migration need and leave the project unchanged; migration is a separate task. Historical references alone do not block setup.

## Module snapshots

Modules are project-owned copies of `modules/<name>.md`, bounded by markers:

```markdown
<!-- module:backend-python -->
…snapshot content…
<!-- /module:backend-python -->
```

Preserve project customizations. Identical snapshots need no write. For differences, show the diff: **keep** preserves the project version; **overwrite** takes the rendered template. A targeted edit approved by the user can update only the agreed wording. Preserve other blocks and authored content.

## Selectable modules

Evidence informs recommendations; the user chooses which modules to add.

| Module | Evidence |
| --- | --- |
| `language` | Project or session language preference |
| `backend-python` | `pyproject.toml`, `setup.py`, or `environment.yml` |
| `database` | Dependencies include `sqlmodel`, `sqlalchemy`, `alembic`, `asyncpg`, `psycopg`, `aiosqlite`, `duckdb`, or `polars`; or compose defines PostgreSQL |
| `frontend-ts` | `vite` or `react` dependencies, or `tsconfig.json` |
| `agent-dev` | Backend/frontend evidence plus `pydantic-ai`, `open-interpreter`, `@anthropic-ai/*`, or `ai` dependencies |
| `vibe-coding` | User preference for technical reference guidance |
| `skill-note` | `grilling` in the current catalog or installed roots; record its resolved path |
| `file` | `.design/`, a legacy `design` block, or either document in use |

## File index

`modules/file.md` describes paths and their contents. Keep descriptions informational, without prescribing when to read each file.

The `file` block lives at the top of root `AGENTS.md`. Include it when either document is in use, with rows only for documents in use. Preserve custom rows and reuse existing routes; add missing document rows as part of the draft, even when keeping other project edits. Selecting `file` alone creates no directories or supporting documents.

## Stack modules

`backend-python`, `database`, `frontend-ts`, and `agent-dev` live in `docs/tech-stack.md` when it is in use; otherwise they live in root `AGENTS.md`. Other modules live in root `AGENTS.md`. New blocks append to their host, except `file`.

When tech-stack becomes the host, move existing stack blocks from `AGENTS.md`, preserving their content unless a refresh was selected. Remove the old markers and preceding blank line. Consolidate identical duplicates; present differing copies for resolution. Selecting mission alone does not move stack blocks.

Stack modules describe default choices, purposes, and useful conventions. Preserve existing project choices. Validation follows the project's configured checks and quality requirements, scoped to the change; report required checks that could not run. The Core table records key choices and rationale where useful.

## Legacy snapshots

- **`design` → `file`:** offer replacement. Keeping the legacy block leaves it intact and omits duplicate routes from `file`; accepting creates or refreshes one `file` block and removes `design`.
- **`mattpocock-rules` → `skill-note`:** treat the inline content, or the file referenced by an old pointer, as the snapshot. Keep preserves the old block; overwrite uses `modules/skill-note.md` and its markers, removing the retired `to-spec` rule. If the referenced file is missing, offer the current template. Retain referenced source files and name them in the result. Resolve differing old/new blocks before consolidation.
