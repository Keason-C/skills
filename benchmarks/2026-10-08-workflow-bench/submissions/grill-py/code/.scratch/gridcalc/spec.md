# gridcalc: in-memory spreadsheet engine

Status: ready-for-agent

## Problem Statement

A developer needs a spreadsheet calculation engine they can embed in Python 3.13 code. It must use only the standard library and have no UI or persistence. They want to put raw strings into cells, read back computed values, and edit the grid structurally (insert or delete rows and columns, copy blocks). Formulas must keep pointing at the right cells after those edits, and values must stay correct.

The public API is fixed by `BRIEF.md` and the starter `gridcalc/__init__.py`. A hidden acceptance suite exercises it, including timing tests on large sheets and very long dependency chains. Where the brief leaves behaviour open, the decisions must be made explicitly, implemented consistently, and documented.

## Solution

A pure-Python library, `gridcalc`, that exposes `Sheet` and `CellError` with exactly the signatures from the starter code:

- **Storing cells.** `Sheet.set` stores a cell's raw string, classifies it as a literal or a formula, and recalculates incrementally. It returns the cells whose computed values changed.
- **Formulas.** Each formula is compiled once into a small stack-machine program, so neither evaluation nor parsing ever recurses.
- **Dependencies.** A dependency graph tracks which cells read which. An index for single references and a separate range index find dependents quickly. Cycles are detected on the affected subgraph only.
- **Structural edits and copies.** These rewrite only the reference tokens in a formula's raw text whose target changes, and keep every other byte.
- **Open behaviour.** Every decision the brief leaves open is fixed below and recorded in `NOTES.md`.

## User Stories

### Addresses

1. As a library user, I want to address cells as `A1`, `Z99`, `AA10` or `XFD1048576`, so that I can use familiar spreadsheet notation.
2. As a library user, I want addresses to be case-insensitive (`"b3"` is `"B3"`), so that I don't have to normalise my input.
3. As a library user, I want every returned address in canonical upper case, so that I can compare results reliably.
4. As a library user, I want a malformed address to raise `ValueError`, so that typos fail loudly. Malformed means: surrounding whitespace, a `$` marker, a row of `0`, a row with a leading zero (`A01`), or a range where one cell is expected.
5. As a library user, I want an address outside the 16384 × 1048576 grid to raise `ValueError`, so that I never silently write outside the sheet.
6. As a library user, I want a non-`str` raw value passed to `set` to raise `TypeError`, so that type mistakes are caught immediately.

### Literals

7. As a library user, I want `set(addr, "")` to clear a cell, so that `get` returns `None` and `get_raw` returns `""`.
8. As a library user, I want a raw string that, after `strip()`, fully matches `[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?` to be stored as a float, so that `"42"`, `" 42 "`, `"1."`, `"+5"`, `".5"` and `"-2.5E-2"` are numbers.
9. As a library user, I want `inf`, `nan`, `1_000`, `0x10`, `1,000` and non-ASCII digits to stay text, so that Python's lenient `float()` doesn't leak into spreadsheet semantics.
10. As a library user, I want a numeric literal that overflows to infinity (`1e400`) to be stored as text, so that no infinite numbers ever appear as cell values.
11. As a library user, I want `TRUE` and `FALSE` in any case, with surrounding whitespace allowed (`" true "`), to be booleans.
12. As a library user, I want a leading apostrophe to force text (`'123` is the text `"123"`), and a lone `'` to be the text `""` (a non-empty cell).
13. As a library user, I want any other literal stored exactly as given, with no stripping (`"   "` is the text `"   "`), so that my text is preserved.
14. As a library user, I want only raw strings whose first character is `=` treated as formulas, so that `" =1"` is text.
15. As a library user, I want `get_raw` to return exactly what I stored, so that I can round-trip cell contents.
16. As a library user, I want numbers always returned as `float`, never `int`, so that value types are predictable.

### Formula language

