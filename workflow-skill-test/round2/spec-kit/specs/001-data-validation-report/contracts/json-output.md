# Contract — JSON output

Emitted by `sqlite-utils validate --json`, and the exact payload embedded in the HTML report.
One shape, two consumers — this is what guarantees the machine and human reports agree (FR-011).

## Shape

```json
{
  "table": "events",
  "ok": false,
  "summary": {
    "table": "events",
    "rows_checked": 1000,
    "rows_with_violations": 3,
    "total_violations": 4,
    "violations_by_kind": { "type-invalid": 2, "enum": 1, "missing-column": 1 },
    "violations_by_column": { "age": 2, "status": 1, "email": 1 },
    "truncated": false,
    "scan_limited": false,
    "max_violations": 1000,
    "scan_limit": null
  },
  "violations": [
    {
      "kind": "missing-column",
      "column": "email",
      "message": "Column 'email' is required by the schema but does not exist in the table",
      "row_id": null,
      "value": null,
      "expected": "column present"
    },
    {
      "kind": "type-invalid",
      "column": "age",
      "message": "Expected integer, got text that cannot be read as integer",
      "row_id": "7",
      "value": "abc",
      "expected": "integer"
    }
  ]
}
```

## Field guarantees

- `ok` is `true` **iff** `summary.total_violations == 0`. It is derived, never independently set.
- `summary.total_violations` is the **true** count, even when `violations` has been truncated
  (FR-024). Therefore `len(violations) <= summary.total_violations`, with equality exactly when
  `truncated` is `false`.
- `violations_by_kind` and `violations_by_column` are likewise **true** totals, unaffected by
  truncation — so a truncated report still shows accurately which columns dominate (US4 scenario 3).
- `truncated` and `scan_limited` are independent booleans (FR-025b). Either, both, or neither.
- `row_id` is `null` exactly for table-level kinds (`missing-column`, `unexpected-column`).
- `value` is JSON-safe: `bytes` is replaced by the placeholder `"<binary: N bytes>"` rather than
  failing serialisation.
- The document is always a single valid JSON object, including on a clean table.

## Stability

This shape is the archival format pipelines will store. Field removals or renames are breaking
changes. Adding fields is backwards-compatible.
