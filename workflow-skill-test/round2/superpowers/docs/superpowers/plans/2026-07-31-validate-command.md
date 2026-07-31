# `sqlite-utils validate` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `sqlite-utils validate` command that checks a table against a JSON Schema and emits a machine-readable JSON report plus a self-contained interactive HTML report, with script-friendly exit codes.

**Architecture:** Validation logic lives in a new, fully type-annotated `sqlite_utils/validate.py` (deliberately *not* in `cli.py`, which `mypy.ini` exempts from type checking, nor in the already-5000-line `db.py`). The HTML report is a TypeScript component bundled by esbuild into `sqlite_utils/static/`; those build artifacts are committed because CI installs with pip and has no Node. `sqlite_utils/report.py` does nothing but substitute the bundle and the report JSON into a shell template.

**Tech Stack:** Python 3.10+, click, `jsonschema` (the single new runtime dependency), TypeScript, esbuild, vitest + jsdom, Sphinx + cog for docs.

## Global Constraints

- Existing test suite baseline is **1371 passed, 19 skipped**. Zero regressions permitted.
- `jsonschema` is the only permitted new runtime dependency. All Node tooling is dev-only and must never be needed at install or run time.
- All new Python code carries full type annotations and passes `uv run mypy sqlite_utils tests`.
- New Python logic must NOT go in `sqlite_utils/cli.py` — `mypy.ini` sets `[mypy-sqlite_utils.cli] ignore_errors = True`, so code there is not type-checked. `cli.py` holds argument parsing, output and exit codes only.
- `sqlite_utils/db.py` must not be modified.
- No HTML/JS/CSS logic may be written as Python string literals. Python only performs placeholder substitution on a committed template file.
- `frontend/` must pass `npx tsc --noEmit` and `npm test` (vitest).
- The generated HTML must be fully self-contained: no `http://`, no `https://`, no external `src=` or `href=` references.
- Exit codes: `0` = no violations, `1` = violations found, `2` = tool or usage error.
- Report UI is English only. No `--lang` option.
- Code must satisfy `uv run black . --check` and `uv run flake8` (max line length 160).
- `tests/test_docs.py` fails unless the new command appears in `docs/cli.rst` matching `(?:\$ |    )sqlite-utils (\S+)`.
- CI runs `cog --check --diff README.md docs/*.rst`, so `docs/cli-reference.rst` must be regenerated after adding the command.
- Reference the spec at `docs/superpowers/specs/2026-07-31-validate-design.md` for the nine confirmed product decisions.

---

### Task 1: Add the `jsonschema` dependency and the validation core's data types

**Files:**
- Modify: `pyproject.toml` (the `dependencies` list)
- Create: `sqlite_utils/validate.py`
- Test: `tests/test_validate.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `sqlite_utils.validate.SchemaError`, `Violation`, `ValidationResult`, `load_schema(path) -> dict[str, Any]`.

`Violation` fields: `row_id: dict[str, Any]`, `column: str | None`, `error_type: str`, `message: str`, `expected: str`, `actual: Any`, `row: dict[str, Any] | None = None`.

`ValidationResult` fields: `table: str`, `schema_title: str | None`, `rows_checked: int`, `total_rows: int`, `scan_limited: bool`, `violations: list[Violation]`, `total_violations: int`, `truncated: bool`, `invalid_rows: int`, `violations_by_column: dict[str, int]`, `violations_by_type: dict[str, int]`, `table_errors: list[str]`, `generated: str`. Plus `ok: bool` property and `to_dict() -> dict[str, Any]`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_validate.py
import json
import pytest
from sqlite_utils.validate import SchemaError, ValidationResult, Violation, load_schema


def test_load_schema_reads_json(tmpdir):
    path = str(tmpdir / "schema.json")
    with open(path, "w") as fp:
        json.dump({"type": "object", "properties": {"id": {"type": "integer"}}}, fp)
    assert load_schema(path) == {
        "type": "object",
        "properties": {"id": {"type": "integer"}},
    }


def test_load_schema_rejects_invalid_json(tmpdir):
    path = str(tmpdir / "schema.json")
    with open(path, "w") as fp:
        fp.write("{not json")
    with pytest.raises(SchemaError) as ex:
        load_schema(path)
    assert "not valid JSON" in str(ex.value)


def test_load_schema_rejects_invalid_schema(tmpdir):
    path = str(tmpdir / "schema.json")
    with open(path, "w") as fp:
        json.dump({"type": "not-a-real-type"}, fp)
    with pytest.raises(SchemaError) as ex:
        load_schema(path)
    assert "not a valid JSON Schema" in str(ex.value)


def test_load_schema_rejects_missing_file(tmpdir):
    with pytest.raises(SchemaError):
        load_schema(str(tmpdir / "nope.json"))


def test_validation_result_ok_and_to_dict():
    result = ValidationResult(
        table="t",
        schema_title=None,
        rows_checked=2,
        total_rows=2,
        scan_limited=False,
        violations=[],
        total_violations=0,
        truncated=False,
        invalid_rows=0,
        violations_by_column={},
        violations_by_type={},
        table_errors=[],
        generated="2026-07-31T00:00:00Z",
    )
    assert result.ok
    assert result.to_dict()["table"] == "t"
    assert result.to_dict()["violations"] == []


def test_validation_result_not_ok_when_table_errors():
    result = ValidationResult(
        table="t",
        schema_title=None,
        rows_checked=0,
        total_rows=0,
        scan_limited=False,
        violations=[],
        total_violations=0,
        truncated=False,
        invalid_rows=0,
        violations_by_column={},
        violations_by_type={},
        table_errors=["Column 'name' is required by the schema but does not exist"],
        generated="2026-07-31T00:00:00Z",
    )
    assert not result.ok


def test_violation_to_dict_round_trips_through_json():
    violation = Violation(
        row_id={"rowid": 1},
        column="age",
        error_type="type",
        message="'x' is not of type 'integer'",
        expected="integer",
        actual="x",
    )
    assert json.loads(json.dumps(violation.to_dict()))["column"] == "age"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_validate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sqlite_utils.validate'`

- [ ] **Step 3: Add the dependency**

In `pyproject.toml`, add `"jsonschema",` to the `dependencies` list (keep the list alphabetically neighbouring the existing entries: after `"click-default-group>=1.2.3",` is fine). Then run `uv sync --group dev`.

- [ ] **Step 4: Write minimal implementation**

```python
# sqlite_utils/validate.py
"""Validate the contents of a SQLite table against a JSON Schema."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import jsonschema
from jsonschema.exceptions import SchemaError as JsonSchemaError
from jsonschema.validators import validator_for


class SchemaError(Exception):
    """Raised when a JSON Schema file cannot be read or is not a valid schema."""


@dataclass(frozen=True)
class Violation:
    """A single JSON Schema violation found in a table row."""

    row_id: dict[str, Any]
    column: str | None
    error_type: str
    message: str
    expected: str
    actual: Any
    row: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "row_id": self.row_id,
            "column": self.column,
            "error_type": self.error_type,
            "message": self.message,
            "expected": self.expected,
            "actual": self.actual,
        }
        if self.row is not None:
            data["row"] = self.row
        return data


@dataclass
class ValidationResult:
    """The outcome of validating one table against one schema."""

    table: str
    schema_title: str | None
    rows_checked: int
    total_rows: int
    scan_limited: bool
    violations: list[Violation]
    total_violations: int
    truncated: bool
    invalid_rows: int
    violations_by_column: dict[str, int]
    violations_by_type: dict[str, int]
    table_errors: list[str] = field(default_factory=list)
    generated: str = ""

    @property
    def ok(self) -> bool:
        "True if no violations and no table-level errors were found."
        return not self.total_violations and not self.table_errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "table": self.table,
            "schema_title": self.schema_title,
            "generated": self.generated,
            "ok": self.ok,
            "rows_checked": self.rows_checked,
            "total_rows": self.total_rows,
            "scan_limited": self.scan_limited,
            "invalid_rows": self.invalid_rows,
            "total_violations": self.total_violations,
            "truncated": self.truncated,
            "violations_by_column": self.violations_by_column,
            "violations_by_type": self.violations_by_type,
            "table_errors": self.table_errors,
            "violations": [violation.to_dict() for violation in self.violations],
        }


def load_schema(path: str) -> dict[str, Any]:
    """
    Load and check a JSON Schema from a file path.

    :param path: Path to a file containing a JSON Schema
    """
    try:
        with open(path, "r", encoding="utf-8") as fp:
            schema = json.load(fp)
    except OSError as ex:
        raise SchemaError(f"Could not read schema file {path}: {ex}") from ex
    except json.JSONDecodeError as ex:
        raise SchemaError(f"Schema file {path} is not valid JSON: {ex}") from ex
    if not isinstance(schema, dict):
        raise SchemaError(f"Schema file {path} is not a valid JSON Schema: expected an object")
    validator_class = validator_for(schema)
    try:
        validator_class.check_schema(schema)
    except JsonSchemaError as ex:
        raise SchemaError(f"Schema file {path} is not a valid JSON Schema: {ex.message}") from ex
    return schema


assert jsonschema  # keep the import meaningful until validate_table lands
```