17. As a formula author, I want number literals (`3`, `2.5`, `.5`, `1e3`), string literals with `""` as an escaped quote, and `TRUE`/`FALSE`.
18. As a formula author, I want the six error literals (`#DIV/0!`, `#VALUE!`, `#REF!`, `#NAME?`, `#CYCLE!`, `#PARSE!`) accepted as constants, so that formulas rewritten with `#REF!` still parse.
19. As a formula author, I want references `A1`, `$A1`, `A$1`, `$A$1` and ranges like `A1:B3` with optional `$` on each endpoint. A reversed range such as `B3:A1` should mean `A1:B3`.
20. As a formula author, I want references and function names to be case-insensitive (`=sum(a1)`).
21. As a formula author, I want whitespace allowed between any tokens, including between a function name and `(`.
22. As a formula author, I want the brief's operator precedence. From lowest to highest: comparisons, `&`, `+ -`, `* /`, `^` (left-associative, so `2^3^2` is 64), then unary `-` and `+` (so `-2^2` is 4).
23. As a formula author, I want nested parentheses of any practical depth (at least 200), and very long operator chains like `=A1+A2+…+A5000`, to work without `RecursionError`.
24. As a formula author, I want a formula that cannot be parsed to evaluate to `#PARSE!`. That covers: a lone `=`, trailing garbage, unbalanced parentheses, an empty argument like `=SUM(1,,2)`, malformed references like `A0` or `A01`, `%`, whole-column or whole-row ranges (`A:A`, `1:1`), sheet-qualified references, and array literals.
25. As a formula author, I want a well-formed reference outside the grid (`=XFE1`, `=A1048577`) to evaluate to `#REF!`.
26. As a formula author, I want an unknown function, or a bare identifier such as `=foo`, to evaluate to `#NAME?` without evaluating its arguments.
27. As a formula author, I want a known function called with the wrong number of arguments to evaluate to `#VALUE!`. The count is checked before any argument is evaluated, and only when the call itself is evaluated. So `=ROUND(1/0)` is `#VALUE!`, and `=IF(TRUE,1,ROUND(1))` is 1.

### Values and coercion

28. As a formula author, I want arithmetic to coerce empty to 0 and `TRUE`/`FALSE` to 1/0. Text should convert only if it matches the literal number rule (`"12"+1` is 13, `" 12 "+1` is 13), and any other text gives `#VALUE!` (`""+1` and `"TRUE"+1`).
29. As a formula author, I want unary `+` to convert to a number like unary `-`: `=+"12"` is 12, `=+TRUE` is 1, `=+"a"` is `#VALUE!`.
30. As a formula author, I want `x/0` to give `#DIV/0!`, with an empty divisor counting as 0.
31. As a formula author, I want overflow, nan and complex results (`(-8)^(1/3)`) to give `#VALUE!`, `0^-1` to give `#DIV/0!`, and `0^0` to be 1.
32. As a formula author, I want `-0.0` results normalised to `0.0`.
33. As a formula author, I want `&` to treat empty as `""`, booleans as `"TRUE"`/`"FALSE"`, and numbers as `format(x, ".15g")` (lowercase exponent, `-0` shown as `"0"`). So `=1&"x"` is `"1x"`, `=0.1+0.2&""` is `"0.3"`, and `=1e20&""` is `"1e+20"`.
34. As a formula author, I want a formula whose result is an empty cell (`=A1` with A1 empty) to evaluate to `0.0`, not `None`.
35. As a formula author, I want a range used where a single value is expected (`=A1:A3+1`, `=A1:A3`) to give `#VALUE!`.
36. As a formula author, I want only a reference or range written directly, optionally in parentheses, to count as a reference. A range returned by `IF` or `IFERROR` should give `#VALUE!`, so `=SUM(IF(TRUE,A1:A3,0))` is `#VALUE!`.
37. As a formula author, I want errors to propagate through operators and functions, and when several operands are errors, the leftmost in evaluation order should win.

### Comparisons

38. As a formula author, I want `= <> < > <= >=` to compare same-type values naturally, with text compared ignoring case using casefold (`"a"="A"` is TRUE).
39. As a formula author, I want mixed-type comparisons never to coerce. They should order number < text < boolean, so `1="1"` is FALSE and `"z"<TRUE` is TRUE.
40. As a formula author, I want an empty operand to take the other side's type (0, `""` or FALSE), and two empty operands to be equal.

### Functions

