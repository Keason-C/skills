# Quickstart — validating this feature end-to-end

Runnable checks that prove the feature works. This is the acceptance walkthrough referenced by the
ticket's item 4 ("造脏数据 → validate → 生成 HTML → 断言报告中出现预期违规").

## Prerequisites

```bash
uv sync --group dev          # Python deps
npm --prefix frontend ci     # frontend toolchain (build-time only)
```

## Build the report bundle

```bash
npm --prefix frontend run build
```

Emits the IIFE bundle and CSS into `sqlite_utils/static/`. Committed to the repo, so this is only
needed after changing frontend sources.

## Gate commands

| Gate | Command | Expected |
|---|---|---|
| Existing suite (no regressions) | `uv run pytest` | 1371 passed, 19 skipped — the recorded baseline |
| New Python tests | `uv run pytest tests/test_validate.py tests/test_cli_validate.py` | all pass |
| Types | `uv run mypy sqlite_utils tests` | clean |
| Format | `uv run black . --check` | clean |
| Lint | `uv run flake8` | clean |
| Frontend types | `npm --prefix frontend run typecheck` | clean |
| Frontend tests | `npm --prefix frontend test` | all pass |
| Docs generation | `uv run cog --check README.md docs/*.rst` | clean |

## End-to-end demo

```bash
cd "$(mktemp -d)"

# 1. Dirty data: one clean row, one bad type, one bad enum, one null
cat > rows.csv <<'CSV'
id,age,status
1,30,active
2,abc,active
3,25,banana
4,,active
CSV

sqlite-utils insert demo.db events rows.csv --csv

# 2. A schema.
#
#    IMPORTANT (verified empirically against this repo, not assumed):
#    `insert --csv` DOES apply type detection. Given the CSV above, sqlite-utils
#    creates:  id INTEGER, age TEXT, status TEXT
#    -- `id` types cleanly because every value parses as an integer.
#    -- `age` stays TEXT because row 2 contains "abc".
#    -- the empty cell in row 4 becomes the empty string '', NOT NULL.
#    So strict mode flags exactly the column that failed to type cleanly (`age`),
#    which is a sharper signal than "everything is TEXT so everything fails".
cat > schema.json <<'JSON'
{
  "type": "object",
  "properties": {
    "id":     {"type": "integer"},
    "age":    {"type": "integer"},
    "status": {"type": "string", "enum": ["active", "inactive"]}
  },
  "required": ["id", "age", "status"]
}
JSON

# 3. Validate -- expect exit status 1
sqlite-utils validate demo.db events schema.json ; echo "exit=$?"

# 4. Machine output
sqlite-utils validate demo.db events schema.json --json | python3 -m json.tool

# 5. Human report
sqlite-utils validate demo.db events schema.json --html report.html
```

### Expected

Storage types after import: `id INTEGER`, `age TEXT`, `status TEXT`.

- Step 3 exits **1**.
- `id` — **no violations**. Stored as INTEGER, matches `type: integer` exactly.
- `age` row 1 (`"30"`) → `type-coercible` — text that reads as an integer.
- `age` row 2 (`"abc"`) → `type-invalid` — text that does not.
- `age` row 3 (`"25"`) → `type-coercible`.
- `age` row 4 (`""`) → `type-invalid` — the empty string is a string, not an integer (FR-008e).
- `status` row 3 (`"banana"`) → `enum`.
- **Total: 5 violations across 4 rows.**
- Re-running with `--lenient-types` drops the two `type-coercible` entries, leaving 3.
- `report.html` opens standalone and contains no `http://` or `https://` reference.

The `age` column being the only type-flagged one is the point: it is the column that failed to type
cleanly on import, and strict mode names it.

### Self-containment check

```bash
grep -Eo 'https?://[^"'"'"' )]*' report.html || echo "PASS: no external references"
```

## Exit-status semantics

```bash
sqlite-utils validate demo.db events schema.json  >/dev/null 2>&1; echo "dirty      -> $?"   # 1
sqlite-utils validate demo.db nosuchtable schema.json >/dev/null 2>&1; echo "no table   -> $?"   # 2
echo '{"type":"object","properties":{"a":{"allOf":[]}}}' > bad.json
sqlite-utils validate demo.db events bad.json >/dev/null 2>&1; echo "bad schema -> $?"   # 2
```

The third case is the one that matters most: `allOf` is *unsupported*, and the tool must refuse
(exit 2) rather than validate while ignoring it. A pass produced by skipping a constraint is a false
assurance — see FR-002b.
