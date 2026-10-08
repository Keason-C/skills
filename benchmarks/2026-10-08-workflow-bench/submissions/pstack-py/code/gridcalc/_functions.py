from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal, localcontext
from typing import Callable, NamedTuple

from ._errors import DIV0, VALUE, CellError
from ._values import Context, Value, finite, to_bool, to_number, to_text


class Function(NamedTuple):
    min_args: int
    max_args: float
    impl: Callable[[list, Context], Value]


def _numbers(args, ctx, *, skip_uncoercible: bool = False) -> list[float] | CellError:
    out = []
    for arg in args:
        if arg.rect is not None:
            for v in ctx.iter_rect(arg.rect):
                if type(v) is float:
                    out.append(v)
                elif isinstance(v, CellError):
                    return v
            continue
        v = arg.eval(ctx)
        if isinstance(v, CellError):
            return v
        n = to_number(v)
        if isinstance(n, CellError):
            if skip_uncoercible:
                continue
            return n
        out.append(n)
    return out


def _aggregate(reduce: Callable[[list[float]], Value], *, skip_uncoercible: bool = False):
    def impl(args, ctx):
        numbers = _numbers(args, ctx, skip_uncoercible=skip_uncoercible)
        if isinstance(numbers, CellError):
            return numbers
        result = reduce(numbers)
        return finite(result) if type(result) is float else result

    return impl


def _logical(reduce: Callable[[list[bool]], bool]):
    def impl(args, ctx):
        flags = []
        for arg in args:
            if arg.rect is not None:
                for v in ctx.iter_rect(arg.rect):
                    if isinstance(v, CellError):
                        return v
                    if type(v) is not str:
                        flags.append(to_bool(v))
                continue
            flag = to_bool(arg.eval(ctx))
            if isinstance(flag, CellError):
                return flag
            flags.append(flag)
        return reduce(flags) if flags else VALUE

    return impl


def _if(args, ctx):
    cond = to_bool(args[0].eval(ctx))
    if isinstance(cond, CellError):
        return cond
    if cond:
        return args[1].eval(ctx)
    return args[2].eval(ctx) if len(args) == 3 else False


def _iferror(args, ctx):
    v = args[0].eval(ctx)
    return args[1].eval(ctx) if isinstance(v, CellError) else v


def _not(args, ctx):
    flag = to_bool(args[0].eval(ctx))
    return flag if isinstance(flag, CellError) else not flag


def _round(args, ctx):
    x = to_number(args[0].eval(ctx))
    if isinstance(x, CellError):
        return x
    digits = to_number(args[1].eval(ctx))
    if isinstance(digits, CellError):
        return digits
    digits = max(-400, min(400, math.trunc(digits)))
    # Excel rounds half away from zero on the decimal shown, so 2.675 -> 2.68.
    with localcontext(prec=1000):
        rounded = Decimal(repr(x)).quantize(Decimal(1).scaleb(-digits), ROUND_HALF_UP)
    return float(rounded)


def _abs(args, ctx):
    x = to_number(args[0].eval(ctx))
    return x if isinstance(x, CellError) else abs(x)


def _len(args, ctx):
    text = to_text(args[0].eval(ctx))
    return text if isinstance(text, CellError) else float(len(text))


def _concat(args, ctx):
    parts = []
    for arg in args:
        values = ctx.iter_rect(arg.rect) if arg.rect is not None else (arg.eval(ctx),)
        for v in values:
            text = to_text(v)
            if isinstance(text, CellError):
                return text
            parts.append(text)
    return "".join(parts)


_ANY = math.inf

FUNCTIONS: dict[str, Function] = {
    "SUM": Function(1, _ANY, _aggregate(lambda xs: float(sum(xs)))),
    "AVERAGE": Function(1, _ANY, _aggregate(lambda xs: sum(xs) / len(xs) if xs else DIV0)),
    "MIN": Function(1, _ANY, _aggregate(lambda xs: min(xs, default=0.0))),
    "MAX": Function(1, _ANY, _aggregate(lambda xs: max(xs, default=0.0))),
    "COUNT": Function(1, _ANY, _aggregate(lambda xs: float(len(xs)), skip_uncoercible=True)),
    "IF": Function(2, 3, _if),
    "AND": Function(1, _ANY, _logical(all)),
    "OR": Function(1, _ANY, _logical(any)),
    "NOT": Function(1, 1, _not),
    "IFERROR": Function(2, 2, _iferror),
    "ROUND": Function(2, 2, _round),
    "ABS": Function(1, 1, _abs),
    "LEN": Function(1, 1, _len),
    "CONCAT": Function(1, _ANY, _concat),
}
