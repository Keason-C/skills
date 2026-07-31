# Feature Specification: Data Quality Validation & Interactive Report

**Feature Branch**: `001-data-validation-report`

**Created**: 2026-07-31

**Status**: Clarified — ready for `/speckit-plan`

**Input**: Internal ticket #4821. Requested by Iris (Data Platform PM), technical boundaries set by
the toolchain Tech Lead. Verbatim source: `TASK2.md` at repository root.

---

## Problem Statement

Teams load messy CSV exports and API dumps into SQLite using this tool. Once loaded, the most
frequently asked question is *"is the data in this table actually clean?"* Today nobody can answer
it — the only method is eyeballing samples. There is no way to state what a table is *supposed* to
look like, and no way to get a shareable answer about how it deviates.

## Clarifications

### Session 2026-07-31

- Q: When a column holds the text `"42"` and the schema says that column must be an integer, should
  that count as clean or as a violation? → A: **Configurable, strict by default.** Exposing "the CSV
  arrived untyped" is a primary goal, not a nuisance — 100% violations on day one is the true state
  of the data and must be visible. Additionally, type failures MUST be split into two distinct
  kinds so a strict run is still triageable: values that are *coercible* to the declared type
  (`"42"` against `integer`) and values that are *not* (`"abc"` against `integer`). Lenient
  behaviour is available as an opt-in switch.
- Q: Which JSON Schema features do your existing internal schemas actually use, and which draft?
  → A: **Practical subset, Draft 2020-12 semantics.** Mandatory: `type` (including union form such
  as `["string","null"]`), `properties`, `required`, `enum`, `minimum`/`maximum`,
  `minLength`/`maxLength`, `pattern`, `additionalProperties`. Also supported: `const`,
  `exclusiveMinimum`/`exclusiveMaximum`, `format`, `multipleOf`. **Any keyword outside the supported
  set MUST cause a loud, explicit failure — silently ignoring a keyword and reporting the table as
  validated is forbidden.** The dependency tradeoff for achieving this is an implementer decision.
- Q: If the table has columns your schema says nothing about, should that be reported? → A: **Honour
  the schema's own `additionalProperties` keyword; ignore when unset.** No private rule is to be
  invented on top of JSON Schema.
- Q: When a cell is NULL and the schema marks that column required, is that a violation? → A: **NULL
  is JSON `null`.** `required` is NOT triggered by a NULL value, because the column itself is always
  present. `type` catches it instead, unless the schema explicitly permits `"null"`. This makes
  "nullable" something the schema author expresses, with no leniency added by the tool. The empty
  string `''` is a valid string and is distinct from NULL.
- Q: The report is forwarded to operations. Should it contain the raw offending cell values? → A:
  **Yes, with limits.** Show the real value, truncated only when excessively long, but show **only
  the offending column's value — not the whole row**. Whole-row display is an explicit opt-in. These
  tables carry no regulated personal data, so report usefulness takes priority. Machine-specific
  detail such as absolute filesystem paths MUST NOT appear in the report.
- Q: (follow-up, requester-initiated) Is a row-scan cap needed in addition to the detail cap? → A:
  **Yes.** A separate "check only the first N rows" parameter is required for fast spot-checks from
  scripts. Its semantics are independent of the violation-detail cap, and it must be possible to use
  either without the other.

Technical decisions confirmed by the requester as matching expectations (recorded in
`clarification-session.md`, not re-litigated here): row identification prefers the declared primary
key and falls back to `rowid`; violation detail defaults to 1,000 entries; exit statuses are
0 / 1 / 2; scanning is streaming rather than materialised.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Check a loaded table against a declared shape (Priority: P1)

A data engineer has just loaded a CSV into a SQLite table. They already maintain a JSON Schema
document describing what a well-formed record looks like. They point the tool at the database, the
table, and the schema file, and get back a verdict: how many rows were checked, how many failed, and
what exactly was wrong with them.

**Why this priority**: This is the irreducible core. Without a validation verdict there is nothing to
report on and nothing to automate. Every other story consumes its output.

**Independent Test**: Load a table containing a known mix of clean and dirty rows, run validation
against a schema, and assert that exactly the dirty rows are reported with the correct reason for
each. Delivers value on its own — an engineer can read the terminal output and act.

**Acceptance Scenarios**:

1. **Given** a table whose every row satisfies the schema, **When** validation runs, **Then** the
   result reports zero violations and signals success.
2. **Given** a table where one row holds a value that is not of the declared type and cannot be
   interpreted as it (`"abc"` against `integer`), **When** validation runs, **Then** exactly that row
   is reported as an *invalid type* violation, naming the column, the expected type, and the actual
   value.
