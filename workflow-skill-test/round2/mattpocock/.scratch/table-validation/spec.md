# Spec: table validation against a row schema, with a shareable HTML report

Status: ready-for-agent
Source: internal ticket #4821 (`TASK2.md`), grilling round 1 answered by Iris
(`grilling-round-1.md`), research note `research/jsonschema-dependency.md`,
ADR-0001, ADR-0002, ADR-0003.

Vocabulary is `CONTEXT.md`'s: **row schema**, **violation**, **violation kind**,
**schema error**, **schema/table mismatch**, **scan limit**, **detail cap**,
**validation result**, **JSON report**, **HTML report**.

## Problem Statement

People load messy CSVs and API exports into SQLite with `sqlite-utils`, and then
cannot answer the only question anyone asks afterwards: *is this data any good?*
Today the answer is eyeballing a few rows. There is no way to state what a table
is supposed to look like, no way to get a machine-readable answer in a pipeline,
and nothing that can be forwarded to a non-technical colleague who has to decide
whether to trust the data.

## Solution

A new `sqlite-utils validate` command, and a matching `Table.validate()` Python
API, that take a **row schema** — an ordinary JSON Schema document describing one
row — and report every **violation** in the table.

The result comes out three ways: a human summary on stdout, a **JSON report**
for pipelines, and a self-contained **HTML report** that can be emailed to an
operations colleague and opened offline. The process exit code says whether the
data was clean (`0`), had violations (`1`), or could not be validated at all
(`2`), so a script can gate on it.

## User Stories

1. As a data engineer, I want to describe my table's expected shape in JSON
   Schema, so that I reuse the schemas my team already writes instead of learning
   another DSL.
2. As a data engineer, I want `sqlite-utils validate db.db table schema.json` to
   tell me which rows are bad, so that I stop eyeballing samples.
3. As a data engineer, I want a non-zero exit code when violations exist, so that
   my pipeline fails loudly on dirty data.
4. As a data engineer, I want a *different* non-zero exit code when the command
   could not run at all, so that I can tell "the data is dirty" from "my job is
   broken".
5. As a data engineer, I want the JSON report written to a path I choose, so that
   the next pipeline step can consume it.
6. As an operations colleague, I want a single HTML file I can double-click, so
   that I can review data quality without installing anything.
7. As an operations colleague, I want the HTML report to work with no network
   access, so that it renders the same on a locked-down machine.
8. As an operations colleague, I want to filter violations by column, so that I
   can look only at the field I own.
9. As an operations colleague, I want to filter violations by violation kind, so
   that I can deal with all the missing values before the malformed ones.
10. As an operations colleague, I want to search violations by text, so that I
    can find the one record someone emailed me about.
11. As an operations colleague, I want to sort the violations, so that I can
    group what I'm looking at.
12. As an operations colleague, I want to expand a violation and see expected
    versus actual, so that I understand what "bad" means without asking an
    engineer.
13. As an operations colleague, I want the report to name the table, the database
    file and the schema file it came from, so that I know what I am looking at.
14. As an operations colleague, I want to see when the report was generated, so
    that I don't act on a stale one.
15. As a data platform owner, I want absolute filesystem paths kept out of the
    report, so that forwarding it doesn't leak our machine layout.
16. As a data platform owner, I want only the key and the offending value shown
    by default, so that forwarding a report doesn't forward the whole dataset.
17. As a data engineer, I want an explicit switch to include entire rows, so that
    I can debug deeply when the report is not being forwarded.
18. As a data engineer, I want exact violation counts even on a million-row
    table, so that I can trust "how bad is it" and not just "here are some".
19. As a data engineer, I want the itemised list capped, so that the HTML report
    stays openable, and I want the report to say plainly that it is capped.
20. As a data engineer, I want a way to check only the first N rows, so that I
    can use validation as a fast probe inside a loop.
21. As a data engineer, I want the string `"123"` in a TEXT column to fail
    `"type": "integer"`, so that type drift from CSV loading is exposed rather
    than hidden.
22. As a data engineer, I want "wrong type but would convert cleanly" reported as
    its own violation kind, so that I can separate type drift from genuine
    garbage.
23. As a data engineer, I want an explicit switch that accepts convertible
    values, so that I can validate a table I already know is text-typed.
24. As a data engineer, I want `NULL` to be judged as JSON `null` against the
    schema's `type`, so that "this column may be empty" is something my schema
    states rather than something the tool guesses.
25. As a data engineer, I want an explicit switch to treat empty strings as
    `null` too, so that I can match how my loader behaved.
26. As a data engineer, I want to be told when my schema names a column the table
    does not have, so that I catch typos instead of silently validating nothing.
