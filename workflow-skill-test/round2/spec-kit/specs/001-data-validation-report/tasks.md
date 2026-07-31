# Tasks: Data Quality Validation & Interactive Report

**Feature**: 001-data-validation-report | **Date**: 2026-07-31
**Input**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md),
[data-model.md](./data-model.md), [contracts/](./contracts/), [quickstart.md](./quickstart.md)

**Tests: REQUIRED.** The tasks skill treats test tasks as optional, but they are explicitly demanded
here by the ticket's acceptance criteria ("新功能测试覆盖:正常校验、类型违规、必填缺失、空表、表不
存在、schema 文件非法、退出码语义、HTML 自包含") and by Constitution Principle III. Test tasks are
therefore generated throughout and are not negotiable.

---

## Phase 1: Setup

- [X] T001 Record the pre-existing test baseline by running `uv run pytest -q` at the repository root and noting the pass/skip counts; this is the zero-regression reference for SC-007
- [X] T002 [P] Create the frontend toolchain manifest at `frontend/package.json` with devDependencies only (vite, vitest, typescript, jsdom, @types/node) and scripts for `build`, `test`, `typecheck`
- [X] T003 [P] Create `frontend/tsconfig.json` with strict mode enabled, DOM + ES2020 libs, `noEmit` for the typecheck script
- [X] T004 Create `frontend/vite.config.ts` configured for library mode: single IIFE output, `cssCodeSplit: false`, output directory `../sqlite_utils/static/`, and a vitest block using the jsdom environment
- [X] T005 Install the frontend toolchain with `npm --prefix frontend install` and verify `npx tsc --version` and `npx vitest --version` resolve
- [X] T006 Add `frontend/node_modules/`, `frontend/dist/` and other build noise to `.gitignore`, keeping `sqlite_utils/static/` tracked because the built artifact must ship

**Checkpoint**: toolchain installed; no product code written yet.

---

## Phase 2: Foundational (blocking prerequisites)

These block every user story. Nothing in Phase 3+ can start until they are done.

- [X] T007 Create `sqlite_utils/validate.py` with module docstring and the `ViolationKind` str-enum containing all eleven kinds from `data-model.md`
- [X] T008 Add the `Violation`, `ValidationSummary`, and `ValidationResult` frozen dataclasses to `sqlite_utils/validate.py`, each fully type-annotated, with `to_dict()` methods matching `contracts/json-output.md` exactly, carrying every field required by **FR-004** and **FR-006**
- [X] T009 Add the `SchemaError` exception to `sqlite_utils/validate.py`, following the module-level exception style already used in `sqlite_utils/db.py` (`NoTable`, `AlterError`, `BadPrimaryKey`)
- [X] T010 Implement `compile_schema()` in `sqlite_utils/validate.py`: parse the schema object with Draft 2020-12 semantics, build per-column constraint sets, pre-compile `pattern` regexes once, and capture the `additionalProperties` policy; raise `SchemaError` with an actionable message for unparsable or non-object input (**FR-001**, **FR-002**)
- [X] T011 Implement unsupported-keyword rejection inside `compile_schema()` so that any keyword outside the FR-002a supported set raises `SchemaError` naming the keyword and its location — satisfies **FR-002b**; must reject before any row is read
- [X] T012 [P] Add `tests/test_validate.py` with tests for `compile_schema()` accepting every supported keyword from FR-002a, including the union type form `["string","null"]`
- [X] T013 [P] Add tests to `tests/test_validate.py` asserting `SchemaError` is raised for `allOf`, `anyOf`, `oneOf`, `if`, `$ref`, malformed keyword values, and a non-object schema — the **FR-002b** guard flagged in plan.md

**Checkpoint**: schema compilation complete and independently tested with no database involved.

---

## Phase 3: User Story 1 — Check a table against a declared shape (P1)

**Goal**: produce a correct verdict for a table against a schema.

**Independent test**: load a table of known clean and dirty rows, validate, assert exactly the dirty
rows are reported with the correct kind for each.