41. As a formula author, I want `SUM`, `AVERAGE`, `MIN`, `MAX` and `COUNT` to take one or more arguments, each a range or a scalar. Inside a range, only numbers count; text, booleans and empty cells are skipped, and an error propagates.
42. As a formula author, I want a single reference written directly in those functions (`SUM(A1)`, `SUM((A1))`) treated as a 1-cell range, so its text and booleans are skipped.
43. As a formula author, I want scalar arguments coerced as in arithmetic: `SUM("3")` is 3, `SUM(TRUE)` is 1, `SUM("x")` is `#VALUE!`.
44. As a formula author, I want `COUNT` to count numbers in ranges plus scalar arguments that convert to numbers, with no error for those that don't. So `COUNT("3")` is 1, `COUNT(TRUE)` is 1, `COUNT("x")` is 0, but `COUNT(1/0)` is `#DIV/0!`.
45. As a formula author, I want `AVERAGE` with nothing to average to give `#DIV/0!`, and `MIN`/`MAX` with nothing to compare to give 0.
46. As a formula author, I want `IF(cond, then[, else])` to evaluate only the chosen branch, and to return FALSE when `else` is missing and the condition is false.
47. As a formula author, I want `IFERROR(value, fallback)` to return the fallback only when `value` is an error. That includes errors from a wrong argument count, so `=IFERROR(ROUND(1),5)` is 5.
48. As a formula author, I want logical tests (`IF` condition, `AND`, `OR`, `NOT`) to treat:
    - a nonzero number as TRUE, a boolean as itself, and empty as FALSE;
    - scalar text `"true"` or `"false"` (any case) as the boolean, and any other scalar text as `#VALUE!`;
    - a range as the `IF` condition as `#VALUE!`.
49. As a formula author, I want `AND`/`OR` to accept one or more scalar or range arguments. Inside ranges, text and empty cells are skipped. If there are no logical values at all, the result is `#VALUE!`. `NOT` takes exactly one argument.
50. As a formula author, I want `ROUND(x, digits)` to round half away from zero via `Decimal(repr(x))`, so `ROUND(2.675,2)` is 2.68. Digits are truncated toward zero, and negative digits work (`ROUND(1234,-2)` is 1200).
51. As a formula author, I want `ABS(x)` to coerce like arithmetic.
52. As a formula author, I want `LEN(text)` to measure the text form of its argument: numbers formatted as above, `LEN(TRUE)` is 4, an empty cell is 0.
53. As a formula author, I want `ROUND`, `ABS` and `LEN` given a range to return `#VALUE!`.
54. As a formula author, I want `CONCAT(a, b, ...)` to accept scalars and ranges, joining range cells in row-major order. Empty cells contribute `""` and errors propagate.

### Recalculation and change reporting

55. As a library user, I want `set` to return the address of every cell whose computed value changed, including `addr` itself, sorted by row then column, with no duplicates.
56. As a library user, I want a cell whose raw text changed but whose value didn't to be left out of the list. Equality means same type and equal value: `1.0` and `True` differ, and two errors with the same code are equal.
57. As a library user, I want an edit to recompute only the cells that depend on it, directly or indirectly, so that large sheets stay fast.
58. As a library user, I want dependencies to be the references written in the formula text, regardless of which `IF` branch runs. That includes references inside calls to unknown functions and calls with the wrong argument count.
59. As a library user, I want every cell on a dependency cycle, including a cell that references itself, to evaluate to `#CYCLE!`.
60. As a library user, I want cells that merely depend on a cycle to receive the propagated error like any other error. For example, `IFERROR` around a cycle member returns its fallback.
61. As a library user, I want editing any member of a cycle so that the cycle is broken to restore normal values everywhere.
62. As a library user, I want dependency chains tens of thousands of cells long to build and recalculate without `RecursionError`.
63. As a library user, I want thousands of edits to unrelated cells on a sheet of about 50,000 populated cells to stay fast. That should hold even when many formulas use large or overlapping ranges.

### Structural edits

64. As a library user, I want `insert_rows(at, count)` to insert empty rows so that old row `at` becomes `at+count`, and `insert_cols` to do the same for columns.
65. As a library user, I want `delete_rows(at, count)` to remove rows `at` to `at+count-1` and shift the rows below up, and `delete_cols` to do the same for columns.
66. As a library user, I want structural edits to return `None` and to recalculate values afterwards.
67. As a library user, I want invalid structural edit arguments rejected:
    - `at` outside 1 to max, `count < 1`, or a delete running past the grid edge raises `ValueError`;
    - a non-int or `bool` argument raises `TypeError`.