3. **Given** a table where one row holds a text value that *could* be interpreted as the declared
   type (`"42"` against `integer`), **When** validation runs in the default strict mode, **Then**
   that row is reported as a *coercible type* violation — a kind distinct from the one in scenario 2,
   so the two can be filtered apart.
4. **Given** the same table, **When** validation runs with lenient typing enabled, **Then** the
   coercible value passes and only the genuinely invalid value is reported.
5. **Given** a column whose value is NULL and whose schema type does not include `"null"`, **When**
   validation runs, **Then** that row is reported as a type violation — not as a missing-required
   violation, because the column is present.
6. **Given** a column whose value is NULL and whose schema type is the union `["string","null"]`,
   **When** validation runs, **Then** no violation is reported for it.
7. **Given** a column whose value is the empty string and whose schema type is `"string"`, **When**
   validation runs, **Then** no violation is reported — the empty string is a valid string and is
   distinct from NULL.
8. **Given** a schema that marks a column as required and a table that does not have that column at
   all, **When** validation runs, **Then** a missing-column violation is reported once for the table
   rather than repeated for every row.
9. **Given** a single row that breaks two different rules, **When** validation runs, **Then** both
   violations are reported separately, each with its own column and reason.
10. **Given** an empty table, **When** validation runs, **Then** the result reports zero rows checked
    and zero violations, and signals success rather than an error.

---

### User Story 2 - Use the verdict to gate an automated pipeline (Priority: P1)

A pipeline step runs validation as part of a nightly load. The pipeline does not read prose — it
branches on the process exit status, and archives a machine-readable result document for later
analysis and trend tracking.

**Why this priority**: Equal-highest with Story 1. Iris stated the pipeline requirement explicitly
("脚本里要能用,所以'有没有问题'得从退出码上看得出来"), and a validator that cannot fail a build is
decorative. It is separable from Story 1 only in that it adds exit-status and machine-output
semantics on top of the same verdict.

**Independent Test**: Run the command in a shell against clean and dirty tables and assert the
recorded exit status differs; parse the machine-readable output with a standard parser and assert it
contains the same violations shown in the terminal.

**Acceptance Scenarios**:

1. **Given** a table with no violations, **When** the command runs, **Then** it exits with a status
   meaning success.
2. **Given** a table with at least one violation, **When** the command runs, **Then** it exits with a
   distinct non-success status that a shell script can test for.
3. **Given** a request for machine-readable output, **When** the command runs, **Then** it emits a
   single valid JSON document containing the run summary and every reported violation.
4. **Given** a named table that does not exist in the database, **When** the command runs, **Then**
   it reports a clear error naming the missing table and exits with a status distinguishable from
   "validation found violations".
5. **Given** a schema file that is not readable as a valid schema document, **When** the command
   runs, **Then** it reports a clear error identifying the problem and exits with a status
   distinguishable from "validation found violations".
6. **Given** a schema that uses a keyword outside the supported set, **When** the command runs,
   **Then** it refuses to run, names the unsupported keyword and where it appeared, and exits with
   the "could not run" status. It MUST NOT validate the table while ignoring that keyword, because
   reporting a pass that silently skipped a constraint is worse than reporting nothing.

---

### User Story 3 - Hand a browsable report to a non-technical colleague (Priority: P2)

An operations colleague receives a single report file by chat or email. They open it by
double-clicking. They see a summary, then a table of problems they can filter by column, filter by
kind of problem, free-text search, and sort. Clicking a row expands it to show what was expected
versus what was actually there. Their machine has no network restrictions but they are unwilling to
install anything, and the report must work regardless of connectivity.

**Why this priority**: P2 because it depends on Stories 1 and 2 producing a verdict first, but it is
the reason the ticket exists — Iris's stated goal is "一份能直接转发给运营看的报告页面". A report that
is a wall of text fails this story even if it is technically correct.

**Independent Test**: Generate a report from a known dirty table, open the produced file, and assert
it renders a summary and violation list; drive the filter, search, sort, and expand interactions and
assert the displayed set changes correctly. Separately assert the file references no external
resource.

**Acceptance Scenarios**:

1. **Given** a validation run with violations, **When** a human-readable report is requested,
   **Then** a single self-contained file is produced that opens in a browser with no other files
   alongside it.
2. **Given** the produced report file, **When** its contents are inspected, **Then** it contains no
   reference to any remote resource — no remote scripts, stylesheets, fonts, images, or network calls
   of any kind.
3. **Given** an open report containing violations in several columns, **When** the reader filters to
   one column, **Then** only violations for that column remain listed and the visible count updates.