- [X] T014 [US1] Implement value-level type classification in `sqlite_utils/validate.py` per research D9: storage-class comparison, the `type-coercible` vs `type-invalid` split (**FR-008a/b**), NULL as JSON null (**FR-008d**), empty string as valid string (**FR-008e**), and explicit integer-vs-boolean handling
- [X] T015 [US1] Implement the remaining constraint checks in `sqlite_utils/validate.py`: `enum`, `const`, `minimum`/`maximum`/`exclusiveMinimum`/`exclusiveMaximum`, `multipleOf`, `minLength`/`maxLength`, `pattern`, and `format` restricted to the recognised set `date`, `date-time`, `time`, `email`, `uri`, `ipv4` (**FR-002c**)
- [X] T015a [US1] Reject unrecognised `format` values in `compile_schema()` with `SchemaError`, so `{"format": "uuid"}` fails loudly rather than validating nothing (**FR-002c**, same principle as **FR-002b**)
- [X] T016 [US1] Implement `validate_table()` in `sqlite_utils/validate.py` as the public library entry point (**FR-012**) with a streaming row scan (research D6), checking every row and populating all per-violation fields (**FR-004**), using `Table.pks` for row identity with `rowid` fallback (research D5), raising the existing `NoTable` for a missing table
- [X] T017 [US1] Implement table-level checks in `validate_table()`: `missing-column` emitted once per run not once per row (**FR-003**), and `unexpected-column` governed by the schema's own `additionalProperties` (**FR-008f**)
- [X] T018 [US1] Implement summary aggregation in `validate_table()` producing every field **FR-006** requires: true totals for `total_violations`, `violations_by_kind` and `violations_by_column` that remain accurate after detail truncation (**FR-024**)
- [X] T019 [P] [US1] Add tests to `tests/test_validate.py` for the clean-table pass case and the empty-table case (**FR-007**), asserting `ok is True` and `rows_checked == 0` for the latter
- [X] T020 [P] [US1] Add tests to `tests/test_validate.py` for type violations: invalid values, coercible values under strict mode, both accepted under `lenient_types=True` (**FR-008a/b/c**)
- [X] T021 [P] [US1] Add tests to `tests/test_validate.py` for NULL semantics: NULL against a non-null type is `type-invalid`, NULL against `["string","null"]` passes, NULL never triggers a required violation, empty string passes as a string (**FR-008d/e**)
- [X] T022 [P] [US1] Add tests to `tests/test_validate.py` for the missing-column case asserting exactly one violation regardless of row count (**FR-003**), and for `additionalProperties` both unset and `false` (**FR-008f**)
- [X] T023 [P] [US1] Add tests to `tests/test_validate.py` for a single row breaking two rules producing two separate violations (**FR-005**), and for `NoTable` on a missing table (**FR-008**)
- [X] T024 [P] [US1] Add tests to `tests/test_validate.py` for each remaining constraint keyword (`enum`, `const`, range, `multipleOf`, length, `pattern`, `format`) producing its designated `ViolationKind`
- [X] T024a [P] [US1] Add tests to `tests/test_validate.py` covering each recognised `format` value passing and failing, plus `SchemaError` for an unrecognised `format` such as `uuid` (**FR-002c**)

**Checkpoint**: library API fully functional and tested. US1 delivers value standalone.

---

## Phase 4: User Story 2 — Gate an automated pipeline (P1)

**Goal**: expose the verdict through the CLI with pipeline-safe exit statuses and JSON output.

**Independent test**: run the command against clean and dirty tables in a shell, assert exit statuses
differ; parse `--json` output and assert it matches the terminal verdict.

- [X] T025 [US2] Add the `validate` command to `sqlite_utils/cli.py` per `contracts/cli-contract.md`, following existing repository conventions throughout (**FR-026**): positional `path`/`table`/`schema` arguments using `click.Path(exists=True)` matching the `analyze-tables` style, plus the `--json`, `--lenient-types`, `--max-violations`, `--scan-limit`, `--full-row` and `--load-extension` options
- [X] T026 [US2] Implement exit-status selection in the `validate` command per research D8: 0 pass, 1 violations found, 2 tool failure — ensuring `SchemaError` and `NoTable` both map to 2 and can never yield 1 (**FR-009/FR-010**)
- [X] T027 [US2] Implement the default human-readable terminal summary and the `--json` output path in `sqlite_utils/cli.py`, writing machine output to stdout and all errors to stderr (**FR-011**)
- [X] T028 [P] [US2] Add `tests/test_cli_validate.py` using `CliRunner` following the existing patterns in `tests/test_cli.py`, covering exit status 0 for a clean table and 1 for a dirty one
- [X] T029 [P] [US2] Add tests to `tests/test_cli_validate.py` asserting exit status 2 for a missing table, an unparsable schema file, and a schema using an unsupported keyword — and explicitly asserting these are **not** 1 (**FR-010**)
- [X] T030 [P] [US2] Add a test to `tests/test_cli_validate.py` parsing `--json` output with `json.loads` and asserting it conforms to `contracts/json-output.md`, including the `len(violations) <= total_violations` invariant

