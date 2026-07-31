# Design: `sqlite-utils validate` — JSON Schema data validation with an interactive HTML report

Ticket: #4821. Requested by Iris (data platform PM), technical boundaries from 老周 (tooling tech lead).
Status: approved by Iris on 2026-07-31 (all nine clarifying questions answered; one amendment, see Q6).

## Problem

People load messy CSV / API exports into SQLite with `sqlite-utils insert`. Afterwards nobody can answer
"is the data in this table actually clean?" without eyeballing it. We want: *give the tool a description of
what a table should look like, get back which rows fail and a report you can forward to a non-technical
colleague.*

## Scope

In scope: one database, one table, one JSON Schema file per run. A machine-readable JSON report, a
self-contained interactive HTML report, and script-friendly exit codes.

Explicitly out of scope (confirmed with Iris): validating several tables in one run, a schema file that maps
many tables, scheduling/history, fixing or quarantining bad rows.

## Confirmed product decisions

| # | Decision |
|---|----------|
| 1 | Row identity: primary key columns (all of them for compound keys), falling back to `rowid` for rowid tables. Shown as its own column in both reports. |
| 2 | By default the report shows only the *offending column's* value, truncated. `--include-row` opts into the whole row. Reports get forwarded, so the conservative default wins. |
| 3 | Type checking is strict by default: TEXT `"42"` against `{"type": "integer"}` is a violation, because surfacing type drift during loading is the point. `--coerce` switches to lenient interpretation. |
| 4 | SQL `NULL` means "property present, value is JSON `null`" — it triggers a `type` violation unless the schema says `["string", "null"]`. It does *not* trigger `required`. The tool does not silently allow empties. |
| 5a | Columns present in the table but absent from `properties` are ignored, unless the schema itself sets `"additionalProperties": false`. Behaviour is decided by JSON Schema, we invent no private rules. |
| 5b | A column named in `required` that does not exist in the table at all produces **one table-level violation**, not one per row. |
| 6 | Whole-table scan by default so counts are exact; the report keeps the first 1000 violation details and states the true total. **Two separate knobs**: `--max-violations` caps recorded detail, `--scan-limit` checks only the first N rows (a fast probe for scripts). They must not be conflated. |
| 7 | Exit codes: `0` clean, `1` violations found, `2` tool/usage error (missing table, unreadable database, invalid schema file). A pipeline testing for `1` learns "the data is dirty" and is never confused by the tool failing. |
| 8 | Report UI is English only. No `--lang`. This is destined for upstream; minimum maintenance surface wins. |
| 9 | One table, one schema, per invocation. |

## Approaches considered

### How the HTML report is produced

* **A. Python string templating.** Rejected outright by 老周 — the previous 3000-line embedded template was
  unmaintainable and untestable.
* **B. TypeScript sources → esbuild → committed bundle → Python inlines it. (Chosen.)** The report is a real
  frontend component: data in, DOM out, unit-testable under vitest/jsdom, `tsc --noEmit` clean. Python's only
  job is substituting three strings into a shell template. Crucially, `.github/workflows/test.yml` installs
  with pip and never touches Node, so **the build output must be committed** and shipped as package data;
  neither CI nor an end user can run `npm`.
* **C. Vite instead of esbuild.** Vite is dev-server-first; for one IIFE bundle with no runtime dependencies
  esbuild is a smaller configuration surface. vitest is used for tests either way, so the choice is only about
  the production build. Rejected as unnecessary weight.

### JSON Schema implementation

* **A. Depend on `jsonschema`. (Chosen.)** It is the reference Python implementation, pure Python, permissive
  licence, and — decisively — its `iter_errors()` hands us `validator`, `validator_value`, `instance` and
  `json_path` for free, which is exactly the "expected vs actual" payload the report needs.
* **B. Hand-roll a keyword subset.** Rejected. Iris's team already has JSON Schema files in use; a partial
  implementation that silently ignores unsupported keywords reports "clean" on data it never checked. That is
  a worse failure mode than a dependency.
