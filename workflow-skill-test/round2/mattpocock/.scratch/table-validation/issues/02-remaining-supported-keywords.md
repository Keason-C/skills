# 02 — The rest of the supported keyword set

**What to build:** the row schema can constrain more than type. `enum`,
`minimum`, `maximum`, `minLength`, `maxLength` and `pattern` are evaluated per
column, and `additionalProperties: false` reports columns the schema never
mentioned. A schema that names a column the table does not have is reported once
for the run as a **schema/table mismatch** — the typo-catcher, and the only way
`required` can fail.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] `enum` produces an `enum` violation listing the permitted values
- [ ] `minimum` / `maximum` produce their own violation kinds, and apply only to numeric values
- [ ] `minLength` / `maxLength` / `pattern` produce their own violation kinds, and apply only to strings
- [ ] `pattern` uses unanchored regex search, per JSON Schema
- [ ] Columns not mentioned in the schema are ignored by default, and produce an `additionalProperties` violation only when the schema sets `additionalProperties: false`
- [ ] A column named in `properties` or `required` but absent from the table is a schema/table mismatch, reported once, and makes the result not ok
- [ ] Iris's locked keyword list all works: `type`, `properties`, `required`, `enum`, `minimum`, `maximum`, `minLength`, `maxLength`, `pattern`, `additionalProperties`
