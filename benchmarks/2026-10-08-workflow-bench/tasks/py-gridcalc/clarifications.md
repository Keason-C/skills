# gridcalc — product owner's decisions (NOT shown to developers; answer only what is asked)

These are the product owner's settled decisions on points the brief leaves open.

1. Number → text (used by `&`, `CONCAT`, `LEN`, and anywhere a number becomes text):
   Python `format(x, ".15g")`. So `1.0` → `"1"`, `0.1+0.2` → `"0.3"`, `1/3` → `"0.333333333333333"`,
   `1e20` → `"1e+20"`, `-0.0` → `"0"` (negative zero prints as `0`).
2. Comparisons (`= <> < > <= >=`), result is a boolean:
   - Different types order as: numbers < text < booleans (so `"a" > 5` is TRUE, `TRUE > "z"` is TRUE).
   - Text compares case-insensitively (`"abc" = "ABC"` is TRUE, `"a" < "B"` is TRUE).
   - An empty operand takes the type of the other side (`0` vs number, `""` vs text, `FALSE` vs boolean);
     empty vs empty is equal.
   - Numbers are NOT coerced from text in comparisons (`"1" = 1` is FALSE).
3. Text in arithmetic: text that parses as a number under the same rules as literal input
   (surrounding whitespace allowed, e.g. `" 3 "`) is coerced to that number; anything else is `#VALUE!`.
   The empty string `""` (text) in arithmetic is `#VALUE!` (it is text, not empty).
4. `ROUND(x, digits)`: half away from zero (`ROUND(2.5,0)` = 3, `ROUND(-2.5,0)` = -3,
   `ROUND(0.125,2)` = 0.13). `digits` is truncated toward zero to an integer; negative digits round to
   tens/hundreds (`ROUND(1250,-2)` = 1300). (Hint for implementers: use decimal on repr of the float.)
5. Wrong number of arguments to a known function (e.g. `NOT(1,2)`, `IF(TRUE)`, `ROUND(1)`, `SUM()`) is
   `#VALUE!` (not a parse error). Unknown function name → `#NAME?` (checked before arguments).
6. A formula that is just a reference to an empty cell (`=A1`, A1 empty) evaluates to the number `0`.
   `=A1&""` gives `""`.
7. Function names and cell references inside formulas are case-insensitive (`=sum(a1:a2)` works);
   whitespace is allowed between tokens. `get_raw` keeps what the user typed. When a reference token is
   rewritten (structural edit or copy shifts it, or it becomes `#REF!`), the new token is written in
   canonical upper case; tokens whose target did not change are left untouched.
8. Truthiness (IF condition, AND, OR, NOT arguments): numbers → nonzero is TRUE; booleans as is;
   empty → FALSE; text `"TRUE"`/`"FALSE"` (any case) → that boolean; other text → `#VALUE!`.
   Inside ranges given to AND/OR, text and empty cells are skipped; if nothing remains → `#VALUE!`.
9. Numeric results that are not finite (overflow, e.g. `10^400`) or not real (negative base with a
   fractional exponent, e.g. `(-8)^(1/3)`) are `#VALUE!`. `0^-1` and any division by zero are `#DIV/0!`.
   `0^0` is 1.
10. A formula `="" ` yields the empty TEXT `""` (type `str`), not `None`.
11. `set` with exactly the same raw as before returns `[]`. Clearing an already-empty cell returns `[]`.
12. `copy` destination cells outside the grid: raise `ValueError` and change nothing.
