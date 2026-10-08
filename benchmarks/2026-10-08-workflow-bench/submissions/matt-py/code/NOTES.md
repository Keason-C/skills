# gridcalc — design notes

## Layout

| module | role |
|---|---|
| `gridcalc/__init__.py` | public API: `CellError` (defined here, unchanged) and `Sheet` (re-exported) |
| `_address.py` | A1 addresses ⇄ `(row, col)`; grid bounds |
| `_values.py` | literal parsing, coercions (`to_number`/`to_text`/`to_bool`), comparison, number→text |
| `_formula.py` | tokenizer → shunting-yard parser → AST → flat code list with jumps |
| `_evaluator.py` | stack VM that runs the code, and the built-in functions |
| `_rewrite.py` | rewriting reference tokens in formula text for structural edits and copy |
| `_sheet.py` | `Sheet`: storage, dependency index, incremental recalculation, structural edits, copy |

### No recursion anywhere
Parsing is shunting-yard and compilation uses an explicit stack. Evaluation is a
flat loop over the compiled code: `IF`/`IFERROR` compile to conditional jumps, so
only the branch that is taken runs. Recalculation order comes from an iterative
Tarjan SCC pass. Deep nesting (tested to 1000 levels) and dependency chains of
tens of thousands of cells cannot raise `RecursionError`.

### Dependencies and recalculation
* A formula's static dependencies are its single references plus its ranges,
  taken from the parsed text. Out-of-grid references and error literals are not dependencies.
* Reverse index: `cell -> formulas` for single references, plus a
  multi-resolution bucket index for ranges. Row and column resolution are
  chosen independently: each range uses the finest resolution at which it
  spans at most 4 buckets on that axis. A lookup checks one bucket for each
  resolution pair that is in use. Inserting a value into a cell covered by
  `SUM(A1:A100000)` is found without expanding the range, and tall ranges in
  one column never slow down lookups in the next column.
* `set` stores the cell, settles literal seeds directly, then collects the
  formulas that transitively depend on the seeds. Only formula cells take part
  in the SCC ordering, which avoids the O(n²) literal→formula edges of running
  sums. Components are evaluated in topological order. Every member of a
  non-trivial SCC, or of a self-loop, becomes `#CYCLE!`. Cells downstream of a
  cycle evaluate normally and see the error.
* The changed list is computed by comparing each touched cell's value before
  and after (same type and equal).

### Structural edits
Cells move together with their values. A formula is rewritten (re-tokenised and
recompiled) only if one of its tracked references or ranges is affected by the
edit, or if its text did not parse. The recalculation is seeded with the
rewritten formulas plus the dependents of removed cells. Any change in what a
formula points at shows up as a change in its text, so nothing else can go
stale. Inserting rows in the middle of a 50k-cell sheet takes about 0.7 s.
Inserting at row 1, where every formula shifts, takes about 2.5 s.

## Behaviour decisions (confirmed with the product owner)

**Literals / addresses**
* `"5."` is a number. Surrounding whitespace is stripped for numbers *and* booleans (`" TRUE "` → `True`). The raw text is kept unchanged.
* A literal that overflows a float (`"1e400"`) is text.
* API addresses: leading zeros are allowed (`"A01"` = A1). Rows that are 0, surrounding whitespace, and `$` markers raise `ValueError` in `get`/`set`/`get_raw`.
* `copy` arguments: `$` markers are ignored, case does not matter, and a reversed source range is normalised. `dst` must be a single address. If the destination block would extend past the grid, `ValueError` is raised and nothing changes.
* Structural edit arguments: `at < 1`, `at` beyond the grid or `count < 1` raise `ValueError` and leave the sheet unchanged.

**Formula language**
* Function names and references are case-insensitive. Whitespace is allowed between tokens, including around a range's `:`.
* Error literals (`#DIV/0!`, `#REF!`, …) are valid operands. Any other `#…` is `#PARSE!`.
* An unknown function gives `#NAME?`. This check comes before the arity check, and the arguments are not evaluated. A bare identifier (`=foo`) gives `#NAME?`. A wrong argument count gives `#VALUE!`.
* A reference outside the grid (`=XFE1`, `=A0`, `=A1048577`, including as a range endpoint) gives `#REF!`. Its text is kept.
* A non-finite number (`=1e400`, overflow, `(-8)^0.5`) gives `#VALUE!`. `0^-1` gives `#DIV/0!`.
* Unary `+` coerces like unary `-` (`=+"abc"` → `#VALUE!`).
* A range is never a scalar, even a 1-cell one (`=A1:A1+1` → `#VALUE!`). A formula whose result is empty evaluates to `0.0`.
* Leftmost error: operands are coerced left to right, and a coercion failure is that operand's error. So `="x"+(1/0)` → `#VALUE!`, and `=(1/0)+"x"` → `#DIV/0!`. `SUM` and the other functions do the same across their arguments.
* Number → text uses `format(x, ".15g")` (`1/3` → `0.333333333333333`, `1e20` → `1e+20`, `-0` → `0`).
* Comparisons: text is compared case-insensitively. Mixed types order as numbers < text < booleans, and text is never converted to a number. An empty operand takes the other side's type (`0`, `""`, `FALSE`).
* Text → number: text that parses under the literal-number rules, including whitespace, is converted. `""` and `"TRUE"` give `#VALUE!`.
* Conditions (`IF`/`AND`/`OR`/`NOT`): numbers are true when nonzero, empty is FALSE, and text `"TRUE"`/`"FALSE"` (any case, trimmed) is that boolean. Other text gives `#VALUE!`. A range in a condition gives `#VALUE!`.
* `SUM/AVERAGE/MIN/MAX/COUNT`: a single reference argument is treated like a 1-cell range. `COUNT` counts scalar arguments that can be converted to a number (`"3"`, `TRUE`). Errors propagate, including through `COUNT`.
* `AND/OR`: in ranges, numbers and booleans count and text/empty cells are skipped. A scalar empty reference counts as FALSE. With nothing to evaluate the result is `#VALUE!`.
* `ROUND` rounds half away from zero using decimal arithmetic on `repr(x)`. Digits are truncated toward zero, and negative digits are allowed.
* `IFERROR(range, x)` → `x`, because the range in scalar position is `#VALUE!`. `ABS`, `LEN`, `ROUND` and `NOT` given a range return `#VALUE!`.

**Rewriting (structural edits / copy)**
* Only reference tokens whose target changes are rewritten, in canonical upper case. Every other byte of the text is preserved, including lower case and the whitespace around `:`.
* A rewritten reversed range is emitted normalised (top-left first), and each `$` stays with its row or column part.
* Insert: if only a range's end would leave the grid it is clamped to the last row or column (cells pushed off are dropped). The range becomes `#REF!` only if its start would leave the grid too.
* Formulas that fail to parse still have their reference tokens rewritten. The rewriter skips characters it cannot tokenise, so references after them are still found.

## Tests
`python3 -m pytest` runs the tests in `tests/`, grouped by feature: literals, formulas, recalculation and cycles (including timing and long-chain tests), structural edits, and copy.
