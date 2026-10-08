from __future__ import annotations

import math
import operator
import re
from collections.abc import Iterable
from typing import Protocol

from ._errors import DIV0, VALUE, CellError
from ._grid import Rect

Value = float | str | bool | CellError | None


class Context(Protocol):
    def value(self, row: int, col: int) -> Value: ...

    def iter_rect(self, rect: Rect) -> Iterable[Value]: ...

_NUMBER_RE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


def parse_number(text: str) -> float | None:
    text = text.strip()
    if not _NUMBER_RE.fullmatch(text):
        return None
    number = float(text)
    return number if math.isfinite(number) else None


def parse_literal(raw: str) -> Value:
    if raw.startswith("'"):
        return raw[1:]
    number = parse_number(raw)
    if number is not None:
        return number
    word = raw.strip().upper()
    if word == "TRUE":
        return True
    if word == "FALSE":
        return False
    return raw


def same(a: Value, b: Value) -> bool:
    return type(a) is type(b) and a == b


def finite(x: float) -> float | CellError:
    return x if math.isfinite(x) else VALUE


def to_number(v: Value) -> float | CellError:
    t = type(v)
    if t is float:
        return v
    if t is bool:
        return 1.0 if v else 0.0
    if v is None:
        return 0.0
    if t is str:
        number = parse_number(v)
        return VALUE if number is None else number
    return v


def to_text(v: Value) -> str | CellError:
    t = type(v)
    if t is str:
        return v
    if t is float:
        return "0" if v == 0 else format(v, ".15g")
    if t is bool:
        return "TRUE" if v else "FALSE"
    if v is None:
        return ""
    return v


def to_bool(v: Value) -> bool | CellError:
    t = type(v)
    if t is bool:
        return v
    if t is float:
        return v != 0
    if v is None:
        return False
    if t is str:
        word = v.upper()
        if word == "TRUE":
            return True
        if word == "FALSE":
            return False
        return VALUE
    return v


def _divide(a: float, b: float) -> float | CellError:
    return DIV0 if b == 0 else a / b


def _power(a: float, b: float) -> float | CellError:
    if a == 0 and b < 0:
        return DIV0
    try:
        result = a**b
    except OverflowError:
        return VALUE
    return VALUE if isinstance(result, complex) else result


_ARITHMETIC = {
    "+": operator.add,
    "-": operator.sub,
    "*": operator.mul,
    "/": _divide,
    "^": _power,
}

_RANK = {float: 0, str: 1, bool: 2}
_EMPTY_AS = {float: 0.0, str: "", bool: False}


def _compare(a: Value, b: Value) -> int:
    if a is None:
        a = _EMPTY_AS[type(b)] if b is not None else 0.0
    if b is None:
        b = _EMPTY_AS[type(a)]
    ra, rb = _RANK[type(a)], _RANK[type(b)]
    if ra != rb:
        return -1 if ra < rb else 1
    if ra == 1:
        a, b = a.lower(), b.lower()
    return (a > b) - (a < b)


_COMPARISONS = {
    "=": lambda c: c == 0,
    "<>": lambda c: c != 0,
    "<": lambda c: c < 0,
    ">": lambda c: c > 0,
    "<=": lambda c: c <= 0,
    ">=": lambda c: c >= 0,
}


def binary(op: str, a: Value, b: Value) -> Value:
    if isinstance(a, CellError):
        return a
    if isinstance(b, CellError):
        return b
    if op == "&":
        return to_text(a) + to_text(b)
    if op in _COMPARISONS:
        return _COMPARISONS[op](_compare(a, b))
    a = to_number(a)
    if isinstance(a, CellError):
        return a
    b = to_number(b)
    if isinstance(b, CellError):
        return b
    result = _ARITHMETIC[op](a, b)
    return result if isinstance(result, CellError) else finite(result)


def unary(op: str, v: Value) -> Value:
    v = to_number(v)
    if isinstance(v, CellError) or op == "+":
        return v
    return -v