**Checkpoint**: feature is pipeline-usable. US1 + US2 together are a shippable MVP.

---

## Phase 5: User Story 3 — Browsable report for a non-technical reader (P2)

**Goal**: a single self-contained interactive HTML file.

**Independent test**: generate a report from a dirty table, assert it renders summary and violations,
drive filter/search/sort/expand in jsdom, and assert zero external references.

- [X] T031 [P] [US3] Create `frontend/src/types.ts` mirroring `contracts/json-output.md` exactly, so the TypeScript types and the Python output cannot drift
- [X] T032 [US3] Implement pure filter, search and sort functions in `frontend/src/filters.ts` — no DOM access, so they are directly unit-testable (**FR-016/017/018/019**)
- [X] T033 [US3] Implement the report renderer in `frontend/src/render.ts` as data-in/DOM-out, building nodes with `createElement`/`textContent` and never `innerHTML`, with an expandable detail row showing expected versus actual (**FR-020/FR-021**)
- [X] T034 [US3] Implement the summary panel in `frontend/src/render.ts`, rendered before the violation detail, stating the pass case explicitly and surfacing truncation and scan-limit as two distinct statements (**FR-015/022/024/025b**)
- [X] T035 [US3] Create `frontend/src/main.ts` to read the embedded JSON from the `application/json` script tag and mount the report, plus `frontend/src/styles.css` supporting both light and dark colour schemes
- [X] T036 [P] [US3] Add `frontend/test/filters.test.ts` covering column filter, kind filter, free-text search across row id/column/message/value, sort by each field, and sort direction reversal
- [X] T037 [P] [US3] Add `frontend/test/render.test.ts` in jsdom covering summary rendering, violation list rendering, the zero-violation pass state, row expansion, and an XSS case asserting a `<img onerror>` value renders as literal text
- [X] T038 [US3] Create the HTML template `sqlite_utils/static/report.template.html` containing the three sentinel placeholders and the `application/json` data script tag, with no external references of any kind
- [X] T039 [US3] Build the frontend with `npm --prefix frontend run build` and commit the emitted `sqlite_utils/static/report.js` and `report.css`
- [X] T040 [US3] Implement `build_html_report()` (**FR-013**) in `sqlite_utils/validate.py` using placeholder substitution only, with a JSON serialiser that escapes `<`, `>` and `&` to `\uXXXX` so a cell containing `</script>` cannot break out (research D3); performs no file I/O and embeds no filesystem path (**FR-022c**)
- [X] T041 [US3] Wire the `--html PATH` option in `sqlite_utils/cli.py` to write the report, and implement value truncation plus the `--full-row` opt-in (**FR-022a/b**)
- [X] T042 [P] [US3] Add a test to `tests/test_cli_validate.py` asserting the generated HTML contains no `http://`, `https://`, `//cdn`, `<link rel="stylesheet" href`, or `<script src=` reference — the automated form of **FR-014**
- [X] T043 [P] [US3] Add tests to `tests/test_cli_validate.py` asserting the report is still produced and states the pass for a clean table (**FR-022**), and that a `</script>` payload in a cell value is escaped in the embedded JSON
- [X] T043a [P] [US3] Add tests to `tests/test_cli_validate.py` asserting that by default only the offending column's value appears and other columns of that row do not, and that `--full-row` includes them — the privacy control from clarification Q5 (**FR-022b**)
- [X] T043b [P] [US3] Add a test to `tests/test_cli_validate.py` asserting a value longer than 200 characters is truncated and marked as truncated, while a shorter value is shown whole (**FR-022a**)

**Checkpoint**: report is shareable and verified self-contained.

---

## Phase 6: User Story 4 — Bounded output for very large tables (P3)

**Goal**: accurate totals with bounded work and bounded output.

**Independent test**: validate a table exceeding both limits; assert totals are true while detail is
capped and both facts are reported separately.

