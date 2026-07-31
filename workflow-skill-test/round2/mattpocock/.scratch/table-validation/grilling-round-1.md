# Grilling round 1 — questions for Iris (product/business only)

Ticket #4821. Technical decisions are not here; they are settled by me and
recorded in `.scratch/table-validation/decisions.md` / `docs/adr/`.

Facts I looked up rather than asking (per `/grilling`): CLI command shape,
`analyze-tables` as the nearest analogue, docs/test/cog conventions, the
dependency footprint of `jsonschema` (see `research/jsonschema-dependency.md`).

1. **Does a TEXT `"123"` satisfy `"type": "integer"`?**
   Recommend: **no — strict**. Report it as its own error kind so you can filter
   "wrong type, but coercible" apart from "genuinely garbage".

2. **Is `''` (empty string) the same as missing?**
   Recommend: **no by default** — `''` is a valid string, `NULL` is missing;
   plus an opt-in flag to treat `''` as missing.

3. **What of a bad row goes into the report** (it gets forwarded to ops)?
   Recommend: **primary key (or `rowid`) + the offending column's value only**,
   with an opt-in flag for whole rows.

4. **Full scan for exact counts, or capped scan?**
   Recommend: **always full scan** (exact counts), cap only how many violation
   *details* are kept — default 1000, `--limit` to change, report states
   "showing 1,000 of 48,213".

5. **Cross-row constraints (uniqueness, row counts) in v1?**
   Recommend: **no** — JSON Schema has no vocabulary for them, and inventing one
   is exactly what you told us not to do. Per-row only, plus a table-level error
   when the schema names a column the table doesn't have.

6. **Columns present in the table but absent from the schema.**
   Recommend: **silent unless the schema says `"additionalProperties": false`** —
   i.e. plain JSON Schema semantics, no special-casing.

7. **One table per run, or many?**
   Recommend: **one table per run**; the schema file describes one table's rows.

8. **What must / must not appear in the HTML report?**
   Recommend: table name, row and violation counts, generation timestamp, schema
   file *basename*. No absolute filesystem paths.

9. **Pipeline gating: any violation = failure?**
   Recommend: **yes** — non-zero exit on any violation; no percentage threshold.