Note: delete that trailing `assert jsonschema` line in Task 2, where the `jsonschema` import gains a real use.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/test_validate.py -v`
Expected: PASS (7 tests)

- [ ] **Step 6: Check types and formatting**

Run: `uv run mypy sqlite_utils tests && uv run black sqlite_utils tests && uv run flake8`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock sqlite_utils/validate.py tests/test_validate.py
git commit -m "Add jsonschema dependency and validation result types"
```

---

### Task 2: Implement `validate_table()`

**Files:**
- Modify: `sqlite_utils/validate.py`
- Test: `tests/test_validate.py`

**Interfaces:**
- Consumes: `Violation`, `ValidationResult` from Task 1.
- Produces:
  ```python
  def validate_table(
      table: "sqlite_utils.db.Table",
      schema: dict[str, Any],
      *,
      max_violations: int = 1000,
      scan_limit: int | None = None,
      coerce: bool = False,
      include_row: bool = False,
  ) -> ValidationResult
  ```

Behaviour required by the spec's confirmed decisions:
- Row identity is `table.pks` (`["rowid"]` when `table.use_rowid`), emitted as a dict.
- Strict types by default; `coerce=True` converts a string to int/float/bool first *when* the schema declares that type for the property.
- SQL `NULL` becomes JSON `null` — a `type` violation, never a `required` violation.
- Extra table columns are ignored unless the schema sets `"additionalProperties": false`.
- A column in the schema's `required` list that does not exist in the table produces one entry in `table_errors` and is removed from the per-row `required` check.
- Counts stay exact after detail collection stops at `max_violations`; only `scan_limit` makes them partial.
- `bytes` values become a UTF-8 string when decodable, otherwise base64.
- `actual` values are truncated to 200 characters.

- [ ] **Step 1: Write the failing tests**

```python
# append to tests/test_validate.py
import base64
import sqlite_utils
from sqlite_utils.validate import validate_table

PERSON_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "name": {"type": "string"},
        "age": {"type": "integer", "minimum": 0},
    },
    "required": ["id", "name"],
}


@pytest.fixture
def db():
    return sqlite_utils.Database(memory=True)


def test_clean_table_has_no_violations(db):
    db["people"].insert_all(
        [{"id": 1, "name": "Cleo", "age": 5}, {"id": 2, "name": "Pancakes", "age": 3}],
        pk="id",
    )
    result = validate_table(db["people"], PERSON_SCHEMA)
    assert result.ok
    assert result.rows_checked == 2
    assert result.total_violations == 0
    assert result.invalid_rows == 0


def test_type_violation_is_strict_by_default(db):
    db["people"].insert_all(
        [{"id": 1, "name": "Cleo", "age": "5"}], pk="id", columns={"age": str}
    )
    result = validate_table(db["people"], PERSON_SCHEMA)
    assert not result.ok
    assert result.total_violations == 1
    violation = result.violations[0]
    assert violation.column == "age"
    assert violation.error_type == "type"
    assert violation.expected == "integer"
    assert violation.actual == "5"
    assert violation.row_id == {"id": 1}


def test_coerce_accepts_numeric_strings(db):
    db["people"].insert_all(
        [{"id": 1, "name": "Cleo", "age": "5"}], pk="id", columns={"age": str}
    )
    result = validate_table(db["people"], PERSON_SCHEMA, coerce=True)
    assert result.ok


def test_null_is_a_type_violation_not_a_required_violation(db):
    db["people"].insert_all([{"id": 1, "name": None, "age": 5}], pk="id")
    result = validate_table(db["people"], PERSON_SCHEMA)
    assert result.total_violations == 1
    assert result.violations[0].error_type == "type"
    assert result.violations[0].column == "name"


def test_nullable_schema_allows_null(db):
    db["people"].insert_all([{"id": 1, "name": None, "age": 5}], pk="id")
    schema = {
        "type": "object",
        "properties": {"id": {"type": "integer"}, "name": {"type": ["string", "null"]}},
    }
    assert validate_table(db["people"], schema).ok


def test_missing_required_column_is_a_table_error(db):
    db["people"].insert_all([{"id": 1, "age": 5}], pk="id")
    result = validate_table(db["people"], PERSON_SCHEMA)
    assert result.table_errors == [
        "Column 'name' is required by the schema but does not exist in table 'people'"
    ]
    assert result.total_violations == 0
    assert not result.ok


def test_extra_columns_ignored_by_default(db):
    db["people"].insert_all([{"id": 1, "name": "Cleo", "nickname": "C"}], pk="id")
    assert validate_table(db["people"], PERSON_SCHEMA).ok


def test_additional_properties_false_flags_extra_columns(db):
    db["people"].insert_all([{"id": 1, "name": "Cleo", "nickname": "C"}], pk="id")
    schema = dict(PERSON_SCHEMA, additionalProperties=False)
    result = validate_table(db["people"], schema)
    assert result.total_violations == 1
    assert result.violations[0].error_type == "additionalProperties"


def test_empty_table_is_clean(db):
    db["people"].create({"id": int, "name": str, "age": int}, pk="id")
    result = validate_table(db["people"], PERSON_SCHEMA)
    assert result.ok
    assert result.rows_checked == 0
    assert result.total_rows == 0


def test_rowid_used_when_no_primary_key(db):
    db["people"].insert_all([{"id": 1, "name": 5}])
    result = validate_table(db["people"], PERSON_SCHEMA)
    assert result.violations[0].row_id == {"rowid": 1}


def test_compound_primary_key_in_row_id(db):
    db["stats"].insert_all([{"year": 2026, "code": "a", "value": "bad"}], pk=("year", "code"))
    schema = {"type": "object", "properties": {"value": {"type": "integer"}}}
    result = validate_table(db["stats"], schema)
    assert result.violations[0].row_id == {"year": 2026, "code": "a"}


def test_max_violations_truncates_details_but_not_counts(db):
    db["people"].insert_all(
        [{"id": i, "name": "n", "age": "bad"} for i in range(1, 21)],
        pk="id",
        columns={"age": str},
    )
    result = validate_table(db["people"], PERSON_SCHEMA, max_violations=5)
    assert len(result.violations) == 5
    assert result.total_violations == 20
    assert result.truncated is True
    assert result.scan_limited is False
    assert result.violations_by_column == {"age": 20}
    assert result.violations_by_type == {"type": 20}


def test_scan_limit_checks_only_first_rows(db):
    db["people"].insert_all(
        [{"id": i, "name": "n", "age": "bad"} for i in range(1, 21)],
        pk="id",
        columns={"age": str},
    )
    result = validate_table(db["people"], PERSON_SCHEMA, scan_limit=5)
    assert result.rows_checked == 5
    assert result.total_rows == 20
    assert result.total_violations == 5
    assert result.scan_limited is True


def test_include_row_adds_full_row(db):
    db["people"].insert_all([{"id": 1, "name": "Cleo", "age": "x"}], pk="id", columns={"age": str})
    without = validate_table(db["people"], PERSON_SCHEMA)
    assert without.violations[0].row is None
    with_row = validate_table(db["people"], PERSON_SCHEMA, include_row=True)
    assert with_row.violations[0].row == {"id": 1, "name": "Cleo", "age": "x"}


def test_blob_decoded_as_text_when_possible(db):
    db["files"].insert_all([{"id": 1, "body": b"hello"}], pk="id")
    schema = {"type": "object", "properties": {"body": {"type": "string"}}}
    assert validate_table(db["files"], schema).ok


def test_binary_blob_becomes_base64_string(db):
    db["files"].insert_all([{"id": 1, "body": b"\xff\xfe"}], pk="id")
    schema = {"type": "object", "properties": {"body": {"type": "integer"}}}
    result = validate_table(db["files"], schema)
    assert result.violations[0].actual == base64.b64encode(b"\xff\xfe").decode("ascii")


def test_minimum_violation_reports_expected_and_actual(db):
    db["people"].insert_all([{"id": 1, "name": "Cleo", "age": -1}], pk="id")
    result = validate_table(db["people"], PERSON_SCHEMA)
    assert result.violations[0].error_type == "minimum"
    assert result.violations[0].expected == "0"
    assert result.violations[0].actual == -1


def test_invalid_rows_counts_rows_not_violations(db):
    db["people"].insert_all([{"id": 1, "name": 5, "age": -1}], pk="id")
    result = validate_table(db["people"], PERSON_SCHEMA)
    assert result.total_violations == 2
    assert result.invalid_rows == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_validate.py -v`
Expected: FAIL — `ImportError: cannot import name 'validate_table'`

- [ ] **Step 3: Write the implementation**

Remove the `assert jsonschema` placeholder line added in Task 1. Add these imports at the top of `sqlite_utils/validate.py`: `import base64`, `from datetime import datetime, timezone`, `from typing import TYPE_CHECKING, Any, Iterable`, and under `if TYPE_CHECKING:` add `from sqlite_utils.db import Table`. Then append:

```python
MAX_ACTUAL_LENGTH = 200


def _json_safe(value: Any) -> Any:
    "Convert a SQLite value into something JSON Schema and json.dumps can handle."
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return base64.b64encode(value).decode("ascii")
    return value


def _truncate(value: Any) -> Any:
    if isinstance(value, str) and len(value) > MAX_ACTUAL_LENGTH:
        return value[:MAX_ACTUAL_LENGTH] + "…"
    return value


def _coerce_row(row: dict[str, Any], properties: dict[str, Any]) -> dict[str, Any]:
    "Best-effort conversion of string values to the type the schema declares."
    coerced = dict(row)
    for key, value in row.items():
        if not isinstance(value, str):
            continue
        subschema = properties.get(key)
        if not isinstance(subschema, dict):
            continue
        declared = subschema.get("type")
        types = [declared] if isinstance(declared, str) else list(declared or [])
        for type_name in types:
            if type_name == "integer":
                try:
                    coerced[key] = int(value)
                except ValueError:
                    continue
                break
            if type_name == "number":
                try:
                    coerced[key] = float(value)
                except ValueError:
                    continue
                break
            if type_name == "boolean" and value.lower() in ("true", "false"):
                coerced[key] = value.lower() == "true"
                break
    return coerced


def _expected(error: "jsonschema.ValidationError") -> str:
    value = error.validator_value
    if isinstance(value, (str, int, float, bool)) or value is None:
        return str(value)
    return json.dumps(value, default=str)


def _column_for(error: "jsonschema.ValidationError") -> str | None:
    for part in error.absolute_path:
        if isinstance(part, str):
            return part
    if error.validator == "required":
        # message looks like: 'name' is a required property
        message = error.message
        if message.startswith("'") and "'" in message[1:]:
            return message[1 : message.index("'", 1)]
    if error.validator == "additionalProperties":
        parts = error.message.split("'")
        if len(parts) > 1:
            return parts[1]
    return None


def _row_identity(table: "Table") -> list[str]:
    return ["rowid"] if table.use_rowid else table.pks


def _iter_rows(table: "Table", identity: list[str], scan_limit: int | None) -> Iterable[dict[str, Any]]:
    columns = ", ".join(f"[{name}]" for name in identity) + ", *" if table.use_rowid else "*"
    sql = f"select {columns} from [{table.name}]"
    if scan_limit is not None:
        sql += f" limit {int(scan_limit)}"
    cursor = table.db.execute(sql)
    names = [description[0] for description in cursor.description]
    for row in cursor.fetchall():
        yield dict(zip(names, row))


def validate_table(
    table: "Table",
    schema: dict[str, Any],
    *,
    max_violations: int = 1000,
    scan_limit: int | None = None,
    coerce: bool = False,
    include_row: bool = False,
) -> ValidationResult:
    """
    Validate every row of ``table`` against a JSON Schema.

    :param table: A ``sqlite_utils.db.Table`` to validate
    :param schema: A JSON Schema, as returned by :func:`load_schema`
    :param max_violations: Maximum number of violation details to record - counts stay exact
    :param scan_limit: Only check the first N rows, making counts partial
    :param coerce: Interpret string values as the type the schema declares before validating
    :param include_row: Record the complete row alongside each violation
    """
    identity = _row_identity(table)
    table_columns = {column.name for column in table.columns}
    properties = schema.get("properties") or {}

    table_errors: list[str] = []
    effective_schema = dict(schema)
    required = [name for name in schema.get("required", []) if isinstance(name, str)]
    missing_required = [name for name in required if name not in table_columns]
    if missing_required:
        for name in missing_required:
            table_errors.append(
                "Column '{}' is required by the schema but does not exist in table '{}'".format(
                    name, table.name
                )
            )
        effective_schema["required"] = [
            name for name in required if name in table_columns
        ]

    validator_class = validator_for(effective_schema)
    validator = validator_class(effective_schema)

    violations: list[Violation] = []
    total_violations = 0
    invalid_rows = 0
    rows_checked = 0
    by_column: dict[str, int] = {}
    by_type: dict[str, int] = {}

    for raw_row in _iter_rows(table, identity, scan_limit):
        rows_checked += 1
        row = {key: _json_safe(value) for key, value in raw_row.items()}
        row_id = {name: row[name] for name in identity if name in row}
        candidate = {key: value for key, value in row.items() if key != "rowid" or "rowid" in properties}
        if coerce:
            candidate = _coerce_row(candidate, properties)
        errors = sorted(validator.iter_errors(candidate), key=lambda error: str(error.absolute_path))
        if errors:
            invalid_rows += 1
        for error in errors:
            total_violations += 1
            column = _column_for(error)
            by_column[column or ""] = by_column.get(column or "", 0) + 1
            by_type[str(error.validator)] = by_type.get(str(error.validator), 0) + 1
            if len(violations) < max_violations:
                violations.append(
                    Violation(
                        row_id=row_id,
                        column=column,
                        error_type=str(error.validator),
                        message=error.message,
                        expected=_expected(error),
                        actual=_truncate(error.instance),
                        row=dict(row) if include_row else None,
                    )
                )

    return ValidationResult(
        table=table.name,
        schema_title=schema.get("title"),
        rows_checked=rows_checked,
        total_rows=table.count,
        scan_limited=scan_limit is not None and table.count > rows_checked,
        violations=violations,
        total_violations=total_violations,
        truncated=total_violations > len(violations),
        invalid_rows=invalid_rows,
        violations_by_column=by_column,
        violations_by_type=by_type,
        table_errors=table_errors,
        generated=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_validate.py -v`
Expected: PASS. If `test_rowid_used_when_no_primary_key` fails because `rowid` leaks into the validated object, confirm the `candidate` filter excludes `rowid` unless the schema declares it.

- [ ] **Step 5: Run the full suite for regressions**

Run: `uv run pytest -q`
Expected: 1371 existing tests still pass, plus the new ones.

- [ ] **Step 6: Check types and formatting**

Run: `uv run mypy sqlite_utils tests && uv run black sqlite_utils tests && uv run flake8`

- [ ] **Step 7: Commit**

```bash
git add sqlite_utils/validate.py tests/test_validate.py
git commit -m "Implement validate_table() against a JSON Schema"
```

---

### Task 3: Frontend scaffolding, types and pure filter/sort logic

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/vitest.config.ts`, `frontend/.gitignore`
- Create: `frontend/src/types.ts`, `frontend/src/filter.ts`
- Test: `frontend/src/filter.test.ts`

**Interfaces:**
- Consumes: the JSON shape produced by `ValidationResult.to_dict()` in Task 1.
- Produces:
  ```ts
  export interface ViolationRow { row_id: Record<string, unknown>; column: string | null;
    error_type: string; message: string; expected: string; actual: unknown;
    row?: Record<string, unknown>; }
  export interface ReportData { table: string; schema_title: string | null; generated: string;
    ok: boolean; rows_checked: number; total_rows: number; scan_limited: boolean;
    invalid_rows: number; total_violations: number; truncated: boolean;
    violations_by_column: Record<string, number>; violations_by_type: Record<string, number>;
    table_errors: string[]; violations: ViolationRow[]; }
  export interface FilterState { column: string; errorType: string; search: string; }
  export type SortKey = "row" | "column" | "error_type";
  export function filterViolations(v: ViolationRow[], f: FilterState): ViolationRow[];
  export function sortViolations(v: ViolationRow[], key: SortKey, ascending: boolean): ViolationRow[];
  export function formatRowId(rowId: Record<string, unknown>): string;
  export function formatValue(value: unknown): string;
  export function uniqueColumns(v: ViolationRow[]): string[];
  export function uniqueErrorTypes(v: ViolationRow[]): string[];
  ```

- [ ] **Step 1: Create the project files**

`frontend/package.json`:
```json
{
  "name": "sqlite-utils-validate-report",
  "private": true,
  "version": "0.0.0",
  "type": "module",
  "description": "TypeScript sources for the sqlite-utils validate HTML report",
  "scripts": {
    "build": "node build.mjs",
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "devDependencies": {
    "esbuild": "^0.25.0",
    "jsdom": "^26.0.0",
    "typescript": "^5.7.0",
    "vitest": "^3.0.0"
  }
}
```

`frontend/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2020",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "lib": ["ES2020", "DOM"],
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noImplicitReturns": true,
    "noEmit": true,
    "skipLibCheck": true,
    "types": ["vitest/globals"]
  },
  "include": ["src"]
}
```

`frontend/vitest.config.ts`:
```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.test.ts"],
  },
});
```

`frontend/.gitignore`:
```
node_modules
```

Then run `cd frontend && npm install`.

Note: `npm install` writes `frontend/package-lock.json`. Commit it — it is the only thing that makes the committed bundle reproducible.

- [ ] **Step 2: Write the failing test**

```ts
// frontend/src/filter.test.ts
import { describe, expect, it } from "vitest";
import {
  filterViolations,
  formatRowId,
  formatValue,
  sortViolations,
  uniqueColumns,
  uniqueErrorTypes,
} from "./filter";
import type { ViolationRow } from "./types";

const violations: ViolationRow[] = [
  { row_id: { id: 1 }, column: "age", error_type: "type", message: "'x' is not of type 'integer'", expected: "integer", actual: "x" },
  { row_id: { id: 2 }, column: "name", error_type: "required", message: "'name' is a required property", expected: "['name']", actual: null },
  { row_id: { id: 3 }, column: "age", error_type: "minimum", message: "-1 is less than the minimum of 0", expected: "0", actual: -1 },
];

