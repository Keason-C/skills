# gridcalc hidden acceptance suite (Python)

Plain pytest, no plugins. Each test builds its own `Sheet()`; there is no shared state.
The package under test must be importable as `gridcalc` (put it on `PYTHONPATH`).

    PYTHONPATH=/path/to/impl python3 -m pytest /path/to/tests

Expected values were derived by hand from `BRIEF.md` and `clarifications.md`.
`test_po.py` holds ONLY tests whose expectation depends on a product-owner decision that the
brief leaves open; every other file tests brief-determined behaviour only (so formulas there use
upper case, no whitespace between tokens, no number-to-text conversion, no text-to-number
coercion, and IF/AND/OR/NOT conditions are booleans or comparisons).

| file | category | test functions | collected items (incl. parametrize) |
|---|---|---|---|
| test_literals.py | literal input parsing, formula literals, string escapes, get() types | 35 | 52 |
| test_operators.py | precedence, associativity, unary minus vs `^`, `&`, comparisons, arithmetic coercion | 39 | 47 |
| test_functions.py | SUM/AVERAGE/MIN/MAX/COUNT/IF/AND/OR/NOT/IFERROR/ROUND/ABS/LEN/CONCAT | 61 | 67 |
| test_errors.py | error production, propagation, leftmost error, `#NAME?`, `#PARSE!`, range-as-scalar | 26 | 41 |
| test_cycles.py | static cycle detection, propagation to dependents, breaking cycles | 20 | 20 |
| test_recalc.py | set() return lists, value-change rules, dependency tracking, API addresses | 28 | 42 |
| test_structural.py | insert/delete rows/cols, `$`, `#REF!`, range shrink/grow rules, raw text preservation, grid edge | 47 | 47 |
| test_copy.py | relative/absolute refs, `#REF!` off-grid, blocks, overlap, clearing, return value | 26 | 26 |
| test_perf.py | 50k chain, 50k-cell sheet + 3000 unrelated edits, fan-out edits, depth-200 nesting, 20k cycle | 7 | 7 |
| test_po.py | product-owner decisions 1–12 | 48 | 114 |
| **total** | | **337** | **463** |

Perf limits are generous (60 s to build 50k cells, 10 s for 3000 unrelated / 2000 small
edits, 15–20 s for propagating through a 50k chain / 20k cycle) and fail fast via a
deadline check inside the loops, so a whole-sheet-recalc-per-edit engine fails within the
limit instead of running for hours.