* **C. Optional extra (`sqlite-utils[validate]`).** Rejected: a CLI subcommand that crashes on a fresh install
  is bad UX, and the feature is meant to be a first-class command.

`jsonschema` is the **only** new runtime dependency. Node/TypeScript tooling is dev-only and never required at
install or run time.

### Where the Python logic lives

* **A. New `sqlite_utils/validate.py` module. (Chosen.)** `db.py` is already 5125 lines; `cli.py` is 3808 and,
  more importantly, is exempted from type checking by `mypy.ini` (`[mypy-sqlite_utils.cli] ignore_errors = True`).
  Putting the logic in `cli.py` would make "new Python code passes mypy" vacuously true. A separate module means
  the validation core is genuinely type-checked, and `db.py` is not touched at all — zero regression risk for the
  1371 existing tests.
* **B. A `Table.validate()` method on `db.py`.** More in keeping with the library's shape, but grows an
  already-oversized file and puts new code in the highest-blast-radius module. Rejected; `validate_table()` takes
  a `Table` as its first argument, so the ergonomics are nearly identical.

## Architecture

```
frontend/                       TypeScript sources (dev only, not shipped)
  src/types.ts                  Report data types, shared by tests and runtime
  src/filter.ts                 Pure functions: filter / search / sort violations
  src/render.ts                 DOM builders: summary, filter bar, table, detail row
  src/main.ts                   Entry point: read embedded JSON, mount into #app
  src/*.test.ts                 vitest + jsdom
  build.mjs                     esbuild bundle + copy shell template
        |
        |  npm run build   (committed output, CI never runs this)
        v
sqlite_utils/static/
  validate_report.js            IIFE bundle, no external references
  validate_report.css           Extracted styles
  validate_report.html          Shell template with $STYLES / $SCRIPT / $DATA / $TITLE

sqlite_utils/validate.py        Core: Violation, ValidationResult, validate_table(), load_schema()
sqlite_utils/report.py          render_html_report(result) -> single-file HTML string
sqlite_utils/cli.py             `validate` command: arguments, output, exit codes only
```

Data flow: `cli.validate` → `load_schema(path)` → `validate_table(table, schema, ...)` → `ValidationResult`
→ `result.to_dict()` → either `json.dump` (machine report) or `render_html_report` (human report). The HTML
report embeds exactly the same dict the JSON report contains, in a
`<script type="application/json">` block, so the two reports can never disagree.

### `sqlite_utils/validate.py`

```python
class SchemaError(Exception): ...          # unreadable / invalid schema file

@dataclass(frozen=True)
class Violation:
    row_id: dict[str, Any]                 # {"id": 5} or {"rowid": 5} or compound
    column: str | None                     # None for whole-row / table-level problems
    error_type: str                        # jsonschema keyword: type, required, enum, ...
    message: str
    expected: str
    actual: Any                            # truncated, JSON-safe
    row: dict[str, Any] | None             # only when include_row=True

@dataclass
class ValidationResult:
    table: str
    schema_title: str | None
    rows_checked: int
    total_rows: int
    scan_limited: bool
    violations: list[Violation]            # capped at max_violations
    total_violations: int                  # exact unless scan_limited
    truncated: bool                        # total_violations > len(violations)
    invalid_rows: int
    violations_by_column: dict[str, int]
    violations_by_type: dict[str, int]
    table_errors: list[str]                # decision 5b
    generated: str                         # ISO 8601 UTC
    @property def ok(self) -> bool         # False if total_violations or table_errors
    def to_dict(self) -> dict[str, Any]

def load_schema(path) -> dict[str, Any]    # raises SchemaError on bad JSON or bad schema
def validate_table(table, schema, *, max_violations=1000, scan_limit=None,
                   coerce=False, include_row=False) -> ValidationResult
```

Row → JSON object conversion: `bytes` become a UTF-8 string when decodable and a base64 string otherwise
(SQLite BLOBs have no JSON counterpart and would otherwise fail every `type` check for an uninteresting reason).
Everything else passes through unchanged, which is what makes decision 3 work.