68. As a library user, I want references to moved cells shifted whatever their `$` markers, with the markers kept in the rewritten token.
69. As a library user, I want a single reference to a deleted cell replaced by the token `#REF!` in the raw text, so that the formula evaluates to `#REF!`.
70. As a library user, I want ranges to keep the cells that survive a delete:
    - deleting rows inside a range shrinks it;
    - deleting rows that include an endpoint moves that endpoint to the nearest surviving row inside the range;
    - deleting all of a range's rows (or columns) turns it into `#REF!`.
71. As a library user, I want inserts to treat ranges like Excel does:
    - inserting strictly inside a range (after its first row, at or before its last) grows it;
    - inserting at or above its first row shifts it;
    - inserting directly below its last row leaves it unchanged.
72. As a library user, I want a cell pushed off the grid by an insert to be dropped, and a single reference pushed off the grid to become `#REF!`.
73. As a library user, I want a range whose end is pushed off the grid clamped to the grid edge. It becomes `#REF!` only if its first endpoint is pushed off too.

### Copy

74. As a library user, I want `copy(src, dst)` to copy the raw contents of a single cell or a range (reversed ranges normalised) to the same-sized block whose top-left is `dst`.
75. As a library user, I want relative parts of references shifted by the copy offset and `$`-marked parts kept fixed.
76. As a library user, I want any reference, or any range endpoint, that a copy shifts off the grid to turn the whole token into `#REF!`.
77. As a library user, I want empty source cells to clear the matching destination cells.
78. As a library user, I want an overlapping source and destination to behave as if the whole source block were read before anything is written.
79. As a library user, I want a destination block that would extend past the grid to raise `ValueError` and write nothing.
80. As a library user, I want `copy` to return the changed-value addresses exactly like `set`, with a single recalculation after the whole block is written.

### Rewriting raw text

81. As a library user, I want structural edits and copies to change only the reference tokens whose target changes. Everything else, including the original case of untouched tokens such as `a1`, stays byte for byte.
82. As a library user, I want a rewritten token written in canonical upper case with its `$` markers kept.
83. As a library user, I want a rewritten range written top-left first, normalised one axis at a time with each coordinate keeping its own `$`. So `$B3:A$1` is written `A$1:$B3`, and a one-cell range keeps the `A1:A1` form.
84. As a library user, I want `#PARSE!` formulas, references already outside the grid, and existing `#REF!` tokens left verbatim by both structural edits and copies.

### Deliverables

85. As a maintainer, I want a `NOTES.md` that gives a design overview and lists every behaviour decision the brief left open, so that future changes stay consistent.
86. As a maintainer, I want an automated test suite under `tests/` that runs with `python -m pytest`, including timing tests, so that regressions are caught.

## Implementation Decisions

- **Public seam.** `Sheet` and `CellError` keep the exact names, signatures and return types from the starter code. `CellError` is unchanged. Everything else is private modules inside the package.
- **Modules.**
  - **Addresses.** Converts between column letters (bijective base 26) and numbers, parses addresses and ranges for the API (strict: no `$`, no whitespace, no leading-zero rows, bounds checked), and formats canonical addresses.
  - **Values and coercion.** Classifies literals, converts values to numbers, text and logical values, formats numbers (`.15g`), and implements Excel comparison ordering. One shared literal-number matcher serves both literal classification and text-to-number coercion.
  - **Formula lexer.** Produces tokens annotated with their position in the source text. Reference and range tokens carry their parsed coordinates and `$` flags. The same tokens are used for compiling, for extracting dependencies and for rewriting raw text.
  - **Compiler.** A non-recursive shunting-yard parser that emits a flat program for a small stack machine:
    - lazy `IF` and `IFERROR` are implemented with conditional jumps;
    - argument counts are recorded at each call site;
    - a known function called with the wrong count compiles to an instruction that pushes `#VALUE!` without evaluating its arguments;
    - an unknown function or bare identifier compiles to an instruction that pushes `#NAME?`.

    Compile failure yields a fixed program that returns `#PARSE!` and has no dependencies.
  - **Evaluator and function library.** An iterative stack-machine loop with no recursion. A value reference or range written directly is a distinct operand kind that aggregates can consume. Wherever a scalar is required, such an operand is resolved to a scalar, or to `#VALUE!` for a multi-cell range. Results from `IF`/`IFERROR` are always scalars.
  - **Dependency graph and recalculation engine.**
    - Each formula cell records its static dependencies: single cells and ranges.
    - The reverse index holds single references in a dict from cell to dependents. Ranges go in a separate column-bucketed index, so that a long range doesn't add one entry per covered cell.
    - On `set` or `copy`, the engine collects the transitive dependents of the edited cells with a loop, runs an iterative Tarjan SCC on that subgraph, and marks cycle members (SCCs larger than one cell, or self-loops) as `#CYCLE!`.
    - Remaining cells are evaluated in dependency order. Each cell's old and new values are compared under the brief's equality rule (same type and equal) to build the change list.
  - **Reference rewriting.** Pure functions that map a reference or range token through a structural edit (insert or delete, rows or columns) or a copy offset. Each returns either "unchanged", a new token text, or `#REF!`. Raw text is rebuilt by splicing only the changed token positions.
  - **Sheet facade.**
    - Holds a sparse dict from (row, col) to a cell record: raw text, compiled program, dependencies, cached value.
    - Validates arguments and coordinates the modules above.
    - A structural edit remaps cell positions (dropping cells pushed off the grid), rewrites every parseable formula's raw text, recompiles, rebuilds the dependency graph from scratch and recalculates everything (O(n)).
