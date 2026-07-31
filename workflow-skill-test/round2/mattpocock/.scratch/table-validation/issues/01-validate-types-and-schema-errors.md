# 01 — Validate a table's values against the row schema's `type`

**What to build:** `db["mytable"].validate(schema)` answers "does every value in
this table have the type my row schema says it should?" and hands back a
**validation result**: how many rows were scanned, how many violations there
were, the violations themselves (each naming the row's key, the column, the
violation kind, what was expected and what was actually there), counts by column
and by violation kind, and whether the run was clean.

A **schema error** — the document is not an object schema, or uses a keyword this
tool cannot evaluate — is raised before the table is touched, naming the offending
keyword. Never partially validate.

**Blocked by:** None — can start immediately.

**Status:** ready-for-agent

- [ ] `Table.validate(schema)` returns a validation result; `.ok` is true only when there is nothing wrong
- [ ] A value whose SQLite type contradicts the schema's `type` produces a `type` violation carrying expected and actual
- [ ] `type` accepts a union list, so `["string", "null"]` admits both
- [ ] **Present-as-null**: a SQL `NULL` is JSON `null` — it never fails `required`, and it fails `type` exactly when the schema does not admit null
- [ ] SQLite's storage classes map sanely: a `bool` is not an `integer`, `boolean` also accepts 0/1, a BLOB satisfies no JSON Schema type
- [ ] Each violation identifies its row by primary key, or by `rowid` when the table has no primary key
- [ ] An empty table validates clean
- [ ] A schema that is not valid, is not an object schema, or uses an unsupported keyword raises a schema error naming the keyword — before any row is read
- [ ] Annotation keywords (`$schema`, `title`, `description`, …) are accepted and ignored
- [ ] New code is fully type-annotated and clean under the repo's mypy config
