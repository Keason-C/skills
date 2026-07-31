# Research: can `sqlite-utils` take a runtime dependency on `jsonschema`?

Run for ticket #4821, which requires JSON Schema as the constraint language while
also demanding "be sparing with new runtime dependencies — justify each one".

Run **serially** rather than as a background agent (single-agent adaptation).

## Question

If we validate rows with the reference Python implementation
([`jsonschema`](https://pypi.org/project/jsonschema/)), what does that cost the
project's install story?

## Findings

### 1. `sqlite-utils` today has zero compiled dependencies

From `pyproject.toml` (`[project].dependencies`): `click`, `click-default-group`,
`pluggy`, `python-dateutil`, `sqlite-fts4`, `tabulate`, `pip`. Every one of these
ships as a pure-Python `py3-none-any` wheel. `pip install sqlite-utils` therefore
works on any platform with a Python interpreter, with no toolchain.

### 2. `jsonschema` would break that property

PyPI metadata for `jsonschema` 4.26.0 (`https://pypi.org/pypi/jsonschema/json`,
`info.requires_dist`), core (non-`extra`) requirements:

```
attrs>=22.2.0
jsonschema-specifications>=2023.03.6
referencing>=0.28.4
rpds-py>=0.25.0
```

Of these, `attrs`, `referencing` and `jsonschema-specifications` are pure-Python
(their latest releases publish exactly one `…-py3-none-any.whl` plus an sdist).

**`rpds-py` is not.** Its current release publishes 116 files — per-platform,
per-interpreter binary wheels (`manylinux_2_17_{x86_64,aarch64,armv7l,ppc64le,s390x}`,
`macosx_*`, `win_*`, musllinux, …). It is a Rust extension module (bindings to the
`rpds` crate). On any platform/interpreter combination without a prebuilt wheel,
installation requires a Rust toolchain.

So the transitive cost of `jsonschema` is: **4 new packages, one of which is a
compiled Rust extension**, added to a tool whose selling point includes being
trivially installable ("CLI tool and Python library for manipulating SQLite
databases", installed by data people onto random machines).

### 3. What surface of JSON Schema does #4821 actually need?

The ticket's use case is "describe what a table's rows should look like": a
schema whose top level is `{"type": "object", "properties": {…}, "required": […]}`
where each property describes one **column**. Column-level constraints in play
for CSV/API-export cleanup are the primitive keyword set:

- `type` (`string`/`integer`/`number`/`boolean`/`null`, and unions thereof)
- `required`
- `enum`, `const`
- `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf`
- `minLength`, `maxLength`, `pattern`
- `format` (a few well-known ones)
- `additionalProperties` (as a boolean, to catch unexpected columns)

Not in play: `$ref`/`$defs` resolution across documents, `allOf`/`anyOf`/`oneOf`
composition over nested objects, `items`/array validation of nested structures,
remote schema retrieval. A row is a flat map of column → scalar; SQLite has no
nested values (JSON is stored as TEXT).

### 4. Precedent inside the project

`sqlite-utils` already hand-rolls domain logic rather than pulling dependencies
where the needed subset is small — e.g. `utils.py` implements its own CSV type
sniffing (`sqlite_utils/utils.py: TypeTracker`, `rows_from_file`, `Format`)
instead of depending on a schema-inference library, and `recipes.py` wraps
`python-dateutil` narrowly rather than exposing it.

## Conclusion / recommendation

**Implement the flat-row subset of JSON Schema Draft 2020-12 in-repo; add no
runtime dependency.** Keep the *language* JSON Schema (as the ticket demands —
schemas stay valid JSON Schema documents, readable by any other JSON Schema
tool), but validate with ~300 lines of typed Python instead of importing a Rust
extension tree.

Guard rails that make this honest rather than a silent downgrade:

- **Reject, don't ignore, unsupported keywords.** If a schema uses `$ref`,
  `allOf`, `items`, etc., fail loudly with "not supported by
  `sqlite-utils validate`" rather than silently passing rows that the reference
  implementation would have failed. Silent partial validation is the dangerous
  failure mode.
- Document the supported keyword list in the user docs.

## Sources

- `https://pypi.org/pypi/jsonschema/json` — `info.requires_dist`, retrieved for 4.26.0
- `https://pypi.org/pypi/rpds-py/json` — release file list for 2026.6.3 (116 platform wheels)
- `https://pypi.org/pypi/attrs/json`, `.../referencing/json`, `.../jsonschema-specifications/json` — one `any.whl` each
- JSON Schema Draft 2020-12 validation vocabulary: `https://json-schema.org/draft/2020-12/json-schema-validation`
- This repo: `pyproject.toml`, `sqlite_utils/utils.py`, `sqlite_utils/recipes.py`