- [X] T044 [US4] Implement `max_violations` truncation in `validate_table()`: stop retaining detail at the cap while continuing to count, setting `summary.truncated` (**FR-023/024/025**)
- [X] T045 [US4] Implement `scan_limit` in `validate_table()`: stop reading rows at the cap, setting `summary.scan_limited` independently of `truncated` (**FR-025a/b**)
- [X] T046 [P] [US4] Add tests to `tests/test_validate.py` asserting that with a low `max_violations` the retained list is capped while `total_violations`, `violations_by_kind` and `violations_by_column` stay true (**FR-024**)
- [X] T047 [P] [US4] Add tests to `tests/test_validate.py` asserting `scan_limit` bounds `rows_checked`, and that `truncated` and `scan_limited` are set independently — including a case where one is true and the other false (**FR-025b**)

**Checkpoint**: all four user stories complete.

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T048 Add a `.. _cli_validate:` section to `docs/cli.rst` documenting the command with examples, making it discoverable from the existing docs (**FR-027**) — required by `tests/test_docs.py::test_commands_are_documented`, which will otherwise fail
- [X] T049 Document the Python API in `docs/python-api.rst` following the existing section conventions
- [X] T050 Regenerate `docs/cli-reference.rst` with `uv run cog -r docs/*.rst` so the new command appears in the command reference (**FR-027**) — never hand-edit, since CI runs `cog --check`
- [X] T051 Declare the static report assets as package data in `pyproject.toml` under `[tool.setuptools.package-data]` so they ship in the wheel, and confirm no runtime dependency was added
- [X] T052 Run `uv run black .` and `uv run flake8` and fix all findings
- [X] T053 Run `uv run mypy sqlite_utils tests` and fix all findings with no new ignores and no relaxation of `mypy.ini`
- [X] T054 Run `npm --prefix frontend run typecheck` and `npm --prefix frontend test`, fixing all findings
- [X] T055 Run the full `uv run pytest` suite and confirm the count matches the T001 baseline plus the new tests, with zero pre-existing tests modified or removed (**SC-007**)
- [X] T056 Execute the end-to-end walkthrough in `quickstart.md` verbatim and confirm every stated expectation, including the three exit-status cases

---

## Dependencies

```
Phase 1 Setup  ──> Phase 2 Foundational ──┬──> Phase 3 US1 (P1) ──> Phase 4 US2 (P1) ──> MVP
                                          │                    │
                                          │                    └──> Phase 5 US3 (P2)
                                          │                    └──> Phase 6 US4 (P3)
                                          └──> (T031..T037 frontend work may start early)
                                                                          │
                                                            Phase 7 Polish (all above)
```

- **US2 depends on US1** — the CLI has nothing to expose until `validate_table()` exists.
- **US3 depends on US1** for the result shape, but the *frontend* tasks (T031–T037) depend only on
  `contracts/json-output.md` and can be built in parallel with Python work. This is the largest
  parallelisation opportunity in the plan.
- **US4 depends on US1** only; it is independent of US2 and US3.
- **Phase 7** depends on everything.

## Parallel Execution Opportunities

- **Phase 1**: T002, T003 in parallel.
- **Phase 2**: T012, T013 in parallel once T010/T011 land.
- **Phase 3**: T019–T024 — six independent test tasks, all in the same file but non-overlapping.
- **Phase 4**: T028, T029, T030 in parallel.
- **Phase 5**: T031 then T036/T037 alongside T032–T035; T042/T043 in parallel afterwards.
- **Phase 6**: T046, T047 in parallel.
- **Cross-phase**: the entire frontend track (T031–T037) is parallel to the entire Python track.

## Implementation Strategy

**MVP = Phase 1 + 2 + 3 + 4** (through T030). At that point `sqlite-utils validate` works, gates
pipelines correctly, and emits archival JSON — Iris's items 1, 2 and half of 3. Shippable alone.

**Increment 2 = Phase 5**, the shareable HTML report, which is the reason the ticket exists.

**Increment 3 = Phase 6**, scale bounding — required before use on the million-row tables.

**Phase 7 is not optional polish.** T048 and T050 are needed for the *pre-existing* test suite and CI
to pass; skipping them fails SC-007. They are listed last for ordering reasons, not priority.

## Task Summary

| Phase | Tasks | Count |
|---|---|---|
| 1 — Setup | T001–T006 | 6 |
| 2 — Foundational | T007–T013 | 7 |
| 3 — US1 (P1) | T014–T024 | 11 |
| 4 — US2 (P1) | T025–T030 | 6 |
| 5 — US3 (P2) | T031–T043 | 13 |
| 6 — US4 (P3) | T044–T047 | 4 |
| 7 — Polish | T048–T056 | 9 |
| **Total** | | **56** |
