# Phase 1 — Data Model

**Feature**: 001-data-validation-report | **Date**: 2026-07-31

Types live in `sqlite_utils/validate.py`. All are fully annotated (Constitution Principle IV).

---

## `ViolationKind` — the classification vocabulary

A `str`-valued enum so it serialises to readable JSON and can drive a report filter directly.

| Value | Meaning | Level |
|---|---|---|
| `missing-column` | Schema requires a column the table does not have | table |
| `unexpected-column` | Table has a column the schema disallows via `additionalProperties: false` | table |
| `type-invalid` | Value's type is wrong and cannot be interpreted as the declared type | row |
| `type-coercible` | Value is text that *could* be read as the declared type (strict mode only) | row |
| `enum` | Value not among `enum` | row |
| `const` | Value not equal to `const` | row |
| `out-of-range` | Fails `minimum` / `maximum` / `exclusiveMinimum` / `exclusiveMaximum` | row |
| `multiple-of` | Fails `multipleOf` | row |
| `length` | Fails `minLength` / `maxLength` | row |
| `pattern` | Fails `pattern` | row |
| `format` | Fails `format` | row |

`type-invalid` and `type-coercible` being separate values is the direct implementation of Iris's
Q1 answer — the report's "kind" filter is what makes a strict run triageable.

Table-level kinds carry `row_id = None`; this is how "reported once per run, not once per row"
(FR-003) is represented.

---

## `Violation` — one failed expectation

Frozen dataclass.

| Field | Type | Notes |
|---|---|---|
| `kind` | `ViolationKind` | drives filtering |
| `column` | `str` | column concerned |
| `message` | `str` | human-readable, self-contained |
| `row_id` | `str \| None` | `None` for table-level violations |
| `value` | `object` | the offending value, as stored |
| `expected` | `str \| None` | rendering of the constraint that failed |

`row_id` is a `str` rather than an int because composite primary keys must be representable
(rendered as comma-joined parts). Frozen because a violation is a fact about a run, never edited.

`to_dict()` returns a JSON-safe mapping; `value` passes through a coercion step so `bytes` becomes a
placeholder string rather than crashing the serialiser.

---

## `ValidationSummary` — aggregate counts

| Field | Type | Notes |
|---|---|---|
| `table` | `str` | |
| `rows_checked` | `int` | rows actually examined |
| `rows_with_violations` | `int` | distinct failing rows |
| `total_violations` | `int` | **true** total, never the truncated count (FR-024) |
| `violations_by_kind` | `dict[str, int]` | true totals per kind |
| `violations_by_column` | `dict[str, int]` | true totals per column |
| `truncated` | `bool` | detail list was capped |
| `scan_limited` | `bool` | row scan was capped |
| `max_violations` | `int` | cap in force |
| `scan_limit` | `int \| None` | row cap in force |

`truncated` and `scan_limited` are deliberately **two separate booleans**. FR-025b forbids merging
them — "we only looked at 1,000 rows" and "we only listed 1,000 problems" are different statements
and a reader must be able to tell which happened.

---

## `ValidationResult` — the whole verdict

| Field | Type | Notes |
|---|---|---|
| `summary` | `ValidationSummary` | |
| `violations` | `list[Violation]` | truncated to `max_violations` |

- `ok` → `bool` property: `total_violations == 0`. This is the single source of truth for the exit
  code, so CLI and library can never disagree about pass/fail.
- `to_dict()` → the JSON contract in `contracts/json-output.md`.

Note the invariant: `len(violations) <= summary.total_violations`. Equality holds exactly when
`truncated` is false. Worth asserting in tests.

---

## `SchemaError` — refusing to run

Raised for: unparsable JSON, schema that is not an object, unsupported keyword, malformed keyword
value (e.g. `minLength: "x"`), unknown `type` name.

Carries a message naming the offending keyword and its location (e.g. `properties.age.exclusiveMin`).

This exception is what makes FR-002b real. It is raised during schema *compilation*, before any row
is read, so a bad schema can never produce a partial or misleading verdict. The CLI maps it to exit
status 2 — never 1 — so a pipeline cannot mistake a broken schema for dirty data.

`sqlite_utils/db.py` already defines module-level exceptions in this style
(`AlterError`, `NoTable`, `BadPrimaryKey`, …), so this follows an existing convention rather than
introducing one.

---

## `CompiledSchema` — validated schema, ready to apply

Produced by `compile_schema(raw: object) -> CompiledSchema`. Holds the per-column constraint set,
the `required` names, and the `additionalProperties` policy.

Separating compilation from application matters for three reasons:
1. FR-002b — unsupported keywords are rejected once, up front, not rediscovered per row.
2. Performance — regexes are compiled once, not per row, across millions of rows.
3. Testability — schema rejection is testable without any database at all.

---

## Entity relationships

```
CompiledSchema ──applied to──> Table rows ──produces──> ValidationResult
                                                          ├── ValidationSummary (counts, true totals)
                                                          └── list[Violation]  (bounded by max_violations)
```

`ValidationResult` is the sole input to both renderers — the JSON writer and the HTML report
builder. Neither renderer re-reads the database, which is what guarantees the two outputs can never
disagree (FR-011 vs FR-013).