4. **Given** an open report, **When** the reader filters by kind of problem, **Then** only violations
   of that kind remain listed.
5. **Given** an open report, **When** the reader types a term into search, **Then** only violations
   matching that term in their row identifier, column, message, or value remain listed.
6. **Given** an open report, **When** the reader sorts by a column, **Then** the listed violations
   reorder accordingly and the sort direction can be reversed.
7. **Given** an open report, **When** the reader expands a single violation, **Then** they see what
   the schema expected and what the row actually contained.
8. **Given** a validation run with zero violations, **When** a report is requested, **Then** the
   report is still produced and states clearly that the table passed.

---

### User Story 4 - Validate a table too large to report on in full (Priority: P3)

A data engineer validates a table with millions of rows. They want an honest count of how bad the
situation is without waiting for, or trying to open, a report containing millions of entries.

**Why this priority**: P3 — correctness at small scale must land first, and Iris framed this as
"别把浏览器搞死" rather than a hard requirement. But shipping without it makes the feature unusable on
the tables that motivated the request.

**Independent Test**: Validate a table whose violation count exceeds the reporting limit and assert
that totals are accurate while the reported detail set is bounded and explicitly marked as truncated.

**Acceptance Scenarios**:

1. **Given** a table producing more violations than the reporting limit, **When** validation runs,
   **Then** the summary counts reflect the true totals, not the truncated subset.
2. **Given** such a run, **When** the reader opens either output, **Then** it states plainly that the
   detail list is truncated and how many entries were omitted.
3. **Given** such a run, **When** the reader is only interested in the shape of the problem, **Then**
   the retained subset is sufficient to see which columns and problem kinds dominate.
4. **Given** a very large table and a request to check only the first N rows, **When** validation
   runs, **Then** it examines at most N rows, reports that it did so, and returns quickly rather than
   scanning the whole table.
5. **Given** a run that is both row-capped and detail-capped, **When** the reader inspects the
   result, **Then** the two limits are reported separately and neither is presented as the other —
   "we only looked at 1,000 rows" and "we only listed 1,000 problems" are different statements.

---

### Edge Cases

- **Empty table** — zero rows checked, zero violations, treated as a pass, not an error.
- **Table does not exist** — clear error naming the table; distinguishable exit status; no report
  file written.
- **Schema file missing, unreadable, malformed, or not a valid schema** — clear error; nothing
  written; distinguishable exit status.
- **Schema declares a column the table does not have** — reported once as a table-level
  missing-column violation, not repeated per row; otherwise a typo in the schema would either pass
  silently or generate one violation per row for a single mistake.
- **Schema uses an unsupported keyword** — refuse to run, name the keyword, exit as "could not run".
  Never validate-while-ignoring.
- **Table has columns the schema says nothing about** — governed by the schema's own
  `additionalProperties`; ignored when that keyword is unset.
- **A row breaks several rules at once** — every violation reported individually, not collapsed.
- **NULL against a type that excludes null** — a type violation, not a required violation.
- **NULL against a union type including `"null"`** — passes.
- **NULL in a column named in `required`** — passes `required`; the column exists. Only `type` can
  reject it.
- **Empty string** — a valid string; distinct from NULL; must not be conflated with it.
- **Text that is coercible to the declared type** (`"42"` against `integer`) — a violation under the
  default strict mode, but classified separately from genuinely invalid values so the two can be
  filtered apart; passes under lenient mode.
- **Zero violations with a report requested** — a report is still produced, stating the pass.
- **Row cap and detail cap applied together** — reported as two distinct facts, never merged.
- **Values that are large, binary, or contain markup** — must be displayed safely and without making
  the report unreadable or unsafe to open.
- **Report opened with no network connectivity at all** — full functionality retained.

## Requirements *(mandatory)*

### Functional Requirements

**Declaring expectations**

- **FR-001**: The system MUST accept a table's expected shape as a JSON Schema document supplied as a
  file, interpreted with Draft 2020-12 semantics. It MUST NOT require users to learn a new constraint
  language.
- **FR-002**: The system MUST reject an invalid or unparsable schema document with an actionable
  error before examining any data.
- **FR-002a**: The system MUST support at least these keywords: `type` (including union form such as
  `["string","null"]`), `properties`, `required`, `enum`, `const`, `minimum`, `maximum`,
  `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf`, `minLength`, `maxLength`, `pattern`,
  `format`, and `additionalProperties`.
- **FR-002c**: The system MUST recognise these `format` values: `date`, `date-time`, `time`,
  `email`, `uri`, and `ipv4`. A `format` value outside this set MUST be rejected in the same loud
  manner as an unsupported keyword (FR-002b) rather than accepted and ignored — otherwise a schema
  asking for `"format": "uuid"` would silently validate nothing while appearing to constrain.
