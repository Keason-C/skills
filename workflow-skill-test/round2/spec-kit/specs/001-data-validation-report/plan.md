# Implementation Plan: Data Quality Validation & Interactive Report

**Branch**: `001-data-validation-report` | **Date**: 2026-07-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-data-validation-report/spec.md`

## Summary

Add a `sqlite-utils validate` command and matching library API that checks a table against a
user-supplied JSON Schema and reports violations three ways: a terminal summary, a machine-readable
JSON document for pipelines, and a self-contained interactive HTML report for non-technical readers.

Technical approach, in one line each:

- **Zero new runtime dependencies.** The supported JSON Schema subset is implemented in-tree,
  because `jsonschema` would drag a compiled Rust extension (`rpds-py`) into a project whose
  dependencies are currently all pure-Python wheels. See research D1 — this is the decision with the
  widest blast radius.
- **Library-first.** All logic in a new `sqlite_utils/validate.py`; `cli.py` gets a thin wrapper.
  This is forced, not stylistic: `mypy.ini` excludes `cli.py` from type checking, so logic placed
  there would silently fail the Tech Lead's mypy requirement.
- **Real frontend pipeline.** TypeScript compiled by Vite into a single IIFE bundle, tested with
  Vitest in jsdom. Python inlines the pre-built bundle into an HTML template via placeholder
  substitution and never concatenates markup.

## Technical Context

**Language/Version**: Python ≥3.10 (repo floor, per `pyproject.toml`); TypeScript for the report UI

**Primary Dependencies**: **None added at runtime.** Build-time only: `vite`, `vitest`,
`typescript`, `jsdom`, `@types/node`

**Storage**: SQLite (read-only access; validation never writes)

**Testing**: `pytest` for Python (existing suite + new modules); `vitest` + `jsdom` for TypeScript

**Target Platform**: Any platform running Python ≥3.10; report renders in current mainstream browsers

**Project Type**: CLI tool + Python library, with a small embedded frontend artifact

**Performance Goals**: Streaming scan with O(1) memory in table size; bounded output regardless of
violation count; millions of rows viable (SC-006)

**Constraints**: Report must be a single file, fully functional offline, with no external references
of any kind (FR-014). No Node.js required to install or run the published package.

**Scale/Scope**: One new Python module (~500 lines), one CLI command, a small TypeScript app
(~400 lines), plus tests and docs. Existing suite baseline to preserve: **1371 passed, 19 skipped**.

## Constitution Check

*GATE: evaluated before Phase 0, re-evaluated after Phase 1 design.*

| # | Principle | Pre-Phase-0 | Post-Phase-1 | Evidence |
|---|---|---|---|---|
| I | Library-First, Then CLI | PASS | **PASS** | All logic in `validate.py`; CLI parses/formats/exits only. Contract in `contracts/python-api.md`. Reinforced by the `mypy.ini` finding. |
| II | Existing Conventions Are Law | PASS | **PASS** | Reuses existing `NoTable` rather than a new exception; `Table.pks` for row identity; `@cli.command()` + `click.Path(exists=True)` matching `analyze-tables`; docs in `docs/cli.rst` with a `.. _cli_validate:` label; `cog` regenerated not hand-edited. |
| III | Test Coverage Non-Negotiable | PASS | **PASS** | Baseline 1371/19 recorded and re-run as a gate. New tests cover all eight acceptance areas the ticket lists plus the FR-002b rejection path. Vitest covers report logic in jsdom. All offline. |
| IV | Typed Python, Built Frontend | PASS | **PASS** | New module fully annotated, under mypy with no new ignores. TypeScript + Vite + `tsc --noEmit`. No HTML/JS string-building in Python — substitution only (research D3). |
| V | Dependency Restraint | PASS | **PASS** | **Zero** new runtime dependencies, evidence-backed in research D1. Frontend tooling is devDependency-only and the built artifact is committed. Report is verified self-contained by an automated test. |

**Gate result: PASS.** No violations. The Complexity Tracking table is therefore omitted, per the
template's instruction to fill it only when there are violations to justify.

One item flagged for `/speckit-analyze` to verify rather than assume: **FR-002b** (loud rejection of
unsupported keywords) is the requirement most likely to be quietly dropped during implementation,
because ignoring unknown keywords is less work than rejecting them — and is what the JSON Schema
specification itself prescribes. It must have explicit task and test coverage.

## Project Structure

### Documentation (this feature)

```text
specs/001-data-validation-report/
├── spec.md                    # Phase: specify (+ clarify integration)
├── clarification-session.md   # Phase: clarify — coverage scan, Q&A, overrides
├── checklists/
│   └── requirements.md        # Spec quality checklist, 13/13
├── plan.md                    # This file
├── research.md                # Phase 0 — decision record D1..D10
├── data-model.md              # Phase 1
├── contracts/
│   ├── cli-contract.md        # Phase 1 — command surface, exit codes
│   ├── json-output.md         # Phase 1 — archival JSON shape
│   └── python-api.md          # Phase 1 — library surface
├── quickstart.md              # Phase 1 — runnable acceptance walkthrough
└── tasks.md                   # Phase: tasks (NOT created here)
```

### Source Code (repository root)

```text
sqlite_utils/
├── validate.py                # NEW — all validation logic, fully typed
├── cli.py                     # MODIFIED — one thin `validate` command
└── static/                    # NEW — committed build output, shipped as package data
    ├── report.template.html
    ├── report.js              # built by Vite (IIFE)
    └── report.css             # built by Vite

frontend/                      # NEW — build-time only, not shipped to PyPI
├── package.json
├── tsconfig.json
├── vite.config.ts
├── src/
│   ├── types.ts               # mirrors contracts/json-output.md
│   ├── filters.ts             # pure filter/search/sort — the testable core
│   ├── render.ts              # data in, DOM out
│   ├── main.ts                # entry: read embedded JSON, mount
│   └── styles.css
└── test/
    ├── filters.test.ts
    └── render.test.ts         # jsdom

tests/
├── test_validate.py           # NEW — library-level
└── test_cli_validate.py       # NEW — CLI, exit codes, HTML self-containment

docs/
├── cli.rst                    # MODIFIED — required by test_docs.py
├── cli-reference.rst          # MODIFIED — regenerated via cog
└── python-api.rst             # MODIFIED — library API section

pyproject.toml                 # MODIFIED — package-data only; no new runtime deps
```

**Structure Decision**: Single-project layout, matching the repository as it stands. The `frontend/`
directory is a build-time sibling, deliberately outside the Python package so it is never published;
only its *output* lands in `sqlite_utils/static/` and is declared as package data. This is what lets
a PyPI install work with no Node.js present, satisfying the constitution's build-artifact rule.

## Phase Outputs

- **Phase 0** → [research.md](./research.md) — decisions D1–D10, all `NEEDS CLARIFICATION` resolved.
- **Phase 1** → [data-model.md](./data-model.md), [contracts/](./contracts/),
  [quickstart.md](./quickstart.md).

Next: `/speckit-tasks`.
