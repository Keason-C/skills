"""Cell values: literal classification, coercion, formatting and comparison.

A value is ``None`` (empty), ``float``, ``str``, ``bool`` or ``CellError``.
"""

from __future__ import annotations

import math
import operator
import re

from . import CellError

DIV0 = CellError("#DIV/0!")
VALUE = CellError("#VALUE!")
REF = CellError("#REF!")
NAME = CellError("#NAME?")
CYCLE = CellError("#CYCLE!")
PARSE = CellError("#PARSE!")

ERRORS = {code: CellError(code) for code in CellError.CODES}

Value = float | str | bool | CellError | None

_NUMBER_RE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


def parse_number(text: str) -> float | None:
    """The number ``text`` spells (surrounding whitespace allowed), else ``None``."""
    stripped = text.strip()
    if not _NUMBER_RE.fullmatch(stripped):
        return None
    x = float(stripped)
    if math.isinf(x):
        return None
    return x + 0.0  # normalise -0.0


def classify_literal(raw: str) -> Value:
    """The value of a non-formula raw string (``raw`` is non-empty)."""
    if raw[0] == "'":
        return raw[1:]
    x = parse_number(raw)
    if x is not None:
        return x
    upper = raw.strip().upper()
    if upper == "TRUE":
        return True
    if upper == "FALSE":
        return False
    return raw


def same_value(a: Value, b: Value) -> bool:
    """Equality as the change report defines it: same type and equal."""
    return type(a) is type(b) and a == b


def finite(x: float) -> float | CellError:
    """Normalise an arithmetic result: no inf/nan, no negative zero."""
    if math.isinf(x) or math.isnan(x):
        return VALUE
    return x + 0.0


def to_number(v: Value) -> float | CellError:
    if type(v) is float:
        return v
    if v is None:
        return 0.0
    if v is True:
        return 1.0
    if v is False:
        return 0.0
    if isinstance(v, CellError):
        return v
    x = parse_number(v)
    return VALUE if x is None else x


def format_number(x: float) -> str:
    if x == 0:
        return "0"
    return format(x, ".15g")


def to_text(v: Value) -> str | CellError:
    if type(v) is str:
        return v
    if v is None:
        return ""
    if v is True:
        return "TRUE"
    if v is False:
        return "FALSE"
    if isinstance(v, CellError):
        return v
    return format_number(v)


def to_bool(v: Value) -> bool | CellError:
    if type(v) is bool:
        return v
    if v is None:
        return False
    if type(v) is float:
        return v != 0
    if isinstance(v, CellError):
        return v
    folded = v.casefold()
    if folded == "true":
        return True
    if folded == "false":
        return False
    return VALUE


_COMPARISONS = {
    "=": operator.eq,
    "<>": operator.ne,
    "<": operator.lt,
    ">": operator.gt,
    "<=": operator.le,
    ">=": operator.ge,
}
_RANK = {float: 0, str: 1, bool: 2}
_EMPTY_AS = {float: 0.0, str: "", bool: False}


def compare(op: str, a: Value, b: Value) -> bool:
    """Excel-style comparison of two non-error values."""
    if a is None and b is None:
        a = b = 0.0
    elif a is None:
        a = _EMPTY_AS[type(b)]
    elif b is None:
        b = _EMPTY_AS[type(a)]
    ka, kb = _RANK[type(a)], _RANK[type(b)]
    if ka != kb:
        x, y = ka, kb
    elif ka == 1:
        x, y = a.casefold(), b.casefold()  # type: ignore[union-attr]
    else:
        x, y = a, b
    return _COMPARISONS[op](x, y)
