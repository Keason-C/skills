# gridcalc: an in-memory spreadsheet engine (Python)

Build `gridcalc`, a pure-Python (3.13, standard library only) spreadsheet calculation engine.
There is no UI and no persistence: it is a library. Its public API is fixed (see
`gridcalc/__init__.py`, which already contains the signatures and the `CellError` class you
must keep). An automated acceptance suite you cannot see will import `gridcalc` and exercise
the API below, so keep the names, signatures and return types exactly as specified.

You may add any modules, private helpers and tests you like. `pytest` is installed.

## Addresses and the grid

- A cell address is a column letter group followed by a row number: `A1`, `Z99`, `AA10`,
  `XFD1048576`. Column letters are bijective base-26 (`A`=1 … `Z`=26, `AA`=27 …).
- The grid is 16384 columns (`A`..`XFD`) by 1048576 rows.
- API methods accept addresses case-insensitively (`"b3"` == `"B3"`). Addresses that are
  malformed or outside the grid raise `ValueError`.
- Returned addresses are always upper-case canonical (`"B3"`).

## API

```python
sheet = Sheet()
changed = sheet.set("A1", "42")     # -> list[str]
sheet.get("A1")                     # -> computed value
sheet.get_raw("A1")                 # -> str
sheet.insert_rows(at, count=1); sheet.delete_rows(at, count=1)
sheet.insert_cols(at, count=1); sheet.delete_cols(at, count=1)
sheet.copy("A1:B2", "D5")           # -> list[str]
```

### `set(addr, raw) -> list[str]`

Stores the raw input string for a cell and recalculates.

- `""` (empty string) clears the cell.
- A string starting with `=` is a formula.
- Otherwise the raw string is a literal:
  - a leading apostrophe forces text: `'123` is the text `"123"` (apostrophe removed);
  - after stripping surrounding whitespace, text matching an optional sign, digits with an
    optional decimal part (or a leading-dot decimal like `.5`), and an optional exponent
    (`1e3`, `-2.5E-2`) is a number;
  - `TRUE` / `FALSE` (any case) are booleans;
  - anything else is text, stored exactly as given (no stripping).
- Returns the addresses of **every cell whose computed value changed** as a result of this
  call (including `addr` itself if its value changed), sorted by row then column, without
  duplicates. A cell whose raw content changed but whose value is equal to its previous value
  is not reported. Values are equal if they have the same type and are equal (`1.0` vs `True`
  are different; two errors with the same code are equal).

### `get(addr)`

Returns the computed value:

| kind     | Python type                         |
|----------|-------------------------------------|
| empty    | `None`                              |
| number   | `float` (always float, never int)   |
| text     | `str`                               |
| boolean  | `bool`                              |
| error    | `CellError` (has `.code`)           |

### `get_raw(addr) -> str`

The raw string as stored (`""` for an empty cell). A formula's text is returned exactly as
entered, except that structural edits and copies rewrite the reference tokens inside it (see
below). Everything outside a rewritten reference token is preserved byte for byte.

## Formula language

- Literals: numbers (`3`, `2.5`, `.5`, `1e3`), strings in double quotes with `""` as an
  escaped quote (`"say ""hi"""`), `TRUE`, `FALSE`.
- References: `A1`, `$A1`, `A$1`, `$A$1`; ranges `A1:B3` (each endpoint may carry `$`).
  A range is normalised so its first endpoint is the top-left (`B3:A1` means `A1:B3`).
- Operators, from lowest to highest precedence:
  1. comparisons `=  <>  <  >  <=  >=` (left-assoc)
  2. concatenation `&` (left-assoc)
  3. `+  -` (left-assoc)
  4. `*  /` (left-assoc)
  5. `^` (left-assoc, as in Excel: `2^3^2` is `64`)
  6. unary `-` and `+` (so `-2^2` is `4`, as in Excel)
