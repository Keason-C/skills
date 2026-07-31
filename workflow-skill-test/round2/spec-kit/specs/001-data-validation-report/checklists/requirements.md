# Specification Quality Checklist: Data Quality Validation & Interactive Report

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-07-31
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Validation Iterations

### Iteration 1 — findings and fixes

Three items failed on the first pass and were corrected before this checklist was finalised:

1. **"No implementation details" — initially FAILED.** The first draft of FR-011 said "emit JSON to
   stdout" and FR-013 said "write an HTML file". Both name output formats and a stream. *Judgement
   call:* "JSON Schema", "JSON output" and "a file that opens in a browser" are **not** leaked
   implementation details here — they are verbatim business constraints from the requester ("约束
   描述用 JSON Schema 就行", "HTML,发给运营点开就能看"). Naming them is reporting the requirement,
   not choosing a design. What *was* leaked, and has been removed, is `stdout`, file extensions, CLI
   flag names, and the word "command-line" in requirement bodies. FR-013 now reads "a single file
   that opens directly in a browser".
2. **"Success criteria are technology-agnostic" — initially FAILED.** Draft SC-004 read "the HTML
   report loads in under 2 seconds for 10,000 violations". That is a technical performance budget
   dressed as a user outcome, and it is also unverifiable without fixing a machine spec. Rewritten
   as a user-capability statement about narrowing violations with filter/search/sort.
3. **"Edge cases are identified" — initially PARTIAL.** The draft omitted the case of a schema
   naming a column the table does not have. This is the most likely real-world mistake (a typo in
   the schema) and, handled naively, it silently passes every row — the worst possible failure mode
   for a validation tool. Added as FR-003 and as an edge case.

### Iteration 2 — remaining item

- **"No [NEEDS CLARIFICATION] markers remain" — FAILS, deliberately and by design.**

  Three markers remain (Q1 type coercion, Q2 keyword coverage and extra columns, Q3 NULL
  semantics). Each is a **product decision about the requester's business**, and the ticket is
  explicit on this point: *"哪些细节我没想清楚的,来问我,别自己猜我的业务"* and *"业务/产品决策问
  Iris"*.

  Guessing these to make a checkbox go green would directly violate the instruction that created
  the feature. Q1 in particular is not a detail: CSV-loaded SQLite tables store nearly everything
  as TEXT, so a strict reading of JSON Schema `type: integer` would flag *every row of every
  CSV-derived table*. Getting that wrong makes the entire feature useless while appearing to work.

  These markers are resolved in the `/speckit-clarify` phase, which exists for exactly this
  purpose. **The spec is not ready for `/speckit-plan` until then.**

### Iteration 3 — re-validation after `/speckit-clarify` (2026-07-31)

All five questions were answered by the requester. Re-ran every checkbox against the updated spec.

**Pass count: 12/13 → 13/13.**

State changes:

- **Newly passing**: "No [NEEDS CLARIFICATION] markers remain" — all three markers resolved by
  answers, verified by grep returning zero matches.
- **Regressions**: none.

Two answers *contradicted* the spec as written and required correcting rather than appending. Both
were fixed, and the obsolete text replaced rather than left alongside the new text:

1. **Q1 answered C (strict default), not the recommended D (lenient default).** The requester's
   reasoning overrides mine and is better than mine: surfacing "this CSV arrived completely untyped"
   is the *point* of the tool, and a 100% violation rate on day one is a true report about the data,
   not a broken tool. My recommendation optimised for the tool looking good on first run; hers
   optimises for the tool telling the truth. She also solved the objection I raised — splitting type
   failures into *coercible* vs *invalid* keeps a strict run triageable instead of a uniform wall.
   That distinction is now FR-008b and drives a filter in the report.
2. **Q4 answered B (NULL = JSON null), not the recommended A (NULL = absent).** This inverted
   User Story 1's acceptance scenario 3, which asserted that a NULL in a required column is a
   *required* violation. Under B it is a *type* violation, and `required` is never triggered by NULL
   at all. The scenario was rewritten, not supplemented. `required` now only fires for a column
   missing from the table entirely — which in turn forced FR-003 to be restated as a *table-level*
   violation emitted once, rather than one per row.

New requirements introduced by the answers: FR-002a/FR-002b (keyword coverage and loud rejection of
unsupported keywords), FR-008a–FR-008f (value semantics), FR-022a–FR-022c (value exposure limits),
FR-025a/FR-025b (independent row-scan cap). New criteria SC-009, SC-010, SC-011.

## Notes

- Status: **13 of 13 items pass. Spec is ready for `/speckit-plan`.**
- FR-002b is the requirement most likely to be quietly dropped during implementation, because
  rejecting unknown keywords is more work than ignoring them. It is a hard acceptance condition:
  "绝不允许装作校验过了". Flagged for `/speckit-analyze` to verify a task covers it.
- Two of my five recommendations were overridden by the requester. Worth noting that both overrides
  improved the design — the questions were worth asking precisely because my defaults were wrong.