Counting: `total_violations` and the per-column/per-type breakdowns are exact across every scanned row even
after detail collection stops at `max_violations`. `scan_limit` is the only thing that makes counts partial,
and it sets `scan_limited` so the reports can say so.

### `sqlite_utils/report.py`

One function, `render_html_report(data: dict) -> str`. It reads the three committed assets, and substitutes
via `string.Template.safe_substitute` (which does not rescan substituted values, so `$` inside CSS or JS is
safe). The embedded JSON has `</` escaped to `<\/` so it cannot terminate the script element early. No network
references are produced, and a test asserts that.

### Frontend behaviour

Summary strip (rows checked, invalid rows, total violations, "showing first N of M" when truncated, table-level
errors); a filter bar with a column dropdown, an error-type dropdown, and a free-text search box; a sortable
table of violations; each row expands to show expected vs actual (and the full row when `--include-row` was
used). `filter.ts` holds the pure logic and gets the bulk of the tests; `render.ts` is tested by mounting into
a jsdom document and asserting on the DOM.

### CLI

```
sqlite-utils validate data.db mytable schema.json
    --json report.json        write the machine report (use - for stdout)
    --html report.html        write the self-contained human report
    --max-violations N        detail cap, default 1000
    --scan-limit N            only check the first N rows
    --coerce                  lenient type interpretation
    --include-row             put the whole row in the reports
    --silent                  suppress the stdout summary, exit code only
    --load-extension          (repo convention, present on every db command)
```

Default stdout is a short human summary — rows checked, invalid rows, total violations, table-level errors, and
the top offending columns — regardless of whether `--json` / `--html` were requested. `--silent` suppresses it.

`table_errors` (decision 5b) are kept separate from `total_violations`: they describe the table's shape rather
than individual rows, so they are never counted as row violations, but their presence alone makes the run fail
with exit code 1.

Errors: table missing / schema unreadable / schema not a valid JSON Schema raise a `ClickException` subclass
whose `exit_code` is 2. Violations print a summary and `ctx.exit(1)`. A clean table exits 0, and an empty table
is clean.

## Testing

* `tests/test_validate.py` — library level: clean pass, type violation, required missing, null semantics,
  `--coerce` behaviour, `additionalProperties: false`, `scan_limit`, `max_violations` truncation with exact
  totals, empty table, primary-key vs rowid identity, compound primary key, table-level missing required column,
  BLOB handling.
* `tests/test_cli_validate.py` — exit codes 0/1/2, JSON report shape, HTML report written, HTML is
  self-contained (no `http://`, `https://`, `src=`, external `href=`), missing table, invalid schema file,
  `--silent`, and an end-to-end demo: build a dirty table, validate, generate HTML, assert the expected
  violations appear in it.
* `frontend/src/*.test.ts` — vitest, jsdom environment, covering filtering, searching, sorting and rendering.
* Existing suite must stay at 1371 passed / 19 skipped.

## Documentation

* `docs/cli.rst` — new `.. _cli_validate:` section. This is load-bearing: `tests/test_docs.py` fails if a
  command is missing from it.
* `docs/cli-reference.rst` — add `validate` to the cog `refs` mapping and re-run cog (CI runs `cog --check`).
* `docs/python-api.rst` — how to call `validate_table()` from Python.
* `docs/reference.rst` — autodoc entries for the new public objects.
* `docs/contributing.rst` — how to rebuild the report bundle, and that the output is committed on purpose.

## Risks

* **Committed build output drifts from its sources.** Mitigated by documenting the rebuild command and keeping
  the bundle small; a CI job that rebuilds and diffs would be the upstream follow-up.
* **`jsonschema` on a million rows.** One compiled validator reused across rows keeps this to a few tens of
  seconds; `--scan-limit` is the escape hatch for interactive use.
* **Report size.** 1000 violations of truncated values is a few hundred KB of embedded JSON — fine in a browser.