- **FR-002b**: The system MUST refuse to run when the schema contains any keyword outside its
  supported set, naming the offending keyword and its location. It MUST NOT validate a table while
  silently disregarding a constraint it does not understand. A pass that skipped a constraint is a
  false assurance and is treated as a defect, not a limitation.
- **FR-003**: The system MUST report a schema-declared column that is absent from the table as a
  table-level violation, emitted once per run rather than once per row.

**Producing a verdict**

- **FR-004**: The system MUST check every row of the named table against the schema and produce, for
  each failure, at minimum: an identifier locating the row, the column concerned, the kind of
  problem, a human-readable message, the value found, and what was expected.
- **FR-005**: The system MUST report each distinct failure within a row separately.
- **FR-006**: The system MUST produce a run summary containing at least: rows checked, rows with at
  least one violation, total violation count, a breakdown by problem kind, and a breakdown by column.
- **FR-007**: The system MUST treat an empty table as a successful validation of zero rows.
- **FR-008**: The system MUST report a request for a non-existent table as an error, clearly
  distinguished from a data-quality failure.

**Value semantics**

- **FR-008a**: The system MUST compare stored values against declared types strictly by default: a
  value whose stored type differs from the declared type is a violation even when it could be
  interpreted as that type.
- **FR-008b**: The system MUST classify type failures into two distinct, separately filterable kinds:
  values that can be interpreted as the declared type, and values that cannot.
- **FR-008c**: The system MUST offer an opt-in lenient mode in which a value that can be interpreted
  as the declared type is accepted.
- **FR-008d**: The system MUST treat SQLite NULL as JSON `null`: it satisfies `required` (the column
  exists) and is rejected by `type` unless the declared type admits `"null"`.
- **FR-008e**: The system MUST treat the empty string as a valid string value, distinct from NULL.
- **FR-008f**: The system MUST delegate the treatment of columns absent from the schema to the
  schema's own `additionalProperties` keyword, ignoring such columns when the keyword is unset.

**Automation surface**

- **FR-009**: The system MUST expose validation such that a shell script can determine, from the
  process exit status alone, whether the table passed.
- **FR-010**: The system MUST use exit statuses that distinguish (a) passed, (b) violations found,
  and (c) the tool could not run — a caller MUST NOT be able to confuse a broken schema file with
  dirty data.
- **FR-011**: The system MUST be able to emit the complete result as a single machine-parseable JSON
  document suitable for archiving in a pipeline.
- **FR-012**: The same validation capability MUST be available programmatically as a library call,
  not only through the command line, returning the same result structure.

**Human-readable report**

- **FR-013**: The system MUST be able to produce a human-readable report as a single file that opens
  directly in a browser.
- **FR-014**: The report file MUST be entirely self-contained: it MUST NOT reference or request any
  remote resource, and MUST be fully functional with no network access.
- **FR-015**: The report MUST present the run summary before the violation detail.
- **FR-016**: The report MUST let the reader narrow the violation list by column.
- **FR-017**: The report MUST let the reader narrow the violation list by kind of problem.
- **FR-018**: The report MUST let the reader free-text search the violation list.
- **FR-019**: The report MUST let the reader sort the violation list and reverse the sort direction.
- **FR-020**: The report MUST let the reader expand an individual violation to see expected versus
  actual.
- **FR-021**: The report MUST remain readable and safe when values contain markup, control
  characters, or unusual length; content from the database MUST NOT be able to alter the report's
  structure or behaviour.
- **FR-022**: The report MUST state clearly when a table passed with zero violations.
- **FR-022a**: The report MUST show the real offending value, truncating only when it exceeds 200
  characters, and MUST mark a truncated value as such so a reader never mistakes a shortened value
  for the whole one.
- **FR-022b**: The report MUST show only the offending column's value by default. Displaying the
  full row MUST be an explicit opt-in.
- **FR-022c**: The report MUST NOT contain machine-specific detail such as absolute filesystem paths.

**Scale**

- **FR-023**: The system MUST bound the number of individual violations carried into its outputs, so
  that a very dirty large table does not produce an unopenable report.
- **FR-024**: When that bound is applied, summary totals MUST continue to reflect true totals, and
  both outputs MUST state that the detail list was truncated and by how much.
- **FR-025**: The bound MUST be adjustable by the caller.
- **FR-025a**: The system MUST offer a separate limit on how many rows are examined, for fast
  spot-checks from scripts.