27. As a data engineer, I want extra columns not mentioned in the schema to be
    ignored unless I set `additionalProperties: false`, so that the tool behaves
    like JSON Schema and not like a surprise.
28. As a data engineer, I want a schema using a keyword the tool cannot evaluate
    to be rejected outright, so that I am never told data is clean when it was
    only partly checked.
29. As a data engineer, I want an unreadable or malformed schema file to fail
    clearly, so that I fix the file instead of debugging the data.
30. As a data engineer, I want validating a table that does not exist to fail
    clearly, so that a typo in a table name is not reported as "no violations".
31. As a data engineer, I want an empty table to validate cleanly, so that an
    empty load is not confused with a broken one.
32. As a Python API user, I want `db["t"].validate(schema)` to return a
    validation result object, so that I can build my own tooling on it.
33. As a `sqlite-utils` maintainer, I want no new runtime dependency, so that the
    install story stays "works everywhere with no toolchain".
34. As a `sqlite-utils` maintainer, I want the report UI to be typed, built and
    unit-tested, so that nobody inherits an unmaintainable template string.
35. As a `sqlite-utils` maintainer, I want the new command documented like every
    other command, so that the docs tests and the CLI reference stay coherent.

## Implementation Decisions

### Where the behaviour lives

- A new module owns validation end to end: parsing a row schema into a checkable
  form, walking the table, and producing a **validation result**. It is the deep
  module here — a lot of behaviour (schema interpretation, SQLite type mapping,
  coercion rules, counting, capping) behind a small interface.
- `Table` gains one method, `validate()`, delegating to that module. It sits
  beside `analyze_column()`, the existing "inspect this table and describe it"
  method, and follows its shape: keyword-only tuning parameters with defaults,
  returning a value object rather than printing.
- A second new module renders a validation result to the two reports. It knows
  nothing about databases; it takes a validation result and returns text.
- The CLI command is a thin adapter: parse arguments, call `Table.validate()`,
  hand the result to the renderers, choose an exit code. No validation logic.
- `cli.py` is excluded from mypy in this repo (`mypy.ini`), which is another
  reason to keep it thin — the typed code must be in the library modules.

### The interface

- `Table.validate(schema, *, scan_limit=None, detail_cap=1000, coerce=False,
  empty_is_null=False, include_rows=False) -> ValidationResult`, where `schema`
  is the already-parsed JSON Schema document (a `dict`). Reading and parsing the
  *file* is the CLI's job; the library takes a document.
- A parse step turns the document into a checkable form and raises a **schema
  error** for anything it cannot evaluate. Parsing happens once, before the table
  is walked, so a bad schema fails immediately rather than a million times.
- `ValidationResult` carries: the table name, total rows, rows scanned, rows with
  violations, total violation count, the retained violations, counts by column,
  counts by violation kind, schema/table mismatches, and whether the detail cap
  was hit. `.ok` is true when there are no violations and no mismatches.
- A `Violation` carries: the row's key, the column, the violation kind, a
  human-readable expectation, the actual value (truncated), and the row itself
  when whole rows were requested.

### Row identity

- The table's primary key values identify a row; a table without one uses its
  `rowid`. The key is a mapping of column name to value so the report can show
  it verbatim.

### Schema interpretation

- Supported keywords, and *only* these (ADR-0001): at the document level `type`
  (must be `object`), `properties`, `required`, `additionalProperties` (boolean);
  per column `type` (single or a union list, `null` included), `enum`,
  `minimum`, `maximum`, `minLength`, `maxLength`, `pattern`. Annotation keywords
  (`$schema`, `$id`, `title`, `description`, `$comment`, `default`, `examples`)
  are accepted and ignored.
- Anything else — `$ref`, `allOf`, `anyOf`, `oneOf`, `not`, `items`, `format`,
  `const`, `exclusiveMinimum`, `multipleOf`, … — is a schema error naming the
  keyword and the column it appeared on.
- JSON Schema types map onto SQLite values as: `string` ↔ `str`, `integer` ↔
  `int` (and `bool` is *not* an integer), `number` ↔ `int`/`float`,
  `boolean` ↔ `bool`, `null` ↔ `None`. SQLite has no boolean storage class, so
  `boolean` also accepts the integers `0` and `1`. `bytes` (BLOB) satisfies no
  JSON Schema type.
- **`NULL` is present-as-null** (Iris, follow-up clarification): a SQL `NULL` is
  the JSON value `null` on a field that *exists*. It therefore never triggers
  `required`; it triggers `type` unless the schema admits null
  (`"type": ["string", "null"]`). "May be empty" is expressed with `type` and
  nothing else. Consequently `required` can only fail at the table level, as a
  schema/table mismatch — a column that exists is on every row.
