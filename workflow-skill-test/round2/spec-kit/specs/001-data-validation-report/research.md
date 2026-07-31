# Phase 0 — Research & Decision Record

**Feature**: 001-data-validation-report | **Date**: 2026-07-31

This is the decision record the ticket requires ("新增运行时依赖要克制,每加一个都要说得出理由,
写进决策记录"). Every technical decision below was made by the implementer; product decisions were
escalated and are recorded in `spec.md` under `## Clarifications`.

---

## D1 — Do not add a JSON Schema library. Implement the supported subset in-tree. **(decisive)**

**Decision**: Add **zero** new runtime dependencies. Implement the keyword subset from FR-002a
directly in a new pure-Python module.

**Evidence gathered** (not assumed — checked against PyPI during this phase):

`jsonschema` 4.26.0 declares:

```
attrs>=22.2.0, jsonschema-specifications>=2023.03.6, referencing>=0.28.4, rpds-py>=0.25.0
```

`rpds-py` is a **compiled Rust extension**, not pure Python. Meanwhile every one of
`sqlite-utils`'s six current runtime dependencies ships as a `py3-none-any` wheel:

| Dependency | Wheel |
|---|---|
| click | `py3-none-any` |
| click-default-group | `py3-none-any` |
| pluggy | `py3-none-any` |
| python-dateutil | `py3-none-any` |
| sqlite-fts4 | `py3-none-any` |
| tabulate | `py3-none-any` |

**Rationale**:

1. **It would break a property the project currently has.** `sqlite-utils` is installable as pure
   Python on any platform with a Python interpreter — no compiler, no platform-specific wheel, no
   binary. Adding `jsonschema` makes `rpds-py` a transitive requirement for *every* user of the
   library, including the overwhelming majority who will never run `validate`. On any platform
   without a prebuilt `rpds-py` wheel, installing `sqlite-utils` would suddenly need a Rust
   toolchain. That is a large, invisible tax to impose on the whole userbase for one command.
2. **`format` validation would need still more dependencies.** FR-002a requires `format`.
   `jsonschema` only validates `format` when the `[format]` extra is installed, which adds
   `fqdn`, `idna`, `isoduration`, `jsonpointer`, `rfc3339-validator`, `rfc3987`, `uri-template`,
   and `webcolors`. So the "just use the library" path is ~12 new transitive dependencies, not one.
3. **The library actively works against two of our hard requirements.**
   - **FR-002b (loud rejection of unsupported keywords)**: `jsonschema` is designed to *ignore*
     keywords it does not recognise — that is mandated by the JSON Schema spec itself. To satisfy
     FR-002b we would have to walk the schema ourselves and reject unknown keywords *anyway*. The
     work does not disappear; it just gets duplicated alongside a large dependency.
   - **FR-008b (coercible vs invalid type split)**: this classification does not exist in JSON
     Schema. `jsonschema` reports one `type` error. Producing the split requires our own logic on
     top regardless.
4. **The subset is genuinely small.** Fifteen keywords, no `$ref`, no `allOf`/`anyOf`/`oneOf`, no
   `if`/`then`/`else`, no remote schema resolution, no recursion beyond one object level (the spec's
   Assumptions fix the schema as describing one flat row). This is a few hundred lines of
   straightforward, fully testable code — not a re-implementation of JSON Schema.
5. **Constitution Principle V** sets the preference order as stdlib → existing dependency →
   dev-only → new runtime dependency as a last resort. Option 1 (stdlib `json`, `re`, `datetime`)
   is sufficient here, so the last resort is not reached.

**Alternatives considered**:

- *`jsonschema` as a hard runtime dependency* — rejected: reasons 1–3 above.
- *`jsonschema` as an optional extra, feature degrades without it* — rejected: gives two different
  validation behaviours depending on install state, which for a *correctness* tool is worse than
  either consistent option. A user could get "passed" on one machine and violations on another.
- *`fastjsonschema`* — pure Python and fast, but it generates code via `exec`, ignores unknown
  keywords (same FR-002b problem), and still cannot produce the FR-008b split. No advantage over
  in-tree code for a 15-keyword subset.

**Cost accepted**: we own the correctness of ~15 keyword implementations, and we do not get
`$ref`/composition for free if the requirement ever expands. Mitigated by FR-002b: anything we do
not implement is *loudly rejected*, never silently mishandled. Growth path if needed later: add
keywords to the supported set one at a time, each with tests.

---

## D2 — Frontend: TypeScript + Vite (library mode) + Vitest/jsdom

**Decision**: `vite` in library mode producing a single IIFE bundle, `vitest` with the `jsdom`
environment for DOM tests, `tsc --noEmit` for type checking. All are **devDependencies only**.

**Rationale**:
- The Tech Lead permitted "vite 或 esbuild 都行你们定". Vite wins because `vitest` is its native
  test runner — one config, one dependency tree, no separate bundler/test-runner integration.
- Library mode with `formats: ['iife']` yields exactly one self-executing `.js` file with no module
  loader and no import statements, which is what inlining into a single HTML file requires.
- `cssCodeSplit: false` keeps CSS as one emitted file to inline alongside it.
- Verified reachable during this phase: vite 8.2.0, vitest 4.1.10, typescript 7.0.2, jsdom 30.0.1.

**Constraint honoured**: Node is required only to *build* the bundle. The built artifact is
committed to the repository and shipped as package data, so installing from PyPI and running
`validate` never touches Node. This is the constitution's "Build artifacts" rule.

**Alternatives considered**:
- *esbuild alone* — fewer moving parts, but then Vitest arrives as an independent tool with its own
  transform pipeline, and we maintain two configs. Rejected on maintenance grounds, not capability.
- *No bundler, plain `tsc` to a single file* — `tsc` cannot bundle CSS and cannot produce a true
  IIFE from multiple modules without `outFile` + namespaces, which is a deprecated style. Rejected.

---

## D3 — Report assembly: template with placeholder substitution, not string-built HTML

**Decision**: Ship a small static `report.html` template containing three sentinel placeholders
(`__SQLITE_UTILS_CSS__`, `__SQLITE_UTILS_JS__`, `__SQLITE_UTILS_DATA__`). Python reads the built
CSS and JS from package data, serialises the result to JSON, and substitutes. Python emits **no**
markup and **no** script logic of its own.

**Rationale**: directly satisfies the Tech Lead's hard boundary — "我不接受在 Python 里拼
HTML/JS 字符串". Python's role is reduced to file reading, JSON serialisation, and three string
replacements. All structure lives in the template; all behaviour lives in TypeScript.

**Security detail (FR-021)**: the embedded data is injected inside
`<script type="application/json">`. Two protections are required and both are tested:
1. The JSON serialiser escapes `<`, `>`, and `&` to `\uXXXX` so a cell value containing
   `</script>` cannot terminate the tag and inject markup.
2. The TypeScript renderer builds DOM via `document.createElement` and `textContent`, never
   `innerHTML`. A cell value containing `<img onerror=...>` renders as literal text.

**Alternatives considered**:
- *Jinja2 templating* — a new runtime dependency for three substitutions. Rejected per Principle V.
- *Python `string.Template`* — stdlib, but its `$name` syntax collides with CSS/JS `$` usage and
  would require escaping the entire bundle. Plain `str.replace` on distinctive sentinels is simpler
  and has no escaping hazard.
- *Base64-encoding the data blob* — avoids all escaping questions, but makes the report opaque to
  anyone inspecting it and adds ~33% size. The `\uXXXX` escaping approach is standard and testable.

---

## D4 — Where the code lives: new `sqlite_utils/validate.py`, thin CLI wrapper

**Decision**: All logic in a new module `sqlite_utils/validate.py`. `sqlite_utils/cli.py` gains one
`@cli.command()` that parses options, calls the library, formats output, and selects the exit code.

**Rationale**: Constitution Principle I, and a hard practical reason discovered in Phase 1 of this
workflow — `mypy.ini` contains:

```ini
[mypy-sqlite_utils.cli]
ignore_errors = True
```

Anything placed in `cli.py` is **excluded from type checking**. The Tech Lead requires new Python
code to pass mypy. Therefore putting logic in `cli.py` would silently void that requirement. A new
module is the only way to actually satisfy it. Note also that `db.py` is 5,125 lines already;
adding an unrelated concern to it serves nobody.

**Alternatives considered**:
- *Methods on `Table` in `db.py`* — would match `analyze_column`'s placement, but `db.py` is
  already very large and validation is a self-contained concern with its own data types. A separate
  module keeps the diff reviewable. A `Table.validate()` convenience method is *not* added, to keep
  the public API surface change minimal for an upstream contribution.

---

## D5 — Row identification: declared primary key, falling back to `rowid`

**Decision**: identify each row by its primary key when the table has one, else by `rowid`.

**Rationale**: not invented — `Table.pks` in `db.py` (line ~2177) already implements exactly this,
returning `["rowid"]` when `use_rowid` is true. Reusing it makes violation identifiers consistent
with `pks_and_rows_where` and the rest of the library. Confirmed as expected by the requester.

---

## D6 — Streaming scan, bounded memory

**Decision**: iterate rows with a cursor; never materialise the table. Retain at most
`--max-violations` violation records (default 1,000); keep counting totals after the cap is hit.

**Rationale**: FR-024 requires true totals *and* bounded output. Counters are O(1); the retained
list is O(cap). Memory is therefore independent of table size, which is what makes the
million-row requirement (SC-006) achievable.

---

## D7 — Two independent limits with unambiguous names

**Decision**: `--scan-limit N` (examine at most N rows) and `--max-violations N` (retain at most N
violation records, default 1000). Both surfaced in the result summary as separate fields.

**Rationale**: FR-025b explicitly forbids conflating "only N rows were checked" with "only N
problems were listed". A bare `--limit` would be ambiguous between exactly these two meanings, which
is the confusion the requirement exists to prevent. Longer names are the correct trade here.

---

## D8 — Exit statuses 0 / 1 / 2

**Decision**: `0` = passed, `1` = violations found, `2` = could not run (bad schema, missing table,
unsupported keyword).

**Rationale**: `2` is not arbitrary — `click` already exits `2` for usage errors, and raising
`click.ClickException` (the pattern used throughout `cli.py`) exits `1`. Since `1` is needed for
"violations found", tool errors must be raised in a way that produces `2` to stay distinguishable.
Confirmed as expected by the requester. Implementation note: use `click.exceptions.Exit(1)` for the
violations case and a `UsageError`-style path (exit 2) for tool errors, so the two never collide.

---

## D9 — Type classification rules (implements FR-008a/b, Q1's answer)

**Decision**: compare the *SQLite storage class* of the value against the declared JSON type.

| Situation | Kind |
|---|---|
| Storage class matches declared type | pass |
| Value is `TEXT`, declared type is numeric/boolean/integer, and the text parses cleanly as it | `type-coercible` (strict) / pass (lenient) |
| Value is `TEXT`, declared type is numeric, text does not parse | `type-invalid` |
| Value is NULL, declared type does not include `"null"` | `type-invalid` |
| Value is NULL, declared type includes `"null"` | pass |
| Value is `''`, declared type is `"string"` | pass (empty string is a valid string) |

**Rationale**: this is the mechanical form of Iris's Q1 and Q4 answers. Booleans need care —
SQLite has no boolean type and stores `0`/`1` as INTEGER, so `integer` vs `boolean` needs an
explicit rule rather than falling out of Python's `isinstance(True, int) == True`.

---

## D10 — Documentation placement

**Decision**: new section in `docs/cli.rst` with a `.. _cli_validate:` label, referenced from the
CLI reference; `docs/cli-reference.rst` regenerated with `cog`.

**Rationale**: enforced by the existing test suite, not a style preference.
`tests/test_docs.py::test_commands_are_documented` parametrises over `cli.cli.commands.keys()` and
asserts each command name appears in `docs/cli.rst`. **Adding the command without documenting it
breaks the pre-existing test suite** — i.e. it would violate SC-007. `docs/cli-reference.rst` is
cog-generated and CI runs `cog --check`, so it must be regenerated, never hand-edited.

---

## Resolved unknowns

No `NEEDS CLARIFICATION` items remain. All product ambiguities were resolved in `/speckit-clarify`;
all technical unknowns are decided above with evidence.
