"""Cell values: literal parsing, coercions, comparison and number formatting.

Values are `None` (empty), `float`, `str`, `bool` or `CellError`.
"""

from __future__ import annotations

import math
import re

from . import CellError  # defined before submodules are imported

_NUMBER_RE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")

DIV0 = CellError("#DIV/0!")
VALUE = CellError("#VALUE!")
REF = CellError("#REF!")
NAME = CellError("#NAME?")
CYCLE = CellError("#CYCLE!")
PARSE = CellError("#PARSE!")


def parse_number(text: str) -> float | None:
    """The number `text` denotes under the literal-input rules, else None."""
    stripped = text.strip()
    if _NUMBER_RE.fullmatch(stripped) is None:
        return None
    number = float(stripped)
    return number + 0.0 if math.isfinite(number) else None


def parse_literal(raw: str) -> float | str | bool:
    """Value of a non-formula, non-empty raw input."""
    if raw.startswith("'"):
        return raw[1:]
    number = parse_number(raw)
    if number is not None:
        return number
    upper = raw.strip().upper()
    if upper == "TRUE":
        return True
    if upper == "FALSE":
        return False
    return raw


def same_value(a, b) -> bool:
    """Value equality as `set` reports changes: same type and equal."""
    return type(a) is type(b) and a == b


def checked(x: float) -> float | CellError:
    """Normalise an arithmetic result: no -0.0, non-finite -> #VALUE!."""
    if math.isfinite(x):
        return x + 0.0
    return VALUE


def to_number(v) -> float | CellError:
    """Coerce for arithmetic. Returns a float or a CellError."""
    t = type(v)
    if t is float:
        return v
    if v is None:
        return 0.0
    if t is bool:
        return 1.0 if v else 0.0
    if t is str:
        n = parse_number(v)
        return VALUE if n is None else n
    if t is CellError:
        return v
    return VALUE  # a range in scalar position


def format_number(x: float) -> str:
    if x == 0:
        return "0"
    return format(x, ".15g")


def to_text(v) -> str | CellError:
    """Coerce for `&` and text functions. Returns a str or a CellError."""
    t = type(v)
    if t is str:
        return v
    if v is None:
        return ""
    if t is float:
        return format_number(v)
    if t is bool:
        return "TRUE" if v else "FALSE"
    if t is CellError:
        return v
    return VALUE


def to_bool(v) -> bool | CellError:
    """Coerce for IF/AND/OR/NOT. Returns a bool or a CellError."""
    t = type(v)
    if t is bool:
        return v
    if v is None:
        return False
    if t is float:
        return v != 0
    if t is str:
        upper = v.strip().upper()
        if upper == "TRUE":
            return True
        if upper == "FALSE":
            return False
        return VALUE
    if t is CellError:
        return v
    return VALUE


# Excel ordering of types in comparisons: numbers < text < booleans.
_TYPE_RANK = {float: 0, str: 1, bool: 2}
_EMPTY_AS = {float: 0.0, str: "", bool: False}


def compare(op: str, a, b) -> bool:
    """Evaluate a comparison operator. Operands are scalars (no errors)."""
    if a is None and b is None:
        a = b = 0.0
    elif a is None:
        a = _EMPTY_AS[type(b)]
    elif b is None:
        b = _EMPTY_AS[type(a)]
    ra, rb = _TYPE_RANK[type(a)], _TYPE_RANK[type(b)]
    if ra != rb:
        a, b = ra, rb
    elif ra == 1:
        a, b = a.casefold(), b.casefold()
    if op == "=":
        return a == b
    if op == "<>":
        return a != b
    if op == "<":
        return a < b
    if op == ">":
        return a > b
    if op == "<=":
        return a <= b
    return a >= b