- `empty_is_null` makes `''` behave as that same JSON `null` — so with the flag
  on, an empty string in a `"type": "string"` column becomes a `type` violation.
  Without it, `''` is just a string (Iris, Q2).
- A value that fails `type` but whose text would parse as the expected type is
  the `type-coercible` violation kind, not `type` — the distinction Iris asked
  for. With `coerce=True` such a value passes instead, and subsequent keywords
  (`minimum`, `pattern`, …) are checked against the converted value.
- Constraint keywords apply only to values of the relevant kind, per JSON Schema:
  `minLength`/`maxLength`/`pattern` apply to strings, `minimum`/`maximum` to
  numbers; a value of another type is not additionally penalised by them.
- `pattern` is a regular expression searched (not anchored), matching JSON
  Schema semantics.

### Counting and capping

- The table is scanned once, in full, so counts are exact (`scan_limit` is the
  only thing that shortens the scan, and the result records that it did).
- Every violation increments the counters; only the first `detail_cap`
  violations are retained with detail. The result records both numbers so the
  reports can say "showing 1,000 of N".

### CLI shape

- `sqlite-utils validate PATH TABLE SCHEMA` with `--json PATH`, `--html PATH`,
  `--limit N` (scan limit), `--max-violations N` (detail cap, default 1000),
  `--coerce`, `--empty-null`, `--full-rows`, `--silent`.
- Exit codes 0/1/2 per ADR-0002, implemented as a `ClickException` subclass
  overriding `exit_code`.
- Human summary on stdout mirrors the layout `analyze-tables` established.

### HTML report

- Built from TypeScript with Vite, unit-tested with vitest in a DOM
  environment, bundle committed and shipped as package data (ADR-0003).
- Python's contribution is: read the committed bundle, JSON-encode the validation
  result with `<` escaped, and interpolate both into a small HTML skeleton. No
  markup or behaviour is authored in Python.
- The page is one file with no external references of any kind.
- The report shows database basename, table name, schema file basename,
  generation timestamp, totals, counts by column and by kind, the capped notice,
  filters (column, kind, free text), sorting, and per-violation expected/actual
  detail. No absolute paths anywhere.

## Testing Decisions

A good test here exercises **external behaviour through the smallest number of
seams**, and would survive a rewrite of the internals. It asserts on the
validation result and on the rendered artifacts, never on private helpers.

Three seams, two of which already exist in this repo:

1. **`Table.validate()`** — the library seam, and the highest one available.
   Nearly all Python behaviour is tested here: clean data, each violation kind,
   `NULL`-against-`type` in both directions (schema admits null / does not),
   a required column absent from the table, empty table, coercion on and off,
   empty-string handling with and without `empty_is_null`,
   schema/table mismatch, scan limit, detail cap, row keys with and without a
   primary key. Prior art: `tests/test_analyze_tables.py`, which drives
   `db[...].analyze_column()` against a fixture database.
2. **The CLI, via `click.testing.CliRunner`** — exit code semantics, JSON and
   HTML file output, schema file errors, missing table, argument validation.
   Prior art: `tests/test_cli.py`, used throughout the repo, with `isolated_filesystem`.
3. **The report module in TypeScript, via vitest with a DOM** — filtering,
   searching, sorting, expansion, and the capped-notice text, driven through the
   exported render function against a real `document`. No prior art in this repo;
   it is the first JS in it.

Plus one **end-to-end test** that runs the CLI over a deliberately dirty table,
generates the HTML, and asserts both that the expected violations appear in the
file and that the file references nothing external.

## Out of Scope

- Cross-row constraints: uniqueness, row counts, referential checks. JSON Schema
  has no vocabulary for them and inventing one was explicitly ruled out.
- Validating more than one table per invocation, and combined multi-table reports.
- Fixing or quarantining bad rows — this feature reports, it does not repair.
- Percentage thresholds for pass/fail.
- `$ref` resolution, remote schemas, nested object/array validation.
- Validating views.

## Further Notes

- Product acceptance from Iris pins the supported keyword list; it may grow, but
  `type`/`properties`/`required`/`enum`/`minimum`/`maximum`/`minLength`/
  `maxLength`/`pattern`/`additionalProperties` must all work, and unsupported
  keywords must fail loudly.
- `tests/test_docs.py` mechanically requires the new command to appear in
  `docs/cli.rst` as `$ sqlite-utils validate …`, and `docs/cli-reference.rst` is
  cog-generated — `just cog` must be re-run.