describe("filterViolations", () => {
  it("returns everything when the filter is empty", () => {
    expect(filterViolations(violations, { column: "", errorType: "", search: "" })).toHaveLength(3);
  });

  it("filters by column", () => {
    const result = filterViolations(violations, { column: "age", errorType: "", search: "" });
    expect(result.map((v) => v.error_type)).toEqual(["type", "minimum"]);
  });

  it("filters by error type", () => {
    const result = filterViolations(violations, { column: "", errorType: "required", search: "" });
    expect(result).toHaveLength(1);
  });

  it("combines column and error type", () => {
    expect(filterViolations(violations, { column: "age", errorType: "minimum", search: "" })).toHaveLength(1);
  });

  it("searches messages, values and row ids case-insensitively", () => {
    expect(filterViolations(violations, { column: "", errorType: "", search: "MINIMUM" })).toHaveLength(1);
    expect(filterViolations(violations, { column: "", errorType: "", search: "id=2" })).toHaveLength(1);
  });

  it("returns nothing when the search matches nothing", () => {
    expect(filterViolations(violations, { column: "", errorType: "", search: "zzz" })).toHaveLength(0);
  });
});

describe("sortViolations", () => {
  it("sorts by column ascending and descending", () => {
    expect(sortViolations(violations, "column", true).map((v) => v.column)).toEqual(["age", "age", "name"]);
    expect(sortViolations(violations, "column", false).map((v) => v.column)).toEqual(["name", "age", "age"]);
  });

  it("sorts by error type", () => {
    expect(sortViolations(violations, "error_type", true).map((v) => v.error_type)).toEqual(["minimum", "required", "type"]);
  });

  it("does not mutate its input", () => {
    const before = violations.map((v) => v.column);
    sortViolations(violations, "column", false);
    expect(violations.map((v) => v.column)).toEqual(before);
  });
});

describe("helpers", () => {
  it("formats single and compound row ids", () => {
    expect(formatRowId({ id: 1 })).toBe("id=1");
    expect(formatRowId({ year: 2026, code: "a" })).toBe("year=2026, code=a");
  });

  it("formats values including null and objects", () => {
    expect(formatValue(null)).toBe("null");
    expect(formatValue("x")).toBe('"x"');
    expect(formatValue(5)).toBe("5");
    expect(formatValue({ a: 1 })).toBe('{"a":1}');
  });

  it("lists unique columns and error types, sorted", () => {
    expect(uniqueColumns(violations)).toEqual(["age", "name"]);
    expect(uniqueErrorTypes(violations)).toEqual(["minimum", "required", "type"]);
  });
});
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — cannot resolve `./filter`.

- [ ] **Step 4: Write the implementation**

```ts
// frontend/src/types.ts
export interface ViolationRow {
  row_id: Record<string, unknown>;
  column: string | null;
  error_type: string;
  message: string;
  expected: string;
  actual: unknown;
  row?: Record<string, unknown>;
}

export interface ReportData {
  table: string;
  schema_title: string | null;
  generated: string;
  ok: boolean;
  rows_checked: number;
  total_rows: number;
  scan_limited: boolean;
  invalid_rows: number;
  total_violations: number;
  truncated: boolean;
  violations_by_column: Record<string, number>;
  violations_by_type: Record<string, number>;
  table_errors: string[];
  violations: ViolationRow[];
}

export interface FilterState {
  column: string;
  errorType: string;
  search: string;
}

export type SortKey = "row" | "column" | "error_type";
```

```ts
// frontend/src/filter.ts
import type { FilterState, SortKey, ViolationRow } from "./types";

export function formatRowId(rowId: Record<string, unknown>): string {
  return Object.entries(rowId)
    .map(([key, value]) => `${key}=${String(value)}`)
    .join(", ");
}

export function formatValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "null";
  }
  if (typeof value === "string") {
    return JSON.stringify(value);
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

export function filterViolations(violations: ViolationRow[], filter: FilterState): ViolationRow[] {
  const search = filter.search.trim().toLowerCase();
  return violations.filter((violation) => {
    if (filter.column && (violation.column ?? "") !== filter.column) {
      return false;
    }
    if (filter.errorType && violation.error_type !== filter.errorType) {
      return false;
    }
    if (!search) {
      return true;
    }
    const haystack = [
      formatRowId(violation.row_id),
      violation.column ?? "",
      violation.error_type,
      violation.message,
      violation.expected,
      formatValue(violation.actual),
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(search);
  });
}

export function sortViolations(violations: ViolationRow[], key: SortKey, ascending: boolean): ViolationRow[] {
  const direction = ascending ? 1 : -1;
  const value = (violation: ViolationRow): string =>
    key === "row" ? formatRowId(violation.row_id) : key === "column" ? violation.column ?? "" : violation.error_type;
  return [...violations].sort((a, b) => value(a).localeCompare(value(b), "en") * direction);
}

export function uniqueColumns(violations: ViolationRow[]): string[] {
  return [...new Set(violations.map((violation) => violation.column ?? ""))].filter(Boolean).sort();
}

export function uniqueErrorTypes(violations: ViolationRow[]): string[] {
  return [...new Set(violations.map((violation) => violation.error_type))].sort();
}
```

- [ ] **Step 5: Run the tests and the type check**

Run: `cd frontend && npm test && npm run typecheck`
Expected: all tests pass, `tsc --noEmit` silent.

- [ ] **Step 6: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/tsconfig.json \
        frontend/vitest.config.ts frontend/.gitignore frontend/src/types.ts \
        frontend/src/filter.ts frontend/src/filter.test.ts
git commit -m "Add TypeScript report scaffolding and violation filtering logic"
```

---

### Task 4: Report rendering (DOM) and the esbuild bundle

**Files:**
- Create: `frontend/src/render.ts`, `frontend/src/main.ts`, `frontend/src/styles.css`, `frontend/src/css.d.ts`, `frontend/src/report.html`, `frontend/build.mjs`
- Test: `frontend/src/render.test.ts`
- Create (build output, committed): `sqlite_utils/static/validate_report.js`, `sqlite_utils/static/validate_report.css`, `sqlite_utils/static/validate_report.html`

**Interfaces:**
- Consumes: `ReportData`, `ViolationRow`, `FilterState`, `SortKey`, `filterViolations`, `sortViolations`, `uniqueColumns`, `uniqueErrorTypes`, `formatRowId`, `formatValue` from Task 3.
- Produces: `export function renderReport(root: HTMLElement, data: ReportData): void` — mounts the whole report. Build output at `sqlite_utils/static/validate_report.{js,css,html}` consumed by Task 5.

The shell template must contain exactly the placeholders `$TITLE`, `$STYLES`, `$DATA`, `$SCRIPT`.

- [ ] **Step 1: Write the failing test**

```ts
// frontend/src/render.test.ts
import { beforeEach, describe, expect, it } from "vitest";
import { renderReport } from "./render";
import type { ReportData } from "./types";

const data: ReportData = {
  table: "people",
  schema_title: "People",
  generated: "2026-07-31T00:00:00Z",
  ok: false,
  rows_checked: 3,
  total_rows: 3,
  scan_limited: false,
  invalid_rows: 2,
  total_violations: 3,
  truncated: false,
  violations_by_column: { age: 2, name: 1 },
  violations_by_type: { type: 2, minimum: 1 },
  table_errors: [],
  violations: [
    { row_id: { id: 1 }, column: "age", error_type: "type", message: "'x' is not of type 'integer'", expected: "integer", actual: "x" },
    { row_id: { id: 2 }, column: "name", error_type: "type", message: "5 is not of type 'string'", expected: "string", actual: 5 },
    { row_id: { id: 3 }, column: "age", error_type: "minimum", message: "-1 is less than the minimum of 0", expected: "0", actual: -1 },
  ],
};

let root: HTMLElement;

beforeEach(() => {
  document.body.innerHTML = "";
  root = document.createElement("div");
  document.body.appendChild(root);
});

