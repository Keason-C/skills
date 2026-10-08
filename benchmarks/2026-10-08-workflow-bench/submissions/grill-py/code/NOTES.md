# gridcalc: design notes

## Design overview

`Sheet` (in `gridcalc/__init__.py`) is a thin facade over a private engine.

| Module | Responsibility |
|---|---|
| `_address.py` | A1 addresses ⇄ `(row, col)`; strict API parsing. |
| `_values.py` | Literal classification, coercion, number formatting, Excel-style comparison, error singletons. |
| `_lexer.py` | Tokenizer (one master regex). Tokens carry source spans, so references can be rewritten in place. |
| `_formula.py` | Shunting-yard parser → small AST → flat stack-machine program. `IF`/`IFERROR` compile to jumps, so only the chosen branch runs. Also holds the evaluator loop. |
| `_functions.py` | The 14 built-in functions. |
| `_operands.py` | What evaluation passes around: values, plus unread references as coordinate tuples. |
| `_depgraph.py` | Reverse dependency index: a dict for single references, and a 2-D dyadic block index for ranges. |
| `_rewrite.py` | Rewriting reference tokens for `copy` and structural edits. |
| `_engine.py` | Cell storage, recalculation, `copy`, structural edits. |

**No recursion anywhere.** Parsing, code generation and evaluation all use
explicit stacks, and so does the walk across cells. Nesting depth and chain
length are bounded only by memory. `sys.setrecursionlimit` is never touched.

**Recalculation** (`Engine._recalc`) runs after a `set` or `copy`:

1. Collect every cell downstream of the edited cells, plus the edges among
   them, with a loop over the reverse index.
2. Order the acyclic part with Kahn's algorithm. Whatever Kahn cannot order
   is on a cycle or downstream of one; only that part goes through an
   iterative Tarjan SCC pass. Cycle members (an SCC with more than one cell,
   or a self-loop) get `#CYCLE!`.
3. Evaluate in dependency order. A cell is re-evaluated only if one of its
   inputs actually changed value. A cell that just left a cycle is always
   re-evaluated.
4. The change list is every visited cell whose value changed (same type and
   equal), sorted row-major.

An edit to a cell nothing reads takes a fast path that skips all of this.

**Range index.** Each range is split into O(log n) aligned power-of-two
blocks per axis and filed under every (column block, row block) pair. A
point lookup probes one bucket per level that is actually in use. So even a
range over the whole grid stays cheap, and a lookup never scans unrelated
ranges (for example, thousands of `SUM` formulas in one column).

**Structural edits.**

- Every cell is moved.
- Formulas that could be affected are rewritten in their raw text. A formula
  whose references all lie before the edit point is skipped.
- Each rewritten formula's compiled program is *relocated*: reference
  operands are mapped to their new positions, or to `#REF!`. This is
  equivalent to recompiling the rewritten text, without tokenizing again.
- Only formulas whose references *lost* cells are recalculated, along with
  their dependents. Losing cells means a reference became `#REF!`, or a range
  shrank or was clamped. A pure shift leaves every value unchanged, and
  growing a range only adds empty cells, which every range function skips.
- A randomised differential test (`tests/test_differential.py`) checks these
  shortcuts against freshly built sheets.

**`copy`** reads the whole source block, computes every destination's raw
text, writes the block, then recalculates once.

**Performance**, measured on this machine and covered by `tests/test_performance.py`:

- 5,000 unrelated edits on a 50,000-cell sheet: about 0.05s.
- Building a 50,000-cell chain: about 2s. Editing its head: about 0.3s.
- An insert or delete on the 50,000-cell sheet: about 0.9s.

These timings vary by about ±25% from run to run on this machine. Under
pytest the chain test takes 2.0–2.7s, against a 3s budget.

Compiled code is made of tuples of atomic values, so CPython's garbage
collector stops tracking it. Before that change, GC was about 40% of the
time to build a large sheet.

## Behaviour decisions beyond the brief

### Literals

- After `strip()`, a cell is a number if it fully matches
  `[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?` (ASCII digits only).
  So `1.` and `+5` are numbers.
- `inf`, `nan`, `1_000`, `0x10` and `1,000` stay text, as does a literal
  that overflows to infinity (`1e400`).
- The strip also applies to booleans: `" true "` is `True`.
- `'` alone is the text `""`, not an empty cell.
- A raw string is a formula only if its first character is `=`, so `" =1"`
  is text.

### Coercion and formatting

- Text converts to a number only if it matches the literal rule above:
  `"12"+1` is 13, while `""+1` and `"TRUE"+1` are `#VALUE!`.
- Unary `+` converts to a number, just like unary `-` (`=+"a"` is
  `#VALUE!`). Excel treats unary `+` as a no-op.
- A number becomes text via `format(x, ".15g")`, with Python's lowercase
  exponent: `3` → `"3"`, `0.1+0.2` → `"0.3"`, `1e20` → `"1e+20"`, `-0` → `"0"`.
- A formula whose result is an empty cell (`=A1` with A1 empty) evaluates to
  `0.0`, not `None`.

### Arithmetic

- `CellError` has no `#NUM!` code, so wherever Excel gives `#NUM!` we give
  `#VALUE!`: overflow to inf or nan, complex results such as `(-8)^(1/3)`,
  and a number literal in a formula that overflows (`=1e400`).
