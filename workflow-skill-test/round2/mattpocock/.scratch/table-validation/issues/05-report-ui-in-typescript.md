# 05 — The report UI, in TypeScript

**What to build:** the interactive part of the **HTML report**, as a typed,
built, unit-tested frontend (ADR-0003) — never a template string in Python.
Given a validation result it renders a header (table, database, schema file,
timestamp, totals, counts by column and by kind, and the "showing N of M" notice
when capped) and a violations table that can be filtered by column, filtered by
violation kind, searched free-text, sorted, and expanded row by row to show
expected versus actual.

**Blocked by:** 04 (the JSON report is the contract this renders)

**Status:** ready-for-agent

- [ ] Data in, DOM out: an exported function renders a validation result into a container element
- [ ] Filtering by column, filtering by violation kind, free-text search and sorting all work, and compose with each other
- [ ] Expanding a violation reveals expected versus actual
- [ ] The capped notice appears when, and only when, violations were capped
- [ ] An empty violation list renders a clean "no violations" state rather than an empty table
- [ ] Tested with vitest against a real DOM, exercising the rendered output — not internals
- [ ] `tsc --noEmit` is clean
- [ ] `npm run build` produces one self-contained bundle, committed and shipped as package data
