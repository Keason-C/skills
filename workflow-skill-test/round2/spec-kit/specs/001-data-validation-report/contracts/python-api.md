# Contract — Python API

Satisfies FR-012: the same capability available programmatically, returning the same structure the
CLI uses. All logic lives here; the CLI is a thin wrapper (Constitution Principle I, research D4).

## Public surface — `sqlite_utils/validate.py`

```python
def compile_schema(raw: object) -> CompiledSchema: ...

def validate_table(
    db: Database,
    table: str,
    schema: CompiledSchema | Mapping[str, object],
    *,
    lenient_types: bool = False,
    max_violations: int = 1000,
    scan_limit: int | None = None,
    include_full_row: bool = False,
) -> ValidationResult: ...

def build_html_report(result: ValidationResult) -> str: ...
```

Plus the exported types: `ValidationResult`, `ValidationSummary`, `Violation`, `ViolationKind`,
`CompiledSchema`, `SchemaError`.

## Behavioural contract

| Condition | Behaviour |
|---|---|
| `table` absent from `db` | raise `NoTable` (**existing** `db.py` exception — not a new one) |
| schema unsupported/malformed | raise `SchemaError` |
| empty table | return a result with `rows_checked == 0`, `ok is True` |
| `schema` given as a plain mapping | compiled internally; `SchemaError` still raised eagerly |
| `max_violations` reached | stop retaining, keep counting; set `summary.truncated` |
| `scan_limit` reached | stop reading rows; set `summary.scan_limited` |

Reusing `NoTable` rather than inventing a new exception is deliberate: `db.py` already raises it for
this exact condition, and a second exception meaning the same thing would violate Constitution
Principle II.

`build_html_report` returns the complete HTML document as a string. It performs **no** file I/O and
**no** network access, so it is directly unit-testable and cannot leak a filesystem path (FR-022c).

## Type checking

The module carries complete annotations and must pass `mypy` under the repository's existing
`mypy.ini` with no new ignores and no relaxation of settings.