- Parentheses; nesting depth up to at least 200 must work.
- Function calls `NAME(arg, ...)`. Required functions:
  `SUM, AVERAGE, MIN, MAX, COUNT, IF, AND, OR, NOT, IFERROR, ROUND, ABS, LEN, CONCAT`.
  - `SUM/AVERAGE/MIN/MAX/COUNT` take any number (≥1) of arguments, each a range or a scalar
    expression. Inside a range only numbers participate; text, booleans and empty cells are
    skipped; an error in a range is propagated. Scalar arguments are coerced to numbers like
    arithmetic operands. `COUNT` counts numbers only (range cells that are numbers, scalar
    arguments that are numbers or coercible to numbers). `AVERAGE` with nothing to average is
    `#DIV/0!`. `MIN`/`MAX` with nothing to compare is `0`.
  - `IF(cond, then[, else])`: only the chosen branch is evaluated. Missing `else` yields
    `FALSE`.
  - `IFERROR(value, fallback)`: `fallback` only if `value` is an error.
  - `AND/OR` take ≥1 scalar or range arguments; `NOT` takes 1.
  - `ROUND(x, digits)`, `ABS(x)`, `LEN(text)`, `CONCAT(a, b, ...)` (ranges allowed in
    `CONCAT`: cells concatenated row-major).
- A range used where a single value is expected (e.g. `=A1:A3+1`) is `#VALUE!`.
- Errors (codes): `#DIV/0!`, `#VALUE!`, `#REF!`, `#NAME?` (unknown function),
  `#CYCLE!`, `#PARSE!` (formula text cannot be parsed). Errors propagate through operators and
  functions; when several operands are errors, the leftmost one (in evaluation order) wins.
- Coercion in arithmetic: empty → `0`, `TRUE`/`FALSE` → `1`/`0`; text that is not a number →
  `#VALUE!`. In `&`, empty → `""` and booleans → `"TRUE"`/`"FALSE"`.

## Dependencies, cycles, recalculation

- Dependencies are the references appearing in the formula text (static, regardless of
  `IF` branches).
- Every cell that lies on a dependency cycle (including a self-reference) evaluates to
  `#CYCLE!`. Cells that merely depend on a cycle receive the propagated error like any other
  error. Breaking the cycle (editing any member) must restore normal values everywhere.
- Recalculation must be incremental: editing a cell recomputes only cells that (transitively)
  depend on it. The acceptance suite has timing tests, e.g. a sheet with ~50,000 populated
  cells where thousands of edits of unrelated cells must stay fast, and dependency chains
  tens of thousands of cells long (no `RecursionError`).

## Structural edits

`insert_rows(at, count)` inserts `count` empty rows so that the old row `at` becomes row
`at+count`; `delete_rows(at, count)` removes rows `at .. at+count-1` and shifts the rows below
up. Columns behave the same way (`at` is a 1-based column number). Both return `None`.
Formulas everywhere are rewritten so they keep pointing at the same cells:

- References to moved cells are shifted. `$` does **not** prevent shifting (it only matters
  for `copy`). The `$` markers are preserved in the rewritten token.
- A single reference to a deleted cell is replaced by the token `#REF!` in the raw text, and
  the formula evaluates to `#REF!`.
- A range keeps the surviving cells: deleting rows inside it shrinks it, deleting rows that
  include an endpoint moves that endpoint to the nearest surviving row inside the range.
  A range whose rows (or columns) are entirely deleted becomes `#REF!`.
- Inserting rows strictly inside a range (after its first row, at or before its last row)
  grows the range. Inserting at or above its first row shifts the whole range. Inserting
  directly below its last row does not change it.
- Values are recalculated after a structural edit.
- If a shift would push a cell or reference beyond the grid, the cell is dropped / the
  reference becomes `#REF!`.

## `copy(src_range, dst_top_left) -> list[str]`

Copies the raw contents of the source block (a single address or a range) to the block of
the same size whose top-left is `dst_top_left`, like Excel paste. Relative row/column parts of
references in formulas are shifted by the offset; parts marked with `$` are not. A reference
that would leave the grid becomes `#REF!`. Empty source cells clear the destination cell.
The copy behaves as if the whole source block were read before anything is written
(overlapping source/destination is allowed). Returns the changed-value addresses like `set`.

## Deliverables

- The library in `gridcalc/` with the fixed public API.
- Your own automated tests (`tests/`, runnable with `python -m pytest`).
- A short `NOTES.md`: design overview and any decisions you made about behaviour this brief
  leaves open.
