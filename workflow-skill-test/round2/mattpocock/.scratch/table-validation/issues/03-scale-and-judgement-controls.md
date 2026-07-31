# 03 — Controls for scale and for judgement calls

**What to build:** the knobs that make validation usable on a million-row table
and on data whose types have drifted.

Counts stay exact — the table is scanned in full — while the itemised list of
violations stops at a **detail cap**, and the result says how many it is showing
out of how many there were. A **scan limit** shortens the scan itself for a fast
probe, and the result records that it did. Wrong-but-convertible values
(`"123"` in a TEXT column against `"type": "integer"`) get their own violation
kind so type drift can be filtered apart from real garbage, and can be accepted
outright with an explicit opt-in.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] A value of the wrong type whose text would parse as the expected type is the `type-coercible` kind, not `type`
- [ ] With coercion enabled, such values pass, and later constraints are checked against the converted value
- [ ] With the empty-string option on, `''` behaves as JSON `null`; off (the default), `''` is an ordinary string
- [ ] The detail cap bounds retained violations without distorting the counts, and the result exposes both numbers
- [ ] The scan limit reads only the first N rows, and the result reports rows scanned separately from the table's total
- [ ] Violation values are truncated for display; whole rows are included only on explicit request