- **FR-025b**: The row-examination limit and the violation-detail limit MUST be independent: either
  may be used without the other, and outputs MUST report them as two distinct facts so that "only N
  rows were checked" is never confused with "only N problems were listed".

**Fitting the existing product**

- **FR-026**: The capability MUST follow the conventions already established by this tool's other
  commands and library functions — option naming, error reporting, output formatting, and
  documentation placement.
- **FR-027**: The new command MUST be discoverable from the existing documentation index and command
  reference.

### Key Entities

- **Schema Document**: A user-authored JSON Schema describing what one well-formed row of the table
  should look like. Owned and versioned by the user, not by this tool.
- **Validation Run**: One application of a Schema Document to one table, producing a Result.
- **Violation**: A single failed expectation. Locates itself (row identifier + column), classifies
  itself (kind of problem), and explains itself (message, expected, actual). A violation may be
  table-level (no row identifier) when the problem is about the table's shape rather than a row's
  contents.
- **Violation Kind**: The classification used for filtering. Must at minimum distinguish: a missing
  column; a value of an unusable type; a value of a wrong-but-interpretable type; and each supported
  constraint keyword's failure mode.
- **Result Summary**: Aggregate counts for a Validation Run — rows checked, rows failed, violations
  total, counts per problem kind, counts per column, whether the row scan was capped, and whether
  the violation detail was truncated.
- **Report**: A rendering of a Result for a particular audience — one for machines, one for people.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A data engineer who already has a JSON Schema can get a clean/dirty verdict on a table
  with a single command and no prior configuration.
- **SC-002**: Every violation reported is traceable to a specific row and column, such that a user
  can locate the offending record in the source table without guessing.
- **SC-003**: A pipeline can gate on data quality using only the process exit status, and can
  distinguish "the data is bad" from "the check itself failed" without parsing any text output.
- **SC-004**: A non-technical reader can open the report with no installation step, no server, and no
  network, and can narrow thousands of violations to the handful they care about using filter,
  search, and sort alone.
- **SC-005**: A reader can determine, for any listed violation, both what was expected and what was
  actually present, without consulting the schema file or the database.
- **SC-006**: Validating a table with millions of rows produces accurate summary totals and a report
  that opens and remains responsive.
- **SC-007**: Every previously existing behaviour of the tool is unchanged — the pre-existing
  automated test suite passes in full, with no test modified or removed.
- **SC-008**: The new capability is documented where users already look for command documentation,
  and the documentation's own automated checks pass.
- **SC-009**: A user can never receive a "passed" verdict that was produced by ignoring part of their
  schema — an unsupported constraint always stops the run instead of being skipped.
- **SC-010**: On a freshly imported, wholly untyped CSV table, the default run makes the lack of
  typing visible, and the reader can still separate "this value is the wrong type but salvageable"
  from "this value is garbage" without reading every entry.
- **SC-011**: A script can spot-check a multi-million-row table in a fraction of the time a full scan
  would take, and the output makes unmistakably clear that only part of the table was examined.

## Assumptions

- Users supply their own JSON Schema documents; authoring, discovering, or inferring schemas is out
  of scope for this feature.
- Validation is read-only. It never modifies, repairs, quarantines, or deletes data. Auto-fixing is
  out of scope.
- One run validates one table against one schema. Whole-database validation and cross-table
  referential checks are out of scope.
- The schema describes a single row as an object whose properties correspond to columns; it does not
  describe the table as a whole.
- Reports are point-in-time artifacts. Storing history, diffing runs, or tracking trends is out of
  scope; the machine-readable output exists so users can build that themselves.
- Row-level constraints only. Aggregate assertions ("this column must have fewer than 5% nulls
  overall", uniqueness across rows) are out of scope for this feature.
- The report is read-only. Readers cannot annotate, assign, or resolve violations from it.
- Readers of the report use a current mainstream browser.
- No new network access is introduced at any point — neither validation nor report viewing performs
  any network activity.
- The tables in scope carry no regulated personal data; report usefulness is therefore prioritised
  over redaction. Should that change, FR-022b's default becomes the mitigation point.
- A strict-by-default type policy will report violations on any column whose storage type does not
  match the schema. Note (verified against this repository, not assumed): `sqlite-utils insert --csv`
  *does* apply type detection, so a column of clean integers is stored as INTEGER and passes, while a
  column containing any non-numeric value stays TEXT and is flagged. Strict mode therefore highlights
  precisely the columns that failed to type cleanly — a narrower and more useful signal than "every
  column fails". This is the intended behaviour, not a defect.
- An empty cell in an imported CSV becomes the empty string, not NULL. FR-008e therefore governs it,
  and it will not satisfy a numeric type.
