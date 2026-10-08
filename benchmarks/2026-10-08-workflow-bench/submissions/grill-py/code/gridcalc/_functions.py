"""Built-in spreadsheet functions.

Each function receives its evaluated arguments as operands: plain values, or
coordinate tuples for references written directly in the call.
"""

from __future__ import annotations

from collections.abc import Callable
from decimal import (
    MAX_EMAX,
    MIN_EMIN,
    ROUND_HALF_UP,
    Context,
    Decimal,
    InvalidOperation,
)

from . import CellError
from ._operands import Operand, Reader, cells, scalar
from ._values import DIV0, VALUE, Value, finite, to_bool, to_number, to_text


def _numbers(args: list[Operand], reader: Reader) -> list[float] | CellError:
    """Numbers taking part in an aggregate: numbers from references, coerced scalars."""
    out: list[float] = []
    for arg in args:
        refs = cells(arg, reader)
        if refs is None:
            x = to_number(arg)  # type: ignore[arg-type]
            if type(x) is not float:
                return x  # type: ignore[return-value]
            out.append(x)  # type: ignore[arg-type]
            continue
        for v in refs:
            if type(v) is float:
                out.append(v)
            elif isinstance(v, CellError):
                return v
    return out


def _sum(args: list[Operand], reader: Reader) -> Value:
    nums = _numbers(args, reader)
    return nums if isinstance(nums, CellError) else finite(sum(nums))


def _average(args: list[Operand], reader: Reader) -> Value:
    nums = _numbers(args, reader)
    if isinstance(nums, CellError):
        return nums
    if not nums:
        return DIV0
    return finite(sum(nums) / len(nums))


def _extreme(
    pick: Callable[[list[float]], float],
) -> Callable[[list[Operand], Reader], Value]:
    def fn(args: list[Operand], reader: Reader) -> Value:
        nums = _numbers(args, reader)
        if isinstance(nums, CellError):
            return nums
        return pick(nums) if nums else 0.0

    return fn


def _count(args: list[Operand], reader: Reader) -> Value:
    n = 0
    for arg in args:
        refs = cells(arg, reader)
        if refs is None:
            if isinstance(arg, CellError):
                return arg
            if type(to_number(arg)) is float:  # type: ignore[arg-type]
                n += 1
            continue
        for v in refs:
            if type(v) is float:
                n += 1
            elif isinstance(v, CellError):
                return v
    return float(n)


def _logicals(args: list[Operand], reader: Reader) -> list[bool] | CellError:
    out: list[bool] = []
    for arg in args:
        refs = cells(arg, reader)
        if refs is None:
            b = to_bool(arg)  # type: ignore[arg-type]
            if type(b) is not bool:
                return b  # type: ignore[return-value]
            out.append(b)  # type: ignore[arg-type]
            continue
        for v in refs:
            if type(v) is bool:
                out.append(v)
            elif type(v) is float:
                out.append(v != 0)
            elif isinstance(v, CellError):
                return v
    return out


def _and(args: list[Operand], reader: Reader) -> Value:
    bools = _logicals(args, reader)
    if isinstance(bools, CellError):
        return bools
    return all(bools) if bools else VALUE


def _or(args: list[Operand], reader: Reader) -> Value:
    bools = _logicals(args, reader)
    if isinstance(bools, CellError):
        return bools
    return any(bools) if bools else VALUE


def _scalars(fn: Callable[..., Value]) -> Callable[[list[Operand], Reader], Value]:
    """Adapt ``fn`` to take only single values (references are read, ranges rejected)."""

    def wrapper(args: list[Operand], reader: Reader) -> Value:
        return fn(*(scalar(a, reader) for a in args))

    return wrapper


def _not(v: Value) -> Value:
    b = to_bool(v)
    return b if isinstance(b, CellError) else not b


def _round(v: Value, d: Value) -> Value:
    x = to_number(v)
    if isinstance(x, CellError):
        return x
    digits = to_number(d)
    if isinstance(digits, CellError):
        return digits
    places = int(digits)
    exact = Decimal(repr(x))
    if exact.as_tuple().exponent >= -places:  # type: ignore[operator]
        return x  # no digits beyond the requested position
    # Enough precision for every digit kept, however large the number.
    context = Context(
        prec=max(28, exact.adjusted() + places + 2), Emax=MAX_EMAX, Emin=MIN_EMIN
    )
    try:
        quantum = Decimal(1).scaleb(-places, context)
        rounded = exact.quantize(quantum, rounding=ROUND_HALF_UP, context=context)
    except InvalidOperation:  # rounding position far above the number
        return 0.0
    return finite(float(rounded))


def _abs(v: Value) -> Value:
    x = to_number(v)
    return x if isinstance(x, CellError) else abs(x)


def _len(v: Value) -> Value:
    t = to_text(v)
    return t if isinstance(t, CellError) else float(len(t))


def _concat(args: list[Operand], reader: Reader) -> Value:
    parts: list[str] = []
    for arg in args:
        refs = cells(arg, reader)
        for v in (arg,) if refs is None else refs:  # type: ignore[assignment]
            t = to_text(v)  # type: ignore[arg-type]
            if isinstance(t, CellError):
                return t
            parts.append(t)
    return "".join(parts)


LAZY = object()  # IF and IFERROR are compiled to jumps, not called

# name -> (implementation, min args, max args or None for unbounded)
FUNCTIONS: dict[str, tuple[object, int, int | None]] = {
    "SUM": (_sum, 1, None),
    "AVERAGE": (_average, 1, None),
    "MIN": (_extreme(min), 1, None),
    "MAX": (_extreme(max), 1, None),
    "COUNT": (_count, 1, None),
    "IF": (LAZY, 2, 3),
    "IFERROR": (LAZY, 2, 2),
    "AND": (_and, 1, None),
    "OR": (_or, 1, None),
    "NOT": (_scalars(_not), 1, 1),
    "ROUND": (_scalars(_round), 2, 2),
    "ABS": (_scalars(_abs), 1, 1),
    "LEN": (_scalars(_len), 1, 1),
    "CONCAT": (_concat, 1, None),
}