describe("renderReport", () => {
  it("renders a summary with the headline numbers", () => {
    renderReport(root, data);
    const summary = root.querySelector(".summary")!.textContent!;
    expect(summary).toContain("people");
    expect(summary).toContain("3");
    expect(summary).toContain("2");
  });

  it("renders one table row per violation", () => {
    renderReport(root, data);
    expect(root.querySelectorAll("tbody tr.violation")).toHaveLength(3);
  });

  it("filters when a column is selected", () => {
    renderReport(root, data);
    const select = root.querySelector<HTMLSelectElement>("select.filter-column")!;
    select.value = "age";
    select.dispatchEvent(new Event("change"));
    expect(root.querySelectorAll("tbody tr.violation")).toHaveLength(2);
  });

  it("filters when an error type is selected", () => {
    renderReport(root, data);
    const select = root.querySelector<HTMLSelectElement>("select.filter-error-type")!;
    select.value = "minimum";
    select.dispatchEvent(new Event("change"));
    expect(root.querySelectorAll("tbody tr.violation")).toHaveLength(1);
  });

  it("searches as the user types", () => {
    renderReport(root, data);
    const input = root.querySelector<HTMLInputElement>("input.filter-search")!;
    input.value = "minimum";
    input.dispatchEvent(new Event("input"));
    expect(root.querySelectorAll("tbody tr.violation")).toHaveLength(1);
  });

  it("sorts when a column header is clicked", () => {
    renderReport(root, data);
    const header = root.querySelector<HTMLElement>("th[data-sort='column']")!;
    header.dispatchEvent(new Event("click"));
    const columns = [...root.querySelectorAll("tbody tr.violation td.column")].map((td) => td.textContent);
    expect(columns).toEqual(["age", "age", "name"]);
  });

  it("expands a row to show expected and actual", () => {
    renderReport(root, data);
    const first = root.querySelector<HTMLElement>("tbody tr.violation")!;
    first.dispatchEvent(new Event("click"));
    const detail = root.querySelector(".detail")!;
    expect(detail.textContent).toContain("Expected");
    expect(detail.textContent).toContain("integer");
    expect(detail.textContent).toContain("Actual");
  });

  it("shows an empty state when a filter matches nothing", () => {
    renderReport(root, data);
    const input = root.querySelector<HTMLInputElement>("input.filter-search")!;
    input.value = "no-such-thing";
    input.dispatchEvent(new Event("input"));
    expect(root.querySelector(".empty-state")).not.toBeNull();
  });

  it("announces truncation when the detail list was capped", () => {
    renderReport(root, { ...data, truncated: true, total_violations: 5000 });
    expect(root.querySelector(".truncation-note")!.textContent).toContain("5000");
  });

  it("shows table level errors", () => {
    renderReport(root, { ...data, table_errors: ["Column 'name' is required by the schema but does not exist in table 'people'"] });
    expect(root.querySelector(".table-errors")!.textContent).toContain("does not exist");
  });

  it("shows a clean state when there are no violations", () => {
    renderReport(root, { ...data, ok: true, invalid_rows: 0, total_violations: 0, violations: [] });
    expect(root.querySelector(".clean-state")).not.toBeNull();
  });

  it("escapes values rather than injecting HTML", () => {
    renderReport(root, {
      ...data,
      violations: [{ row_id: { id: 1 }, column: "bio", error_type: "type", message: "bad", expected: "string", actual: "<img src=x onerror=alert(1)>" }],
    });
    expect(root.querySelector("img")).toBeNull();
    expect(root.textContent).toContain("<img src=x onerror=alert(1)>");
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — cannot resolve `./render`.

- [ ] **Step 3: Write `frontend/src/render.ts`**

Build everything with `document.createElement` and `textContent` (never `innerHTML` with data — that is what the escaping test guards). Structure:

```ts
import { filterViolations, formatRowId, formatValue, sortViolations, uniqueColumns, uniqueErrorTypes } from "./filter";
import type { FilterState, ReportData, SortKey, ViolationRow } from "./types";

function el<K extends keyof HTMLElementTagNameMap>(tag: K, className?: string, text?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function statTile(label: string, value: string): HTMLElement {
  const tile = el("div", "stat");
  tile.appendChild(el("div", "stat-value", value));
  tile.appendChild(el("div", "stat-label", label));
  return tile;
}

export function renderReport(root: HTMLElement, data: ReportData): void {
  root.textContent = "";
  const state: FilterState = { column: "", errorType: "", search: "" };
  let sortKey: SortKey = "row";
  let ascending = true;

  // Header
  const header = el("header", "report-header");
  header.appendChild(el("h1", undefined, `Validation report: ${data.table}`));
  const subtitle = [data.schema_title, `generated ${data.generated}`].filter(Boolean).join(" · ");
  header.appendChild(el("p", "subtitle", subtitle));
  root.appendChild(header);

  // Summary
  const summary = el("section", "summary");
  summary.appendChild(statTile("Table", data.table));
  summary.appendChild(statTile("Rows checked", String(data.rows_checked)));
  summary.appendChild(statTile("Invalid rows", String(data.invalid_rows)));
  summary.appendChild(statTile("Violations", String(data.total_violations)));
  root.appendChild(summary);

  if (data.scan_limited) {
    root.appendChild(el("p", "scan-note", `Only the first ${data.rows_checked} of ${data.total_rows} rows were checked, so these counts are partial.`));
  }
  if (data.truncated) {
    root.appendChild(el("p", "truncation-note", `Showing the first ${data.violations.length} of ${data.total_violations} violations.`));
  }
  if (data.table_errors.length) {
    const box = el("section", "table-errors");
    box.appendChild(el("h2", undefined, "Table-level problems"));
    const list = el("ul");
    for (const error of data.table_errors) list.appendChild(el("li", undefined, error));
    box.appendChild(list);
    root.appendChild(box);
  }
  if (!data.violations.length && !data.table_errors.length) {
    root.appendChild(el("p", "clean-state", "No violations found. This table matches its schema."));
    return;
  }

  const body = el("tbody");

  const draw = (): void => {
    body.textContent = "";
    const rows = sortViolations(filterViolations(data.violations, state), sortKey, ascending);
    if (!rows.length) {
      const tr = el("tr");
      const td = el("td");
      td.colSpan = 4;
      td.appendChild(el("div", "empty-state", "No violations match these filters."));
      tr.appendChild(td);
      body.appendChild(tr);
      return;
    }
    for (const violation of rows) {
      body.appendChild(buildViolationRow(violation, body));
    }
  };

  root.appendChild(buildFilterBar(data, state, draw));
  root.appendChild(buildTable(body, (key) => {
    if (key === sortKey) {
      ascending = !ascending;
    } else {
      sortKey = key;
      ascending = true;
    }
    draw();
  }));
  draw();
}

function buildFilterBar(data: ReportData, state: FilterState, draw: () => void): HTMLElement {
  const bar = el("section", "filters");

  const columnSelect = el("select", "filter-column");
  columnSelect.appendChild(new Option("All columns", ""));
  for (const column of uniqueColumns(data.violations)) {
    columnSelect.appendChild(new Option(column, column));
  }
  columnSelect.addEventListener("change", () => {
    state.column = columnSelect.value;
    draw();
  });

  const typeSelect = el("select", "filter-error-type");
  typeSelect.appendChild(new Option("All error types", ""));
  for (const errorType of uniqueErrorTypes(data.violations)) {
    typeSelect.appendChild(new Option(errorType, errorType));
  }
  typeSelect.addEventListener("change", () => {
    state.errorType = typeSelect.value;
    draw();
  });

  const search = el("input", "filter-search");
  search.type = "search";
  search.placeholder = "Search violations";
  search.addEventListener("input", () => {
    state.search = search.value;
    draw();
  });

  bar.appendChild(labelled("Column", columnSelect));
  bar.appendChild(labelled("Error type", typeSelect));
  bar.appendChild(labelled("Search", search));
  return bar;
}

function labelled(text: string, control: HTMLElement): HTMLElement {
  const label = el("label");
  label.appendChild(el("span", "filter-label", text));
  label.appendChild(control);
  return label;
}

function buildTable(body: HTMLElement, onSort: (key: SortKey) => void): HTMLElement {
  const table = el("table", "violations");
  const head = el("thead");
  const headRow = el("tr");
  const headers: Array<[string, SortKey | null]> = [
    ["Row", "row"],
    ["Column", "column"],
    ["Error type", "error_type"],
    ["Message", null],
  ];
  for (const [text, key] of headers) {
    const th = el("th", undefined, text);
    if (key) {
      th.dataset.sort = key;
      th.className = "sortable";
      th.addEventListener("click", () => onSort(key));
    }
    headRow.appendChild(th);
  }
  head.appendChild(headRow);
  table.appendChild(head);
  table.appendChild(body);
  return table;
}

function buildViolationRow(violation: ViolationRow, body: HTMLElement): HTMLElement {
  const tr = el("tr", "violation");
  tr.appendChild(el("td", "row-id", formatRowId(violation.row_id)));
  tr.appendChild(el("td", "column", violation.column ?? ""));
  tr.appendChild(el("td", "error-type", violation.error_type));
  tr.appendChild(el("td", "message", violation.message));
  let detailRow: HTMLElement | null = null;
  tr.addEventListener("click", () => {
    if (detailRow) {
      detailRow.remove();
      detailRow = null;
      tr.classList.remove("expanded");
      return;
    }
    detailRow = el("tr", "detail-row");
    const cell = el("td");
    cell.colSpan = 4;
    cell.appendChild(buildDetail(violation));
    detailRow.appendChild(cell);
    body.insertBefore(detailRow, tr.nextSibling);
    tr.classList.add("expanded");
  });
  return tr;
}

function buildDetail(violation: ViolationRow): HTMLElement {
  const detail = el("div", "detail");
  const list = el("dl");
  const pairs: Array<[string, string]> = [
    ["Expected", violation.expected],
    ["Actual", formatValue(violation.actual)],
    ["Message", violation.message],
  ];
  for (const [term, description] of pairs) {
    list.appendChild(el("dt", undefined, term));
    list.appendChild(el("dd", undefined, description));
  }
  detail.appendChild(list);
  if (violation.row) {
    detail.appendChild(el("h3", undefined, "Full row"));
    const rowList = el("dl", "full-row");
    for (const [key, value] of Object.entries(violation.row)) {
      rowList.appendChild(el("dt", undefined, key));
      rowList.appendChild(el("dd", undefined, formatValue(value)));
    }
    detail.appendChild(rowList);
  }
  return detail;
}
```

Note the ordering constraint the tests encode: `renderReport` must append the filter bar and table *after* the early `clean-state` return, and `buildViolationRow` inserts its detail row into `body` directly so that `draw()` rebuilding `body` discards any expanded details.

- [ ] **Step 4: Write `frontend/src/main.ts`**

```ts
import "./styles.css";
import { renderReport } from "./render";
import type { ReportData } from "./types";

function boot(): void {
  const dataNode = document.getElementById("report-data");
  const root = document.getElementById("app");
  if (!dataNode || !root) {
    return;
  }
  const data = JSON.parse(dataNode.textContent || "{}") as ReportData;
  renderReport(root, data);
}

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", boot);
} else {
  boot();
}
```

Add `frontend/src/css.d.ts` containing `declare module "*.css";` so `tsc --noEmit` accepts the CSS import.

- [ ] **Step 5: Write `frontend/src/styles.css`**

A plain stylesheet — system font stack, a light card layout, a sticky table header, monospace for values, and a `@media (prefers-color-scheme: dark)` block. No `@import`, no `url()` pointing anywhere off-file, no web fonts. About 120 lines.

- [ ] **Step 6: Write `frontend/src/report.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$TITLE</title>
<style>$STYLES</style>
</head>
<body>
<div id="app"></div>
<script id="report-data" type="application/json">$DATA</script>
<script>$SCRIPT</script>
</body>
</html>
```

- [ ] **Step 7: Write `frontend/build.mjs`**

```js
import { build } from "esbuild";
import { copyFileSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const outDir = join(here, "..", "sqlite_utils", "static");

mkdirSync(outDir, { recursive: true });

await build({
  entryPoints: [join(here, "src", "main.ts")],
  bundle: true,
  minify: true,
  format: "iife",
  target: ["es2020"],
  outfile: join(outDir, "validate_report.js"),
  legalComments: "none",
});

copyFileSync(join(here, "src", "report.html"), join(outDir, "validate_report.html"));
console.log("Built report bundle into", outDir);
```

esbuild writes the extracted stylesheet next to the JS as `validate_report.css` automatically when the entry point imports a CSS file.

- [ ] **Step 8: Build and verify**

Run: `cd frontend && npm test && npm run typecheck && npm run build`
Then: `ls -la ../sqlite_utils/static/` — expect `validate_report.js`, `validate_report.css`, `validate_report.html`.
Then: `grep -c "http" ../sqlite_utils/static/validate_report.js` — investigate any hit; there must be no network URLs.

- [ ] **Step 9: Commit**

```bash
git add frontend/src frontend/build.mjs sqlite_utils/static
git commit -m "Add TypeScript report renderer and esbuild bundle"
```

---

### Task 5: `sqlite_utils/report.py` — single-file HTML assembly

**Files:**
- Create: `sqlite_utils/report.py`
- Modify: `pyproject.toml` (`[tool.setuptools.package-data]`), `MANIFEST.in`
- Test: `tests/test_validate.py`

**Interfaces:**
- Consumes: `ValidationResult.to_dict()` from Task 1; the three files in `sqlite_utils/static/` from Task 4.
- Produces: `def render_html_report(data: dict[str, Any]) -> str`.

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_validate.py
from sqlite_utils.report import render_html_report


def test_render_html_report_is_self_contained(db):
    db["people"].insert_all([{"id": 1, "name": "Cleo", "age": "x"}], pk="id", columns={"age": str})
    html = render_html_report(validate_table(db["people"], PERSON_SCHEMA).to_dict())
    assert html.startswith("<!DOCTYPE html>")
    assert "http://" not in html
    assert "https://" not in html
    assert "src=" not in html
    assert 'href="' not in html
    assert "$STYLES" not in html
    assert "$SCRIPT" not in html
    assert "$DATA" not in html
    assert "$TITLE" not in html


def test_render_html_report_embeds_the_report_data(db):
    db["people"].insert_all([{"id": 1, "name": "Cleo", "age": "x"}], pk="id", columns={"age": str})
    data = validate_table(db["people"], PERSON_SCHEMA).to_dict()
    html = render_html_report(data)
    start = html.index('<script id="report-data" type="application/json">') + len(
        '<script id="report-data" type="application/json">'
    )
    end = html.index("</script>", start)
    assert json.loads(html[start:end].replace("<\\/", "</")) == data


def test_render_html_report_escapes_script_terminators(db):
    db["people"].insert_all([{"id": 1, "name": "</script><script>alert(1)</script>"}], pk="id")
    schema = {"type": "object", "properties": {"name": {"type": "integer"}}}
    html = render_html_report(
        validate_table(db["people"], schema, include_row=True).to_dict()
    )
    assert "</script><script>alert(1)" not in html
    assert "<\\/script>" in html
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_validate.py -k render -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'sqlite_utils.report'`

- [ ] **Step 3: Write the implementation**

```python
# sqlite_utils/report.py
"""Assemble a self-contained HTML report from a validation result.

The HTML, CSS and JavaScript live in ``sqlite_utils/static/``, built from the
TypeScript sources in ``frontend/``. This module only substitutes values into
the shell template - it never generates markup or script code itself.
"""

from __future__ import annotations

import json
import pathlib
from typing import Any

STATIC_DIR = pathlib.Path(__file__).parent / "static"


def _read(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


def render_html_report(data: dict[str, Any]) -> str:
    """
    Render a validation result dictionary as a single self-contained HTML page.

    :param data: The dictionary returned by ``ValidationResult.to_dict()``
    """
    from string import Template

    template = Template(_read("validate_report.html"))
    payload = json.dumps(data, default=str).replace("</", "<\\/")
    return template.safe_substitute(
        TITLE="Validation report: {}".format(data.get("table", "")),
        STYLES=_read("validate_report.css"),
        SCRIPT=_read("validate_report.js"),
        DATA=payload,
    )
```

Move `from string import Template` to the module's import block rather than inside the function.

- [ ] **Step 4: Make the static files ship with the package**

In `pyproject.toml`:
```toml
[tool.setuptools.package-data]
sqlite_utils = ["py.typed", "static/*"]
```

In `MANIFEST.in` add:
```
recursive-include sqlite_utils/static *
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_validate.py -v`
Expected: PASS.

If `assert 'href="' not in html` fails, the shell template or stylesheet contains a link — remove it; the report must not reference anything outside itself.

- [ ] **Step 6: Check types and formatting**

Run: `uv run mypy sqlite_utils tests && uv run black sqlite_utils tests && uv run flake8`

- [ ] **Step 7: Commit**

```bash
git add sqlite_utils/report.py pyproject.toml MANIFEST.in tests/test_validate.py
git commit -m "Assemble self-contained HTML validation reports"
```

---

### Task 6: The `sqlite-utils validate` CLI command

**Files:**
- Modify: `sqlite_utils/cli.py` (add imports near the existing `from sqlite_utils.db import ...` block; append the command near `analyze_tables`, around line 3019)
- Test: `tests/test_cli_validate.py`

**Interfaces:**
- Consumes: `load_schema`, `validate_table`, `SchemaError` from `sqlite_utils.validate`; `render_html_report` from `sqlite_utils.report`.
- Produces: the `validate` click command. No new Python API.

Options: `--json PATH` (`-` for stdout), `--html PATH`, `--max-violations INT` (default 1000), `--scan-limit INT`, `--coerce`, `--include-row`, `--silent`, plus `@load_extension_option` per repo convention.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_cli_validate.py
import json
import pathlib

import pytest
from click.testing import CliRunner

import sqlite_utils
from sqlite_utils import cli

SCHEMA = {
    "title": "People",
    "type": "object",
    "properties": {
        "id": {"type": "integer"},
        "name": {"type": "string"},
        "age": {"type": "integer", "minimum": 0},
    },
    "required": ["id", "name"],
}


@pytest.fixture
def schema_path(tmpdir):
    path = str(tmpdir / "schema.json")
    with open(path, "w") as fp:
        json.dump(SCHEMA, fp)
    return path


@pytest.fixture
def clean_db(tmpdir):
    path = str(tmpdir / "clean.db")
    db = sqlite_utils.Database(path)
    db["people"].insert_all([{"id": 1, "name": "Cleo", "age": 5}], pk="id")
    db.close()
    return path


@pytest.fixture
def dirty_db(tmpdir):
    path = str(tmpdir / "dirty.db")
    db = sqlite_utils.Database(path)
    db["people"].insert_all(
        [
            {"id": 1, "name": "Cleo", "age": "five"},
            {"id": 2, "name": "Pancakes", "age": "-1"},
        ],
        pk="id",
        columns={"age": str},
    )
    db.close()
    return path


def test_validate_clean_table_exits_zero(clean_db, schema_path):
    result = CliRunner().invoke(cli.cli, ["validate", clean_db, "people", schema_path])
    assert result.exit_code == 0
    assert "No violations" in result.output


def test_validate_dirty_table_exits_one(dirty_db, schema_path):
    result = CliRunner().invoke(cli.cli, ["validate", dirty_db, "people", schema_path])
    assert result.exit_code == 1
    assert "2 violations" in result.output


def test_validate_missing_table_exits_two(clean_db, schema_path):
    result = CliRunner().invoke(cli.cli, ["validate", clean_db, "nope", schema_path])
    assert result.exit_code == 2
    assert "Table 'nope' does not exist" in result.output


def test_validate_invalid_schema_exits_two(clean_db, tmpdir):
    bad = str(tmpdir / "bad.json")
    with open(bad, "w") as fp:
        fp.write("{oops")
    result = CliRunner().invoke(cli.cli, ["validate", clean_db, "people", bad])
    assert result.exit_code == 2
    assert "not valid JSON" in result.output


def test_validate_missing_schema_file_exits_two(clean_db, tmpdir):
    result = CliRunner().invoke(
        cli.cli, ["validate", clean_db, "people", str(tmpdir / "absent.json")]
    )
    assert result.exit_code == 2


def test_validate_empty_table_exits_zero(tmpdir, schema_path):
    path = str(tmpdir / "empty.db")
    db = sqlite_utils.Database(path)
    db["people"].create({"id": int, "name": str, "age": int}, pk="id")
    db.close()
    result = CliRunner().invoke(cli.cli, ["validate", path, "people", schema_path])
    assert result.exit_code == 0


def test_validate_json_report_to_stdout(dirty_db, schema_path):
    result = CliRunner().invoke(
        cli.cli, ["validate", dirty_db, "people", schema_path, "--json", "-", "--silent"]
    )
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["table"] == "people"
    assert data["total_violations"] == 2
    assert data["ok"] is False
    assert {violation["error_type"] for violation in data["violations"]} == {"type"}


def test_validate_json_report_to_file(dirty_db, schema_path, tmpdir):
    out = str(tmpdir / "report.json")
    result = CliRunner().invoke(
        cli.cli, ["validate", dirty_db, "people", schema_path, "--json", out]
    )
    assert result.exit_code == 1
    data = json.loads(pathlib.Path(out).read_text())
    assert data["rows_checked"] == 2


def test_validate_html_report_is_self_contained(dirty_db, schema_path, tmpdir):
    out = str(tmpdir / "report.html")
    result = CliRunner().invoke(
        cli.cli, ["validate", dirty_db, "people", schema_path, "--html", out]
    )
    assert result.exit_code == 1
    html = pathlib.Path(out).read_text()
    assert html.startswith("<!DOCTYPE html>")
    assert "http://" not in html
    assert "https://" not in html
    assert "src=" not in html
    assert 'href="' not in html
    # End-to-end: the expected violations are present in the report payload
    assert "five" in html
    assert "is not of type" in html


def test_validate_silent_suppresses_summary(dirty_db, schema_path):
    result = CliRunner().invoke(
        cli.cli, ["validate", dirty_db, "people", schema_path, "--silent"]
    )
    assert result.exit_code == 1
    assert result.output == ""


def test_validate_coerce_makes_numeric_strings_pass(tmpdir, schema_path):
    path = str(tmpdir / "coerce.db")
    db = sqlite_utils.Database(path)
    db["people"].insert_all([{"id": 1, "name": "Cleo", "age": "5"}], pk="id", columns={"age": str})
    db.close()
    assert CliRunner().invoke(cli.cli, ["validate", path, "people", schema_path]).exit_code == 1
    assert (
        CliRunner()
        .invoke(cli.cli, ["validate", path, "people", schema_path, "--coerce"])
        .exit_code
        == 0
    )


def test_validate_scan_limit_and_max_violations_are_separate(dirty_db, schema_path):
    scan = CliRunner().invoke(
        cli.cli,
        ["validate", dirty_db, "people", schema_path, "--scan-limit", "1", "--json", "-", "--silent"],
    )
    assert json.loads(scan.output)["rows_checked"] == 1
    assert json.loads(scan.output)["scan_limited"] is True

    capped = CliRunner().invoke(
        cli.cli,
        ["validate", dirty_db, "people", schema_path, "--max-violations", "1", "--json", "-", "--silent"],
    )
    payload = json.loads(capped.output)
    assert len(payload["violations"]) == 1
    assert payload["total_violations"] == 2
    assert payload["truncated"] is True
    assert payload["scan_limited"] is False


def test_validate_missing_required_column_is_reported_once(tmpdir, schema_path):
    path = str(tmpdir / "structure.db")
    db = sqlite_utils.Database(path)
    db["people"].insert_all([{"id": i} for i in range(1, 6)], pk="id")
    db.close()
    result = CliRunner().invoke(
        cli.cli, ["validate", path, "people", schema_path, "--json", "-", "--silent"]
    )
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert len(data["table_errors"]) == 1
    assert data["total_violations"] == 0


def test_validate_include_row(dirty_db, schema_path):
    result = CliRunner().invoke(
        cli.cli,
        ["validate", dirty_db, "people", schema_path, "--include-row", "--json", "-", "--silent"],
    )
    assert json.loads(result.output)["violations"][0]["row"]["name"] == "Cleo"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_cli_validate.py -v`
Expected: FAIL — `Error: No such command 'validate'.`

- [ ] **Step 3: Write the implementation**

Add to the imports at the top of `sqlite_utils/cli.py`:
```python
from sqlite_utils.report import render_html_report
from sqlite_utils.validate import SchemaError, load_schema, validate_table
```

Then add the command (place it just before `@cli.command(name="analyze-tables")`):

```python
class ValidateUsageError(click.ClickException):
    """A validate error that should exit with code 2, not click's default 1."""

    exit_code = 2


@cli.command()
@click.argument(
    "path",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False, exists=True),
    required=True,
)
@click.argument("table")
@click.argument(
    "schema",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    required=True,
)
@click.option(
    "json_path",
    "--json",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=True),
    help="Write the JSON report here, or - for standard output",
)
@click.option(
    "html_path",
    "--html",
    type=click.Path(file_okay=True, dir_okay=False, allow_dash=False),
    help="Write a self-contained HTML report here",
)
@click.option(
    "--max-violations",
    type=int,
    default=1000,
    help="Maximum number of violations to record in detail",
)
@click.option(
    "--scan-limit",
    type=int,
    default=None,
    help="Only check the first N rows",
)
@click.option(
    "--coerce",
    is_flag=True,
    default=False,
    help="Interpret string values as the type the schema declares",
)
@click.option(
    "--include-row",
    is_flag=True,
    default=False,
    help="Include the full row in the reports, not just the invalid value",
)
@click.option("--silent", is_flag=True, default=False, help="Do not print a summary")
@load_extension_option
def validate(
    path,
    table,
    schema,
    json_path,
    html_path,
    max_violations,
    scan_limit,
    coerce,
    include_row,
    silent,
    load_extension,
):
    """Validate a table against a JSON Schema

    Exits 0 if the data is clean, 1 if violations were found and 2 on a tool error.

    Example:

    \b
        sqlite-utils validate data.db people schema.json --html report.html
    """
    try:
        loaded_schema = load_schema(schema)
    except SchemaError as ex:
        raise ValidateUsageError(str(ex))
    db = sqlite_utils.Database(path)
    _register_db_for_cleanup(db)
    _load_extensions(db, load_extension)
    if table not in db.table_names():
        raise ValidateUsageError(f"Table '{table}' does not exist")
    result = validate_table(
        db[table],
        loaded_schema,
        max_violations=max_violations,
        scan_limit=scan_limit,
        coerce=coerce,
        include_row=include_row,
    )
    data = result.to_dict()
    if json_path:
        rendered = json.dumps(data, indent=2, default=str)
        if json_path == "-":
            click.echo(rendered)
        else:
            with open(json_path, "w", encoding="utf-8") as fp:
                fp.write(rendered)
    if html_path:
        with open(html_path, "w", encoding="utf-8") as fp:
            fp.write(render_html_report(data))
    if not silent:
        for line in _validate_summary(result):
            click.echo(line, err=False)
    if not result.ok:
        raise click.exceptions.Exit(1)


def _validate_summary(result):
    "Yield the human-readable summary lines for a validation result."
    if result.scan_limited:
        yield "Checked first {} of {} rows in '{}'".format(
            result.rows_checked, result.total_rows, result.table
        )
    else:
        yield "Checked {} rows in '{}'".format(result.rows_checked, result.table)
    for error in result.table_errors:
        yield "Table error: {}".format(error)
    if not result.total_violations:
        if not result.table_errors:
            yield "No violations found"
        return
    yield "{} violations across {} rows".format(
        result.total_violations, result.invalid_rows
    )
    if result.truncated:
        yield "Recorded details for the first {}".format(len(result.violations))
    for column, count in sorted(
        result.violations_by_column.items(), key=lambda item: (-item[1], item[0])
    )[:5]:
        yield "  {}: {}".format(column or "(row)", count)
```

Note on `--json -` plus a summary: the test passes `--silent` when reading JSON from stdout, so the two never interleave. Keep it that way.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_cli_validate.py -v`
Expected: PASS (15 tests).

If `test_validate_dirty_table_exits_one` reports 3 violations instead of 2, check that `age` values `"five"` and `"-1"` each produce exactly one `type` error — `minimum` is not evaluated for a value that already failed `type`.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: no regressions. `tests/test_docs.py::test_commands_are_documented[validate]` WILL FAIL here — that is expected and Task 7 fixes it. Note the failure and continue.

- [ ] **Step 6: Check types and formatting**

Run: `uv run mypy sqlite_utils tests && uv run black sqlite_utils tests && uv run flake8`

- [ ] **Step 7: Commit**

```bash
git add sqlite_utils/cli.py tests/test_cli_validate.py
git commit -m "Add sqlite-utils validate command"
```

---

### Task 7: Documentation

**Files:**
- Modify: `docs/cli.rst` (new section after the `.. _cli_analyze_tables_save:` block, before `.. _cli_create_database:`)
- Modify: `docs/cli-reference.rst` (cog `refs` dict, then regenerate)
- Modify: `docs/python-api.rst` (new section)
- Modify: `docs/reference.rst` (autodoc entries)
- Modify: `docs/contributing.rst` (how to rebuild the report bundle)

**Interfaces:**
- Consumes: the `validate` command from Task 6 and the public objects from Tasks 1, 2 and 5.
- Produces: nothing consumed by later tasks.

- [ ] **Step 1: Verify the docs test currently fails**

Run: `uv run pytest tests/test_docs.py -v`
Expected: FAIL — `test_commands_are_documented[validate]`.

- [ ] **Step 2: Add the `docs/cli.rst` section**

Insert before `.. _cli_create_database:`:

```rst
.. _cli_validate:

Validating data against a JSON Schema
=====================================

The ``sqlite-utils validate`` command checks every row of a table against a `JSON Schema <https://json-schema.org/>`__ and reports the rows that do not match.

.. code-block:: bash

    sqlite-utils validate data.db people schema.json

.. code-block:: output

    Checked 2 rows in 'people'
    2 violations across 2 rows
      age: 2

The command exits with code ``0`` if the data is clean, ``1`` if any violations were found and ``2`` if the tool itself could not run - because the table does not exist, or the schema file is missing or invalid. This makes it safe to use in a script:

.. code-block:: bash

    if ! sqlite-utils validate data.db people schema.json --silent; then
        echo "people needs attention"
    fi

Type checking is strict: a value stored as the text ``"42"`` does not satisfy ``{"type": "integer"}``, which is what makes the command useful for spotting type drift introduced while loading data. Use ``--coerce`` to interpret string values as the type the schema declares instead.

A SQL ``NULL`` is treated as a JSON ``null`` value, so it fails a ``{"type": "string"}`` check. Write ``{"type": ["string", "null"]}`` to allow empty values.

Columns that the schema does not mention are ignored, unless the schema sets ``"additionalProperties": false``. A column named in ``required`` that does not exist in the table at all is reported once as a table-level problem rather than once per row.

.. _cli_validate_reports:

Validation reports
------------------

Use ``--json`` for a machine-readable report and ``--html`` for one you can send to somebody else:

.. code-block:: bash

    sqlite-utils validate data.db people schema.json --json report.json --html report.html

Pass ``--json -`` to write the JSON report to standard output, usually with ``--silent`` so the summary does not interleave with it.

The HTML report is a single self-contained file with no external references - open it in a browser with no network connection and it still works. It lists the violations in a table that can be filtered by column and by error type, searched, and sorted, and each row expands to show what the schema expected and what the data actually contained.

Reports show only the value that failed, truncated. Add ``--include-row`` to include the whole row instead.

.. _cli_validate_large_tables:

Large tables
------------

Every row is checked by default, so the counts are exact, but only the first 1000 violations are recorded in detail. Change that with ``--max-violations``:

.. code-block:: bash

    sqlite-utils validate data.db people schema.json --max-violations 50 --html report.html

To check only part of a table - a quick probe rather than a full pass - use ``--scan-limit``:

.. code-block:: bash

    sqlite-utils validate data.db people schema.json --scan-limit 1000

``--scan-limit`` makes the reported counts partial, and both reports say so. The two options are independent: ``--max-violations`` limits what is recorded, ``--scan-limit`` limits what is read.
```

- [ ] **Step 3: Add `validate` to the cog refs in `docs/cli-reference.rst`**

In the `refs = {` dictionary add `"validate": ["cli_validate", "cli_validate_reports", "cli_validate_large_tables"],`.

- [ ] **Step 4: Regenerate the cog blocks**

Run: `uv run --group docs cog -r README.md docs/*.rst`
Then: `uv run --group docs cog --check README.md docs/*.rst`
Expected: check passes.

- [ ] **Step 5: Add the `docs/python-api.rst` section**

Append a section near the end of the file, following the surrounding style:

```rst
.. _python_api_validate:

Validating a table against a JSON Schema
========================================

The :ref:`sqlite-utils validate <cli_validate>` command is also available from Python:

.. code-block:: python

    from sqlite_utils import Database
    from sqlite_utils.validate import load_schema, validate_table

    db = Database("data.db")
    schema = load_schema("schema.json")
    result = validate_table(db["people"], schema)
    if not result.ok:
        for violation in result.violations:
            print(violation.row_id, violation.column, violation.message)

``load_schema()`` raises ``sqlite_utils.validate.SchemaError`` if the file cannot be read or is not a valid JSON Schema. You can pass a schema dictionary to ``validate_table()`` directly if you have one already.

``validate_table()`` accepts ``max_violations=`` (how many violations to record in detail, defaulting to 1000), ``scan_limit=`` (only check the first N rows), ``coerce=`` and ``include_row=``.

To build the self-contained HTML report:

.. code-block:: python

    from sqlite_utils.report import render_html_report

    open("report.html", "w").write(render_html_report(result.to_dict()))
```

- [ ] **Step 6: Add autodoc entries to `docs/reference.rst`**

Append, following the existing ``sqlite_utils.utils`` pattern:

```rst
sqlite_utils.validate
=====================

.. _reference_validate_validate_table:

sqlite_utils.validate.validate_table
------------------------------------

.. autofunction:: sqlite_utils.validate.validate_table

.. _reference_validate_load_schema:

sqlite_utils.validate.load_schema
---------------------------------

.. autofunction:: sqlite_utils.validate.load_schema

.. _reference_validate_result:

sqlite_utils.validate.ValidationResult
--------------------------------------

.. autoclass:: sqlite_utils.validate.ValidationResult
   :members:

.. _reference_validate_violation:

sqlite_utils.validate.Violation
-------------------------------

.. autoclass:: sqlite_utils.validate.Violation
   :members:

sqlite_utils.report
===================

.. _reference_report_render_html_report:

sqlite_utils.report.render_html_report
--------------------------------------

.. autofunction:: sqlite_utils.report.render_html_report
```

- [ ] **Step 7: Document the frontend build in `docs/contributing.rst`**

Append a section:

```rst
.. _contributing_report_bundle:

Rebuilding the validation report bundle
---------------------------------------

The HTML report produced by :ref:`sqlite-utils validate <cli_validate>` is built from TypeScript sources in the ``frontend/`` directory. The build output in ``sqlite_utils/static/`` is committed to the repository on purpose: it ships as package data, and neither the test suite nor an end user installation has Node.js available.

After changing anything in ``frontend/src/``, rebuild and commit the result:

.. code-block:: bash

    cd frontend
    npm install
    npm test
    npm run typecheck
    npm run build

``npm run build`` writes ``validate_report.js``, ``validate_report.css`` and ``validate_report.html`` into ``sqlite_utils/static/``.
```

- [ ] **Step 8: Verify the docs**

Run: `uv run pytest tests/test_docs.py -v`
Expected: PASS, including `test_commands_are_documented[validate]`.
Run: `uv run --group docs codespell docs/*.rst --ignore-words docs/codespell-ignore-words.txt`
Expected: clean.

- [ ] **Step 9: Commit**

```bash
git add docs
git commit -m "Document the validate command"
```

---

### Task 8: Full verification pass

**Files:**
- Modify: whatever the checks turn up.

**Interfaces:**
- Consumes: everything.
- Produces: a green tree.

- [ ] **Step 1: Full Python test suite**

Run: `uv run pytest -q`
Expected: 1371 pre-existing tests pass (baseline), plus the new `tests/test_validate.py` and `tests/test_cli_validate.py`, 19 skipped.

- [ ] **Step 2: Full lint suite**

Run: `uv run black . --check && uv run flake8 && uv run mypy sqlite_utils tests && uv run --group docs cog --check README.md docs/*.rst`
Expected: all clean. `uv run ty check sqlite_utils` is also in the Justfile — run it and fix anything it reports about the new modules.

- [ ] **Step 3: Frontend checks**

Run: `cd frontend && npm test && npm run typecheck`
Expected: all vitest tests pass, `tsc --noEmit` silent.

- [ ] **Step 4: Confirm the committed bundle matches its sources**

Run: `cd frontend && npm run build && cd .. && git status --short sqlite_utils/static`
Expected: no changes — the committed artifacts are what the sources produce.

- [ ] **Step 5: Manual end-to-end check**

```bash
cd /tmp && rm -f demo.db demo.html
uv run --project <repo> python - <<'EOF'
import sqlite_utils, json
db = sqlite_utils.Database("/tmp/demo.db")
db["people"].insert_all([
    {"id": 1, "name": "Cleo", "age": 5},
    {"id": 2, "name": "Pancakes", "age": "old"},
    {"id": 3, "name": 42, "age": -1},
], pk="id", columns={"age": str})
json.dump({"type": "object", "properties": {"id": {"type": "integer"}, "name": {"type": "string"}, "age": {"type": "integer", "minimum": 0}}, "required": ["id", "name"]}, open("/tmp/demo-schema.json", "w"))
EOF
uv run sqlite-utils validate /tmp/demo.db people /tmp/demo-schema.json --html /tmp/demo.html; echo "exit=$?"
grep -c "http" /tmp/demo.html
```
Expected: exit 1, a summary naming the offending columns, `demo.html` written, no network URLs.

- [ ] **Step 6: Commit any fixes**

```bash
git add -A
git commit -m "Fix issues found during verification"
```