- **No recursion anywhere**, either inside one formula or across cell chains. `sys.setrecursionlimit` is never touched.
- **Leftmost error wins.** Operands and arguments are evaluated left to right, and ranges in row-major order. The first error encountered is the result.
- **Normalising `-0.0`.** Numeric results are normalised before storing, so `-0.0` becomes `0.0`.

## Testing Decisions

- **One seam.** All tests go through the public `Sheet`/`CellError` API, the same interface the hidden acceptance suite uses. Tests assert observable behaviour: `set`/`copy` return values, `get`, `get_raw`, and raised exceptions. They never touch internal modules or data structures, so the engine's internals can change freely.
- **A good test** sets up a small sheet, does one action, and checks values, raw text or change lists. Each test is named after the behaviour it checks. Each decision in this spec gets at least one test, including the edge cases (lowercase exponent, `0^0`, arity `#VALUE!`, clamped ranges, verbatim `#PARSE!` copies, and so on).
- **Tests are grouped by area:** addresses and validation, literals, operators and coercion, comparisons, each function family, errors and propagation, dependencies and change reporting, cycles, copy, row edits, column edits, rewriting raw text, and performance.
- **Timing tests.**
  - On a sheet of 50,000 populated cells, 5,000 edits to unrelated cells take under 1 second.
  - Building a 50,000-cell dependency chain and editing its head takes under 3 seconds total, with no `RecursionError`.
  - Parentheses nested 200+ deep and a 5,000-term `+` chain evaluate correctly.
- **Prior art.** None; the repo only has an empty `tests/`. Plain pytest functions, with `pytest.mark.parametrize` for tables of inputs.
- **Process.** Built test-first in vertical slices, in this order: addresses, literals, parser and evaluator, functions, dependency graph and cycles, copy, structural edits, performance. One local commit per slice on a `gridcalc` branch; nothing is pushed.

## Out of Scope

- Any UI, file I/O, persistence, import or export.
- Functions beyond the 14 required ones. Named ranges, sheet-qualified references, whole-row and whole-column ranges, array formulas, the `%` operator, and the space intersection operator are also out.
- Number formatting or display beyond the `.15g` text form.
- Dynamic dependencies (`INDIRECT`, `OFFSET`) and references returned by functions.
- `#NUM!` and other Excel error codes not in `CellError.CODES`.
- Undo/redo, multiple sheets, and thread safety.
- Pushing commits or opening a pull request.

## Further Notes

- `NOTES.md` must restate every decision above that goes beyond the brief: Q2–Q22 from the grilling session.
- These decisions deliberately differ from Excel:
  - `COUNT` propagates errors;
  - `0^0` is 1;
  - conditions Excel reports as `#NUM!` give `#VALUE!`;
  - a wrong argument count gives `#VALUE!` instead of rejecting the formula;
  - unary `+` converts to a number;
  - `IF` cannot return a reference;
  - number text uses `.15g` with a lowercase exponent.
