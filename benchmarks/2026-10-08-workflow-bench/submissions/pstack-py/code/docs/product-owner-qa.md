# Product owner Q&A

Asked with `ask-po` during the build. The questions and answers are copied verbatim. NOTES.md summarizes them.

## Questions

Hi, I'm building gridcalc from BRIEF.md. A batch of open behaviour questions; a short answer per number is plenty, and "your call" is fine for any of them.
1. A formula that is just a reference to an empty cell (=A1, A1 empty): should get() return 0.0 (Excel) or None?
2. SUM/COUNT/AVERAGE/MIN/MAX/AND/OR with a single-cell reference argument like SUM(A1) where A1 holds text "abc": treat the reference like a 1-cell range (text skipped, Excel behaviour) or like a scalar (coerced, so #VALUE!)?
3. Comparisons: Excel-style (text compares case-insensitively, mixed types order number < text < boolean, empty acts as 0 / "" / FALSE depending on the other side)? Or something else, e.g. comparing different types gives #VALUE!?
4. Numbers converted to text (in &, LEN, CONCAT): I plan Excel "General"-like output with up to 15 significant digits: 1 -> "1", 0.1+0.2 -> "0.3", 1E20 -> "1E+20". OK?
5. Math with no valid real result (overflow to infinity, negative number to a fractional power, 0^0, 0^-1): there is no #NUM! code. Which code? My proposal: 0^negative -> #DIV/0!, everything else -> #VALUE!.
6. Wrong number of arguments to a known function (ABS(1,2), SUM(), IF(1)): #VALUE! or #PARSE!?
7. An unknown bare name in a formula (=foo+1), or an out-of-grid reference like =XFE1 or =A0: #NAME? (Excel), #PARSE!, or #REF!?
8. Literal input " TRUE " (surrounding spaces): boolean or text? (Numbers are stripped per the brief; unsure for booleans.)
9. Invalid arguments to insert/delete rows/cols (at < 1, at beyond the grid, count < 1, delete range running past the grid end): raise ValueError, or clamp / no-op?
10. copy() where the destination block would run past the grid edge: ValueError, or silently drop the off-grid cells? And may dst be a range (use its top-left) or must it be a single address?
11. API addresses: should "A01" (leading zero row), " A1" (whitespace) or "$A$1" be accepted or raise ValueError?
12. Inserting rows inside a range when its bottom endpoint would be pushed past the grid: whole range -> #REF!, or clamp its end to the last row?

## Answers

1. `0.0`. A formula that is just a reference to an empty cell gives the number 0. (`=A1&""` gives `""`.)

2. Treat it like a 1-cell range. Text, booleans and empty cells are skipped and errors propagate, as in Excel. This applies to SUM/AVERAGE/MIN/MAX/COUNT and AND/OR.

3. Yes, Excel-style, as you describe. Also, text is never coerced to a number in comparisons, so `"1" = 1` is FALSE.

4. Nearly. Use Python `format(x, ".15g")`, which gives a lowercase exponent: `1e20` → `"1e+20"`. Negative zero prints as `"0"`.

5. `0^negative` → `#DIV/0!` (as is any division by zero). Overflow and non-real results → `#VALUE!`. But `0^0` is `1`, not an error.

6. `#VALUE!`. An unknown function name is `#NAME?`, and that check happens before argument checking.

7. `#NAME?` for both. Any bare identifier that isn't a valid in-grid reference is an unknown name, including `XFE1` and `A0`.

8. Boolean. Surrounding whitespace is stripped for the TRUE/FALSE check too.

9. Raise `ValueError` for `at < 1`, `at` beyond the grid, `count < 1`, and a delete that runs past the grid end.

10. Raise `ValueError` and change nothing. `dst` must be a single address; a range there is a `ValueError`.

11. Raise `ValueError` for all three: `"A01"`, `" A1"` and `"$A$1"`.

12. Clamp the range's end to the last grid row. It becomes `#REF!` only if its first row would be pushed off the grid.