- `0^-1` is `#DIV/0!`.
- `0^0` is `1`.
- `-0.0` results are normalised to `0.0`.
- Error precedence goes left to right, *including coercion*: `="x"+1/0` is
  `#VALUE!`, because the left operand fails first.

### Comparisons

- Text compares ignoring case (casefold).
- Mixed types are never coerced. The order is number < text < boolean, so
  `1="1"` is FALSE.
- An empty operand takes the other side's type (0, `""` or FALSE), and two
  empty operands are equal.

### Functions

- Function names and references are case-insensitive. Whitespace is allowed
  between any tokens, including `SUM (A1)` and `A1 : B2`.
- A single reference written directly (optionally in parentheses) in
  `SUM`/`AVERAGE`/`MIN`/`MAX`/`COUNT`/`AND`/`OR`/`CONCAT` is treated as a
  1-cell range, so text, booleans and empty cells in it are skipped, as in
  Excel. The `AND`/`OR` part was confirmed with the product owner. Computed
  values are scalars and are coerced: `SUM("3")` is 3, `SUM("x")` is
  `#VALUE!`.
- `COUNT` counts scalars that convert to numbers (`COUNT("3")` = 1,
  `COUNT("x")` = 0), but it propagates errors (`COUNT(1/0)` = `#DIV/0!`).
  Excel ignores the error.
- Logical tests (`IF` condition, `AND`/`OR`/`NOT` scalars):
  - a nonzero number is TRUE and empty is FALSE;
  - text `"true"`/`"false"` (any case) converts; other text is `#VALUE!`;
  - a range as the `IF` condition is `#VALUE!`.
- `AND`/`OR` with no logical values at all is `#VALUE!`.
- `ROUND` rounds half away from zero via `Decimal(repr(x))`, so
  `ROUND(2.675,2)` = 2.68. Digits are truncated toward zero, and negative
  digits work. The Decimal context's precision scales with the number, so
  values of 1e28 and above round correctly.
- `LEN` measures the text form of its argument (`LEN(TRUE)` = 4).
- In `CONCAT`, empty cells add `""` and errors propagate.
- `ROUND`, `ABS`, `LEN` and `NOT` given a range return `#VALUE!`.
- Only a reference written directly in the formula is a reference. `IF` and
  `IFERROR` always return scalars, so a range they return is `#VALUE!`:
  `SUM(IF(TRUE,A1:A3,0))` is `#VALUE!`.
- Any range used as a single value is `#VALUE!`, including a 1-cell range
  such as `A1:A1`.

### Names and errors

- An unknown function or a bare identifier (`=foo`) gives `#NAME?`. This is
  checked first, and the arguments are never evaluated.
- A known function with the wrong number of arguments gives `#VALUE!`. The
  count is checked before any argument is evaluated, and only when that call
  is actually evaluated: `=IF(TRUE,1,ROUND(1))` is 1, and
  `=IFERROR(ROUND(1),5)` is 5.
- The six error literals may be written in formulas, in any case.
- A well-formed reference outside the grid (`=XFE1`) evaluates to `#REF!`.
- These give `#PARSE!`: malformed references (`A0`, `A01`), `%`, `A:A`,
  `1:1`, sheet-qualified references, array literals, a lone `=`, an empty
  argument (`SUM(1,,2)`), and trailing garbage.
- A `#PARSE!` formula has no dependencies.
- Dependencies are static: references inside untaken `IF` branches, inside
  unknown-function calls, and inside calls with the wrong argument count all
  count.

### Rewriting raw text

- `#PARSE!` formulas, references already outside the grid and existing
  `#REF!` tokens are never rewritten, by `copy` or by structural edits.
- A token is rewritten only if its target changes. Unchanged tokens keep
  their original bytes, including lower case.
- A rewritten token is written in canonical upper case and keeps its `$`
  markers.
- A rewritten range is written top-left first, normalised one axis at a time
  with each coordinate keeping its own `$`: `$B3:A$1` becomes `A$1:$B3`. A
  one-cell range keeps the `A1:A1` form.
- Whitespace around a range's `:` (`A1 : B2`) is part of the range token.
  When that token is rewritten it is written without the spaces. Everything
  outside the token is preserved byte for byte.
- A range whose end is pushed off the grid by an insert is clamped to the
  edge. It becomes `#REF!` only if its first endpoint is pushed off too.
- In `copy`, a reference or any range endpoint that leaves the grid turns
  the whole token into `#REF!`.

### API validation

- These raise `ValueError`:
  - an address with `$`, surrounding whitespace, a leading-zero row, or a
    range where one cell is expected;
  - a structural edit with `at` outside 1..max, `count < 1`, or a delete
    running past the grid edge;
  - a `copy` whose destination block would leave the grid. Nothing is
    written.
- A non-`str` address (in any method, including `copy`'s source and
  destination) and a non-int (or `bool`) `at`/`count` raise
  `ArgumentTypeError`. It is both a `TypeError` and a `ValueError`, so code
  catching either works (product owner decision).
- A non-`str` raw value raises plain `TypeError`.
- `copy` accepts `"A1"` or `"A1:B2"` (reversed ranges are normalised) as the
  source, and one address as the destination.
