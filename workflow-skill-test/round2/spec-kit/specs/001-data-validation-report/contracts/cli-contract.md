# Contract — CLI surface

**Command**: `sqlite-utils validate`

```
sqlite-utils validate DB_PATH TABLE SCHEMA [OPTIONS]
```

## Arguments

| Argument | Description |
|---|---|
| `DB_PATH` | Path to the SQLite database. Must exist. |
| `TABLE` | Name of the table to validate. |
| `SCHEMA` | Path to the JSON Schema file. Must exist. |

Positional argument style and `click.Path(exists=True)` usage follow `analyze-tables` and other
existing commands in `cli.py`.

## Options

| Option | Type | Default | Effect |
|---|---|---|---|
| `--json` | flag | off | Emit the full result as JSON to stdout (FR-011) |
| `--html PATH` | path | — | Write the self-contained HTML report to PATH (FR-013) |
| `--lenient-types` | flag | off | Accept coercible type mismatches (FR-008c) |
| `--max-violations N` | int | 1000 | Cap retained violation detail (FR-023, FR-025) |
| `--scan-limit N` | int | none | Examine at most N rows (FR-025a) |
| `--full-row` | flag | off | Include the whole row in report detail (FR-022b) |
| `--load-extension` | text | — | Existing repo-wide option, applied for consistency |

Default (no `--json`, no `--html`): a concise human summary on stdout.

## Exit statuses (FR-009, FR-010)

| Status | Meaning |
|---|---|
| `0` | Validation ran; zero violations |
| `1` | Validation ran; one or more violations found |
| `2` | Could not run — missing table, unreadable/invalid schema, unsupported keyword |

Status `2` must be reachable **only** via tool failure, never via dirty data. This is the property
a pipeline depends on and it is directly tested.

## Error messages

All tool errors go to **stderr**; machine output goes to **stdout**, so `--json` output stays
parseable when a warning is emitted.

| Condition | Message shape |
|---|---|
| Table absent | `Error: table 'X' does not exist` |
| Schema file unparsable | `Error: schema file is not valid JSON: <detail>` |
| Unsupported keyword | `Error: unsupported JSON Schema keyword 'X' at <location>` |
| Schema not an object | `Error: schema must be a JSON object` |

Per FR-022c, no absolute filesystem path is embedded in the **HTML report**. (Paths in stderr
messages are fine — those stay on the operator's terminal and never travel.)
