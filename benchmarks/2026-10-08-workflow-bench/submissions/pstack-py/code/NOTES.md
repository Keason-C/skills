# gridcalc notes

## Design

The engine has seven private modules behind the fixed public API in `gridcalc/__init__.py`.

| Module | Owns |
|---|---|
| `_errors.py` | `CellError` and the shared error constants. |
| `_grid.py` | Grid limits, column letters, and parsing of API addresses and blocks. |
| `_values.py` | The value model (`None`, `float`, `str`, `bool`, `CellError`), coercions, operators, and comparison. |
| `_functions.py` | The function registry. Each entry has an arity and an implementation that receives unevaluated argument nodes. |
| `_formula.py` | Tokenizer, parser, AST nodes, and reference rewriting. |
| `_index.py` | `RangeIndex`, a reverse index from a cell to the formulas whose ranges contain it. |
| `_sheet.py` | `Sheet`: cell storage, dependency edges, recalculation, structural edits, and copy. |

**Cells.** `Sheet._cells` maps `(row, col)` to the raw text plus its compiled form, which is a literal value or a `Formula` (tokens, AST, single refs, ranges). `Sheet._values` holds the computed value of every populated cell. Compilation is cached by formula text.

**Dependencies.** Single references go in a dict from the referenced cell to the set of its dependents. Ranges go in `RangeIndex`, which buckets each range into 64-row by 16-column tiles. A range that would span more than 256 tiles goes in a list that every lookup scans. Identical rectangles share one entry, so many formulas summing the same whole column cost one check per lookup.

**Recalculation.** `set` and `copy` update the edges, then run an iterative Tarjan SCC pass over the dependents graph, starting from the edited cells. The pass visits only cells that transitively depend on the edit. Its components, reversed, give a topological evaluation order. A component with more than one cell, or one cell that references itself, gets `#CYCLE!`. Every other cell is evaluated once, after its precedents. Cells downstream of a cycle see `#CYCLE!` as an ordinary propagated error, so `IFERROR` can catch it. Nothing recurses per dependency, so chains of any length work.

**Formula text.** The tokenizer never raises: unknown characters and unterminated strings become `bad` tokens. That lets structural edits and copy rewrite reference tokens in any formula, including one that does not parse. Rewriting splices only the reference tokens whose target changed. Every other byte, including the original spelling of unchanged references, is kept.

**Structural edits** move every cell, rewrite every formula, rebuild the indexes, and recalculate the whole sheet. Measured on this machine, that takes about 1 to 1.4 seconds for a 50,000-cell sheet. Incremental structural edits were not worth the complexity for this brief.

**Recursion.** Long flat formulas (`A1+A2+...`) evaluate left operands in a loop. Parenthesis and function nesting recurse, so `set`, `copy` and structural edits raise the interpreter recursion limit to 20,000 for the duration of the call and then restore it. Nesting 1,000 levels deep works.

## Behaviour decisions

The product owner settled these open questions. The verbatim exchange is in `docs/product-owner-qa.md`, and `tests/test_decisions.py` pins each answer.

1. A formula that is a bare reference to an empty cell (`=A1`) gives `0.0`. Inside an expression, the empty value is kept, so `=A1&""` gives `""`.
2. A bare cell reference passed to `SUM`, `AVERAGE`, `MIN`, `MAX`, `COUNT`, `AND` or `OR` acts as a 1-cell range. Text, booleans and empty cells are skipped, and errors propagate.
3. Comparisons follow Excel. Text compares case-insensitively. Mixed types order number < text < boolean. An empty cell acts as `0`, `""` or `FALSE`, matching the other operand. Text is never coerced to a number, so `"1"=1` is `FALSE`.
4. Numbers convert to text with `format(x, ".15g")`: `1` gives `"1"`, `0.1+0.2` gives `"0.3"`, `1E20` gives `"1e+20"`, and negative zero gives `"0"`.
5. `0^negative` is `#DIV/0!`. `0^0` is `1`. Overflow and non-real results, such as `(-8)^(1/3)`, are `#VALUE!`.
6. A known function called with the wrong number of arguments is `#VALUE!`. An unknown name is `#NAME?`, checked first.
7. A bare identifier that is not a valid in-grid reference (`=foo`, `=XFE1`, `=A0`) is `#NAME?`.
8. Literal booleans are recognized after stripping surrounding whitespace, as numbers are.
9. `insert_*` and `delete_*` raise `ValueError` when `at < 1`, when `at` is beyond the grid, when `count < 1`, or when a delete runs past the grid edge.
10. `copy` raises `ValueError` and changes nothing when the destination block would leave the grid. `dst` must be a single address.
11. API addresses are strict. `"A01"`, `" A1"` and `"$A$1"` raise `ValueError`.
12. When inserted rows or columns push a range's far end off the grid, the end is clamped to the grid edge. The range becomes `#REF!` only when its first row or column would leave the grid.

I made these smaller choices without asking.

- A formula that fails to parse has no dependencies, so it is never part of a cycle. Its reference tokens are still rewritten by structural edits and copy.
- Error literals such as `#REF!` and `#DIV/0!` are accepted in formula text, in any case. Rewritten formulas contain `#REF!`, so they must parse.
- A rewritten range is written top-left first. Each `$` marker travels with its coordinate, so `B$3:$A1` becomes `$A2:B$4`. A range that is not rewritten keeps its original spelling.
- In formula text, a reference whose row has a leading zero (`A01`) is not a valid reference, so it is `#NAME?`. This matches decision 11.
- A range with an off-grid endpoint (`A1:XFE1`) is `#PARSE!`, because the `:` is left dangling.
- Unary `+` coerces to a number, so `=+"abc"` is `#VALUE!`. Excel would return `"abc"`.
- `ROUND` rounds half away from zero on the shortest decimal form of the number, so `ROUND(2.675, 2)` is `2.68`.
- A number literal that overflows a float (`1e400`) is text when typed as a cell value and `#VALUE!` inside a formula.
- Non-ASCII digits in formula text are `#PARSE!`.
- `AND` and `OR` with nothing to evaluate are `#VALUE!`, as in Excel.

## Tests

`python3 -m pytest` runs both suites.

- `tests/test_brief.py` is a black-box suite. A separate agent wrote it from `BRIEF.md` alone, without reading the implementation. It covers every rule in the brief, including the timing scenarios.
- `tests/test_decisions.py` covers the decisions above and engine edge cases: reference rewriting, recursion depth, huge ranges, and cycles that the edit does not reach.

## Known limits

`python3 tools/bench.py` times the main operations on a 50,000-cell sheet and a 50,000-cell chain.


- A formula that sums a range is re-evaluated by reading every populated cell in the range. On this machine that costs about 0.2 µs per cell: re-summing 20,000 cells takes 4 ms. A sheet of prefix sums (`B_i = SUM(A$1:A_i)`) is therefore quadratic to build and to edit.
- Each structural edit recomputes the whole sheet.
