"""Run compiled formula code against cell values."""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Context, Decimal, InvalidOperation
from typing import Callable, Iterable, Protocol

from . import CellError
from ._values import (
    DIV0,
    VALUE,
    checked,
    compare,
    to_bool,
    to_number,
    to_text,
)


class Range:
    """A range value on the evaluation stack (only functions accept it)."""

    __slots__ = ("r1", "c1", "r2", "c2")

    def __init__(self, r1: int, c1: int, r2: int, c2: int) -> None:
        self.r1, self.c1, self.r2, self.c2 = r1, c1, r2, c2


class Cells(Protocol):
    def value(self, row: int, col: int): ...

    def range_values(self, r1: int, c1: int, r2: int, c2: int) -> Iterable:
        """Non-empty values in the range, row-major."""
        ...


def evaluate(code: list, cells: Cells) -> float | str | bool | CellError:
    stack: list = []
    pc, n = 0, len(code)
    while pc < n:
        ins = code[pc]
        pc += 1
        op = ins[0]
        if op == "ref":
            stack.append(cells.value(ins[1], ins[2]))
        elif op == "const":
            stack.append(ins[1])
        elif op == "bin":
            b = stack.pop()
            stack.append(_binary(ins[1], stack.pop(), b))
        elif op == "range":
            stack.append(Range(ins[1], ins[2], ins[3], ins[4]))
        elif op == "unary":
            x = to_number(stack.pop())
            if type(x) is float and ins[1] == "-":
                x = -x + 0.0
            stack.append(x)
        elif op == "call":
            k = ins[2]
            args = stack[-k:]
            del stack[-k:]
            stack.append(FUNCTIONS[ins[1]](args, cells))
        elif op == "jump_if_false":
            cond = to_bool(stack.pop())
            if type(cond) is CellError:
                stack.append(cond)
                pc = ins[2]
            elif not cond:
                pc = ins[1]
        elif op == "jump":
            pc = ins[1]
        elif op == "jump_if_ok":
            top = stack[-1]
            if type(top) is Range:
                stack.pop()
            elif type(top) is not CellError:
                pc = ins[1]
            else:
                stack.pop()
        else:  # pragma: no cover
            raise AssertionError(op)
    result = stack[0]
    if result is None:
        return 0.0
    if type(result) is Range:
        return VALUE
    return result


def _binary(op: str, a, b):
    if type(a) is Range:
        a = VALUE
    if type(b) is Range:
        b = VALUE
    # Operands are coerced left to right; a coercion failure is that
    # operand's error, so the leftmost failing operand wins.
    if op in ("+", "-", "*", "/", "^"):
        x = to_number(a)
        if type(x) is CellError:
            return x
        y = to_number(b)
        if type(y) is CellError:
            return y
        if op == "+":
            return checked(x + y)
        if op == "-":
            return checked(x - y)
        if op == "*":
            return checked(x * y)
        if op == "/":
            return DIV0 if y == 0 else checked(x / y)
        return _power(x, y)
    if op == "&":
        x = to_text(a)
        if type(x) is CellError:
            return x
        y = to_text(b)
        if type(y) is CellError:
            return y
        return x + y
    if type(a) is CellError:
        return a
    if type(b) is CellError:
        return b
    return compare(op, a, b)


def _power(x: float, y: float):
    if x == 0 and y < 0:
        return DIV0
    try:
        r = x**y
    except OverflowError:
        return VALUE
    except ZeroDivisionError:
        return DIV0
    if type(r) is complex:
        return VALUE
    return checked(r)


# ---------------------------------------------------------------- functions


def _numbers(args, cells: Cells, counting: bool = False):
    """Numbers taking part in SUM-like functions, or the first error.

    Range cells contribute only numbers. Scalars are coerced like arithmetic
    operands; when `counting`, uncoercible scalars are skipped instead.
    """
    nums: list[float] = []
    for arg in args:
        if type(arg) is Range:
            values = cells.range_values(arg.r1, arg.c1, arg.r2, arg.c2)
            found = [v for v in values if type(v) is float]
            if len(found) != len(values):
                for v in values:
                    if type(v) is CellError:
                        return v
            nums.extend(found)
            continue
        if type(arg) is CellError:
            return arg
        x = to_number(arg)
        if type(x) is CellError:
            if counting:
                continue
            return x
        nums.append(x)
    return nums


def _sum(args, cells):
    nums = _numbers(args, cells)
    if type(nums) is CellError:
        return nums
    return checked(math.fsum(nums))


def _average(args, cells):
    nums = _numbers(args, cells)
    if type(nums) is CellError:
        return nums
    if not nums:
        return DIV0
    return checked(math.fsum(nums) / len(nums))


def _min(args, cells):
    nums = _numbers(args, cells)
    if type(nums) is CellError:
        return nums
    return min(nums) if nums else 0.0


def _max(args, cells):
    nums = _numbers(args, cells)
    if type(nums) is CellError:
        return nums
    return max(nums) if nums else 0.0


def _count(args, cells):
    nums = _numbers(args, cells, counting=True)
    if type(nums) is CellError:
        return nums
    return float(len(nums))


def _booleans(args, cells):
    """Booleans taking part in AND/OR, or the first error."""
    out: list[bool] = []
    for arg in args:
        if type(arg) is Range:
            for v in cells.range_values(arg.r1, arg.c1, arg.r2, arg.c2):
                t = type(v)
                if t is bool:
                    out.append(v)
                elif t is float:
                    out.append(v != 0)
                elif t is CellError:
                    return v
            continue
        b = to_bool(arg)
        if type(b) is CellError:
            return b
        out.append(b)
    return out


def _and(args, cells):
    bools = _booleans(args, cells)
    if type(bools) is CellError:
        return bools
    return all(bools) if bools else VALUE


def _or(args, cells):
    bools = _booleans(args, cells)
    if type(bools) is CellError:
        return bools
    return any(bools) if bools else VALUE


def _not(args, cells):
    b = to_bool(args[0])
    return b if type(b) is CellError else not b


def _round(args, cells):
    x = to_number(args[0])
    if type(x) is CellError:
        return x
    d = to_number(args[1])
    if type(d) is CellError:
        return d
    digits = int(d)  # truncates toward zero
    if digits > 300:
        return x
    if digits < -310:
        return 0.0
    ctx = Context(prec=400, rounding=ROUND_HALF_UP)
    try:
        q = Decimal(repr(x)).quantize(Decimal(1).scaleb(-digits, ctx), context=ctx)
    except InvalidOperation:
        return x
    return checked(float(q))


def _abs(args, cells):
    x = to_number(args[0])
    return x if type(x) is CellError else abs(x)


def _len(args, cells):
    s = to_text(args[0])
    return s if type(s) is CellError else float(len(s))


def _concat(args, cells):
    parts: list[str] = []
    for arg in args:
        if type(arg) is Range:
            values = cells.range_values(arg.r1, arg.c1, arg.r2, arg.c2)
        else:
            values = (arg,)
        for v in values:
            s = to_text(v)
            if type(s) is CellError:
                return s
            parts.append(s)
    return "".join(parts)


FUNCTIONS: dict[str, Callable] = {
    "SUM": _sum,
    "AVERAGE": _average,
    "MIN": _min,
    "MAX": _max,
    "COUNT": _count,
    "AND": _and,
    "OR": _or,
    "NOT": _not,
    "ROUND": _round,
    "ABS": _abs,
    "LEN": _len,
    "CONCAT": _concat,
}
