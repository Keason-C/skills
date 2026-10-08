"""gridcalc: an in-memory spreadsheet engine. See BRIEF.md.

The public API below is fixed: keep these names and signatures.

Reference implementation. Design summary:

* Cells are keyed by a single int ``(row << 14) | (col - 1)`` so that sorting
  keys gives row-major order.  ``_cells`` holds the raw input / compiled form,
  ``_val`` holds the computed (non-empty) values.
* Formulas are tokenised (recording the exact spans of reference tokens, used
  for byte-preserving rewriting), parsed with an iterative shunting-yard parser
  into a small AST, and compiled into a flat instruction list (with jumps for
  the lazy ``IF`` / ``IFERROR``) that is run by a non-recursive stack machine.
* Reverse dependencies: single references (and tiny ranges, expanded) live in
  ``_dep1``; larger ranges are bucketed into 64x8 tiles, huge ranges sit in a
  global list.  Recalculation collects the transitive dependents of the edited
  cells, orders them with Kahn's algorithm (with change cut-off), and runs an
  iterative Tarjan SCC pass over whatever is left (cycles and their dependents).
"""

from __future__ import annotations

import math
import re
from itertools import accumulate as _accumulate
from itertools import chain as _chain
from decimal import ROUND_HALF_UP, Context, Decimal, InvalidOperation, localcontext

__all__ = ["Sheet", "CellError"]


class CellError:
    """An error value stored in a cell. Compare by code."""

    __slots__ = ("code",)

    CODES = ("#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#CYCLE!", "#PARSE!")

    def __init__(self, code: str) -> None:
        if code not in self.CODES:
            raise ValueError(f"unknown error code: {code!r}")
        self.code = code

    def __eq__(self, other: object) -> bool:
        return isinstance(other, CellError) and other.code == self.code

    def __hash__(self) -> int:
        return hash(("CellError", self.code))

    def __repr__(self) -> str:
        return f"CellError({self.code!r})"


# ---------------------------------------------------------------------------
# constants / helpers
# ---------------------------------------------------------------------------

MAX_ROW = 1048576
MAX_COL = 16384
# key = ((col - 1) << 21) | row : consecutive rows of a column are consecutive
# ints (good dict hashing, contiguous column scans).  Row-major ordering is
# obtained with _rowmajor().
_RSH = 21
_RMASK = (1 << _RSH) - 1


def _mkkey(r: int, c: int) -> int:
    return ((c - 1) << _RSH) | r


def _rowmajor(k: int) -> int:
    return ((k & _RMASK) << 14) | (k >> _RSH)


def _E(code: str) -> CellError:
    return CellError(code)


E_DIV = _E("#DIV/0!")
E_VALUE = _E("#VALUE!")
E_REF = _E("#REF!")
E_NAME = _E("#NAME?")
E_CYCLE = _E("#CYCLE!")
E_PARSE = _E("#PARSE!")

_isfinite = math.isfinite

_COL_CACHE: dict[int, str] = {}


def _col_str(n: int) -> str:
    s = _COL_CACHE.get(n)
    if s is None:
        m = n
        out = ""
        while m:
            m, r = divmod(m - 1, 26)
            out = chr(65 + r) + out
        _COL_CACHE[n] = s = out
    return s


def _col_num(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch) - 64)
    return n


def _addr(key: int) -> str:
    return _col_str((key >> _RSH) + 1) + str(key & _RMASK)


_API_ADDR = re.compile(r"([A-Za-z]+)([0-9]+)")


def _parse_api_addr(addr) -> tuple[int, int]:
    if not isinstance(addr, str):
        raise ValueError(f"address must be a string: {addr!r}")
    m = _API_ADDR.fullmatch(addr)
    if not m:
        raise ValueError(f"malformed address: {addr!r}")
    letters, digits = m.groups()
    if len(letters) > 3 or len(digits) > 10:
        raise ValueError(f"address outside the grid: {addr!r}")
    c = _col_num(letters.upper())
    r = int(digits)
    if not (1 <= c <= MAX_COL and 1 <= r <= MAX_ROW):
        raise ValueError(f"address outside the grid: {addr!r}")
    return r, c


_NUM_RE = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")


def _to_number(s: str):
    """Number parsing shared by literal input and text->number coercion."""
    t = s.strip()
    if _NUM_RE.fullmatch(t):
        f = float(t)
        if _isfinite(f):
            return f
    return None


def _fmt(x: float) -> str:
    if x == 0:
        return "0"
    return format(x, ".15g")


class Rng:
    """A normalised rectangular range value (only ever lives on the eval stack)."""

    __slots__ = ("r1", "c1", "r2", "c2")

    def __init__(self, r1: int, c1: int, r2: int, c2: int) -> None:
        self.r1, self.c1, self.r2, self.c2 = r1, c1, r2, c2


# ---------------------------------------------------------------------------
# value coercions
# ---------------------------------------------------------------------------


def _num(v):
    """Arithmetic coercion -> float or CellError."""
    t = type(v)
    if t is float:
        return v
    if v is None:
        return 0.0
    if t is bool:
        return 1.0 if v else 0.0
    if t is str:
        f = _to_number(v)
        return E_VALUE if f is None else f
    if t is CellError:
        return v
    return E_VALUE  # range


def _text(v):
    """Text coercion -> str or CellError."""
    t = type(v)
    if t is str:
        return v
    if t is float:
        return _fmt(v)
    if v is None:
        return ""
    if t is bool:
        return "TRUE" if v else "FALSE"
    if t is CellError:
        return v
    return E_VALUE


def _truth(v):
    """Truthiness -> bool or CellError (decision 8)."""
    t = type(v)
    if t is bool:
        return v
    if t is float:
        return v != 0
    if v is None:
        return False
    if t is str:
        u = v.upper()
        if u == "TRUE":
            return True
        if u == "FALSE":
            return False
        return E_VALUE
    if t is CellError:
        return v
    return E_VALUE


def _fin(x: float):
    return x if _isfinite(x) else E_VALUE


# ---------------------------------------------------------------------------
# operators
# ---------------------------------------------------------------------------


def _op_add(a, b):
    if type(a) is float and type(b) is float:
        r = a + b
    else:
        x = _num(a)
        if type(x) is CellError:
            return x
        y = _num(b)
        if type(y) is CellError:
            return y
        r = x + y
    return r if _isfinite(r) else E_VALUE


def _op_sub(a, b):
    if type(a) is float and type(b) is float:
        r = a - b
    else:
        x = _num(a)
        if type(x) is CellError:
            return x
        y = _num(b)
        if type(y) is CellError:
            return y
        r = x - y
    return r if _isfinite(r) else E_VALUE


def _op_mul(a, b):
    x = _num(a)
    if type(x) is CellError:
        return x
    y = _num(b)
    if type(y) is CellError:
        return y
    r = x * y
    return r if _isfinite(r) else E_VALUE


def _op_div(a, b):
    x = _num(a)
    if type(x) is CellError:
        return x
    y = _num(b)
    if type(y) is CellError:
        return y
    if y == 0:
        return E_DIV
    r = x / y
    return r if _isfinite(r) else E_VALUE


def _op_pow(a, b):
    x = _num(a)
    if type(x) is CellError:
        return x
    y = _num(b)
    if type(y) is CellError:
        return y
    if x == 0:
        if y < 0:
            return E_DIV
        if y == 0:
            return 1.0
    if x < 0 and not y.is_integer():
        return E_VALUE
    try:
        r = math.pow(x, y)
    except (OverflowError, ValueError):
        return E_VALUE
    return r if _isfinite(r) else E_VALUE


def _op_cat(a, b):
    x = _text(a)
    if type(x) is CellError:
        return x
    y = _text(b)
    if type(y) is CellError:
        return y
    return x + y


_RANK = {float: 0, str: 1, bool: 2}
_EMPTY_AS = {float: 0.0, str: "", bool: False}


def _cmp(a, b):
    """Return -1/0/1 or a CellError (decision 2)."""
    ta = type(a)
    if ta is CellError:
        return a
    if ta is Rng:
        return E_VALUE
    tb = type(b)
    if tb is CellError:
        return b
    if tb is Rng:
        return E_VALUE
    if a is None:
        if b is None:
            return 0
        a = _EMPTY_AS[tb]
        ta = tb
    elif b is None:
        b = _EMPTY_AS[ta]
        tb = ta
    if ta is not tb:
        return -1 if _RANK[ta] < _RANK[tb] else 1
    if ta is str:
        a = a.lower()
        b = b.lower()
    return (a > b) - (a < b)


def _mk_cmp(pred):
    def f(a, b):
        c = _cmp(a, b)
        if type(c) is CellError:
            return c
        return pred(c)
    return f


_BINOPS = {
    "+": _op_add,
    "-": _op_sub,
    "*": _op_mul,
    "/": _op_div,
    "^": _op_pow,
    "&": _op_cat,
    "=": _mk_cmp(lambda c: c == 0),
    "<>": _mk_cmp(lambda c: c != 0),
    "<": _mk_cmp(lambda c: c < 0),
    ">": _mk_cmp(lambda c: c > 0),
    "<=": _mk_cmp(lambda c: c <= 0),
    ">=": _mk_cmp(lambda c: c >= 0),
}

_PREC = {"=": 1, "<>": 1, "<": 1, ">": 1, "<=": 1, ">=": 1,
         "&": 2, "+": 3, "-": 3, "*": 4, "/": 4, "^": 5}


def _neg(v):
    x = _num(v)
    if type(x) is CellError:
        return x
    return -x


# ---------------------------------------------------------------------------
# functions  (fn(sheet, args) -> value)
# ---------------------------------------------------------------------------


def _floats(vs):
    """Split range values into (floats, first_error_or_None)."""
    fl = [v for v in vs if type(v) is float]
    if len(fl) != len(vs):
        for v in vs:
            if type(v) is CellError:
                return fl, v
    return fl, None


def _numbers(sheet, args):
    """Collect the numbers for SUM/AVERAGE/MIN/MAX; returns (list, err)."""
    if len(args) == 1 and type(args[0]) is Rng:
        return _floats(sheet._rvals(args[0]))
    out = []
    for a in args:
        if type(a) is Rng:
            fl, err = _floats(sheet._rvals(a))
            if err is not None:
                return out, err
            out.extend(fl)
        else:
            x = _num(a)
            if type(x) is CellError:
                return out, x
            out.append(x)
    return out, None


def _seqsum(xs) -> float:
    """Plain left-to-right float addition (same as chaining '+')."""
    total = 0.0
    for total in _accumulate(xs, initial=0.0):
        pass
    return total


def _f_sum(sheet, args):
    xs, err = _numbers(sheet, args)
    if err is not None:
        return err
    return _fin(_seqsum(xs))


def _f_average(sheet, args):
    xs, err = _numbers(sheet, args)
    if err is not None:
        return err
    if not xs:
        return E_DIV
    total = _seqsum(xs)
    return _fin(total / len(xs)) if _isfinite(total) else E_VALUE


def _f_min(sheet, args):
    xs, err = _numbers(sheet, args)
    if err is not None:
        return err
    return min(xs) if xs else 0.0


def _f_max(sheet, args):
    xs, err = _numbers(sheet, args)
    if err is not None:
        return err
    return max(xs) if xs else 0.0


def _f_count(sheet, args):
    n = 0
    for a in args:
        if type(a) is Rng:
            fl, err = _floats(sheet._rvals(a))
            if err is not None:
                return err
            n += len(fl)
        else:
            if type(a) is CellError:
                return a
            if type(_num(a)) is float:
                n += 1
    return float(n)


def _logical(sheet, args, is_and):
    seen = 0
    acc = is_and
    for a in args:
        if type(a) is Rng:
            for v in sheet._rvals(a):
                t = type(v)
                if t is float:
                    b = v != 0
                elif t is bool:
                    b = v
                elif t is CellError:
                    return v
                else:  # text skipped
                    continue
                seen += 1
                if is_and:
                    acc = acc and b
                else:
                    acc = acc or b
        else:
            b = _truth(a)
            if type(b) is CellError:
                return b
            seen += 1
            if is_and:
                acc = acc and b
            else:
                acc = acc or b
    if not seen:
        return E_VALUE
    return acc


def _f_and(sheet, args):
    return _logical(sheet, args, True)


def _f_or(sheet, args):
    return _logical(sheet, args, False)


def _f_not(sheet, args):
    b = _truth(args[0])
    if type(b) is CellError:
        return b
    return not b


_DEC_CTX = Context(prec=2000, Emax=10**7, Emin=-(10**7))


def _f_round(sheet, args):
    x = _num(args[0])
    if type(x) is CellError:
        return x
    d = _num(args[1])
    if type(d) is CellError:
        return d
    d = int(d)  # truncate toward zero
    if d > 400:
        return x
    if d < -400:
        d = -400
    with localcontext(_DEC_CTX):
        try:
            q = Decimal(repr(x)).quantize(Decimal(1).scaleb(-d), rounding=ROUND_HALF_UP)
        except InvalidOperation:  # pragma: no cover - defensive
            return x
        r = float(q)
    return r if _isfinite(r) else E_VALUE


def _f_abs(sheet, args):
    x = _num(args[0])
    if type(x) is CellError:
        return x
    return abs(x)


def _f_len(sheet, args):
    s = _text(args[0])
    if type(s) is CellError:
        return s
    return float(len(s))


def _f_concat(sheet, args):
    parts = []
    for a in args:
        if type(a) is Rng:
            for v in sheet._rvals(a):
                s = _text(v)
                if type(s) is CellError:
                    return s
                parts.append(s)
        else:
            s = _text(a)
            if type(s) is CellError:
                return s
            parts.append(s)
    return "".join(parts)


# name -> (fn, min_args, max_args or None)
_FUNCS = {
    "SUM": (_f_sum, 1, None),
    "AVERAGE": (_f_average, 1, None),
    "MIN": (_f_min, 1, None),
    "MAX": (_f_max, 1, None),
    "COUNT": (_f_count, 1, None),
    "IF": (None, 2, 3),
    "IFERROR": (None, 2, 2),
    "AND": (_f_and, 1, None),
    "OR": (_f_or, 1, None),
    "NOT": (_f_not, 1, 1),
    "ROUND": (_f_round, 2, 2),
    "ABS": (_f_abs, 1, 1),
    "LEN": (_f_len, 1, 1),
    "CONCAT": (_f_concat, 1, None),
}


# ---------------------------------------------------------------------------
# tokenizer
# ---------------------------------------------------------------------------


class _ParseError(Exception):
    pass


K_VAL, K_REF, K_OP, K_LP, K_RP, K_COMMA, K_FUNC = range(7)

_NUM_TOK = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_WORD = re.compile(r"[A-Za-z_$][A-Za-z0-9_.$]*")
_ADDR = re.compile(r"(\$?)([A-Z]+)(\$?)([0-9]+)")
_ERR_CODES = sorted(CellError.CODES, key=len, reverse=True)
_ERR_OBJ = {c: _E(c) for c in CellError.CODES}
_OP2 = ("<>", "<=", ">=")
_OP1 = "=<>+-*/^&"


def _addr_parts(word_upper: str):
    """Return (cabs, col, rabs, row, valid) for an address-shaped word, else None."""
    m = _ADDR.fullmatch(word_upper)
    if not m:
        return None
    cabs, letters, rabs, digits = m.groups()
    valid = len(letters) <= 3 and len(digits) <= 10
    col = _col_num(letters) if valid else 0
    row = int(digits) if valid else 0
    valid = valid and 1 <= col <= MAX_COL and 1 <= row <= MAX_ROW
    return (cabs == "$", col, rabs == "$", row, valid)


def _tokenize(src: str, i: int):
    """Tokenise ``src`` from index ``i``.

    Returns (tokens, items).  ``items`` lists the reference tokens with their
    spans in ``src``:  ('c', ep)  or  ('r', ep1, ep2)  where
    ep = (start, end, col_abs, col, row_abs, row).
    """
    toks = []
    items = []
    n = len(src)
    while i < n:
        ch = src[i]
        if ch.isspace():
            i += 1
            continue
        if "0" <= ch <= "9" or (ch == "." and i + 1 < n and "0" <= src[i + 1] <= "9"):
            m = _NUM_TOK.match(src, i)
            f = float(m.group())
            toks.append((K_VAL, f if _isfinite(f) else E_VALUE))
            i = m.end()
            continue
        if ch == '"':
            j = i + 1
            parts = []
            while True:
                k = src.find('"', j)
                if k < 0:
                    raise _ParseError("unterminated string")
                parts.append(src[j:k])
                if k + 1 < n and src[k + 1] == '"':
                    parts.append('"')
                    j = k + 2
                    continue
                i = k + 1
                break
            toks.append((K_VAL, "".join(parts)))
            continue
        if ch == "#":
            for code in _ERR_CODES:
                if src[i:i + len(code)].upper() == code:
                    toks.append((K_VAL, _ERR_OBJ[code]))
                    i += len(code)
                    break
            else:
                raise _ParseError("bad error literal")
            continue
        if ("A" <= ch <= "Z") or ("a" <= ch <= "z") or ch == "_" or ch == "$":
            m = _WORD.match(src, i)
            w = m.group()
            j = m.end()
            k = j
            while k < n and src[k].isspace():
                k += 1
            if k < n and src[k] == "(":
                if "$" in w:
                    raise _ParseError("bad function name")
                toks.append((K_FUNC, w.upper()))
                i = k + 1
                continue
            u = w.upper()
            if u == "TRUE" or u == "FALSE":
                toks.append((K_VAL, u == "TRUE"))
                i = j
                continue
            p1 = _addr_parts(u)
            if p1 is None:
                raise _ParseError(f"unknown identifier {w!r}")
            ep1 = (i, j) + p1[:4]
            if k < n and src[k] == ":":
                k += 1
                while k < n and src[k].isspace():
                    k += 1
                m2 = _WORD.match(src, k)
                if not m2:
                    raise _ParseError("bad range")
                p2 = _addr_parts(m2.group().upper())
                if p2 is None:
                    raise _ParseError("bad range")
                ep2 = (k, m2.end()) + p2[:4]
                if p1[4] and p2[4]:
                    items.append(("r", ep1, ep2))
                    r1, r2 = (p1[3], p2[3]) if p1[3] <= p2[3] else (p2[3], p1[3])
                    c1, c2 = (p1[1], p2[1]) if p1[1] <= p2[1] else (p2[1], p1[1])
                    toks.append((K_VAL, Rng(r1, c1, r2, c2)))
                else:
                    toks.append((K_VAL, E_REF))
                i = m2.end()
                continue
            if p1[4]:
                items.append(("c", ep1))
                toks.append((K_REF, _mkkey(p1[3], p1[1])))
            else:
                toks.append((K_VAL, E_REF))
            i = j
            continue
        if ch == "(":
            toks.append((K_LP, None))
            i += 1
            continue
        if ch == ")":
            toks.append((K_RP, None))
            i += 1
            continue
        if ch == ",":
            toks.append((K_COMMA, None))
            i += 1
            continue
        two = src[i:i + 2]
        if two in _OP2:
            toks.append((K_OP, two))
            i += 2
            continue
        if ch in _OP1:
            toks.append((K_OP, ch))
            i += 1
            continue
        raise _ParseError(f"unexpected character {ch!r}")
    return toks, items


# ---------------------------------------------------------------------------
# parser (iterative shunting-yard -> AST)
#   AST: ('v', value) | ('r', key) | ('u', op, x) | ('b', op, a, b)
#        | ('f', NAME, [args])
# ---------------------------------------------------------------------------


def _reduce(ops, out):
    top = ops.pop()
    if top[0] == "U":
        x = out.pop()
        out.append(("u", top[1], x))
    else:
        b = out.pop()
        a = out.pop()
        out.append(("b", top[2], a, b))


def _parse(toks):
    out = []
    ops = []
    expect = True
    for kind, val in toks:
        if kind == K_VAL:
            if not expect:
                raise _ParseError("operand not expected")
            out.append(("v", val))
            expect = False
        elif kind == K_REF:
            if not expect:
                raise _ParseError("operand not expected")
            out.append(("r", val))
            expect = False
        elif kind == K_OP:
            if expect:
                if val == "+" or val == "-":
                    ops.append(("U", val))
                    continue
                raise _ParseError("operator not expected")
            p = _PREC[val]
            while ops:
                t = ops[-1][0]
                if t == "U" or (t == "B" and ops[-1][1] >= p):
                    _reduce(ops, out)
                else:
                    break
            ops.append(("B", p, val))
            expect = True
        elif kind == K_LP:
            if not expect:
                raise _ParseError("'(' not expected")
            ops.append(("(",))
        elif kind == K_FUNC:
            if not expect:
                raise _ParseError("function not expected")
            ops.append(("F", val, len(out)))
        elif kind == K_COMMA:
            if expect:
                raise _ParseError("empty argument")
            while ops and ops[-1][0] in ("U", "B"):
                _reduce(ops, out)
            if not ops or ops[-1][0] != "F":
                raise _ParseError("',' outside a function call")
            expect = True
        else:  # K_RP
            if expect:
                if ops and ops[-1][0] == "F" and len(out) == ops[-1][2]:
                    top = ops.pop()
                    out.append(("f", top[1], []))
                    expect = False
                    continue
                raise _ParseError("')' not expected")
            while ops and ops[-1][0] in ("U", "B"):
                _reduce(ops, out)
            if not ops:
                raise _ParseError("unbalanced ')'")
            top = ops.pop()
            if top[0] == "F":
                h = top[2]
                args = out[h:]
                del out[h:]
                out.append(("f", top[1], args))
    if expect:
        raise _ParseError("unexpected end of formula")
    while ops:
        if ops[-1][0] not in ("U", "B"):
            raise _ParseError("unbalanced '('")
        _reduce(ops, out)
    if len(out) != 1:  # pragma: no cover - defensive
        raise _ParseError("malformed expression")
    return out[0]


# ---------------------------------------------------------------------------
# compiler (AST -> flat code, iterative)
# ---------------------------------------------------------------------------

OP_CONST, OP_REF, OP_NEG, OP_POS, OP_BIN, OP_CALL, OP_IF, OP_JMP, OP_IFERR = range(9)


def _compile(ast):
    code = []
    work = [("n", ast)]
    while work:
        item = work.pop()
        tag = item[0]
        if tag == "n":
            node = item[1]
            t = node[0]
            if t == "v":
                code.append((OP_CONST, node[1], 0))
            elif t == "r":
                code.append((OP_REF, node[1], 0))
            elif t == "u":
                work.append(("i", (OP_NEG if node[1] == "-" else OP_POS, None, 0)))
                work.append(("n", node[2]))
            elif t == "b":
                work.append(("i", (OP_BIN, _BINOPS[node[1]], 0)))
                work.append(("n", node[3]))
                work.append(("n", node[2]))
            else:  # call
                name, args = node[1], node[2]
                spec = _FUNCS.get(name)
                if spec is None:
                    code.append((OP_CONST, E_NAME, 0))
                    continue
                fn, lo, hi = spec
                na = len(args)
                if na < lo or (hi is not None and na > hi):
                    code.append((OP_CONST, E_VALUE, 0))
                    continue
                if name == "IF":
                    h = [0, 0, 0]
                    els = args[2] if na == 3 else ("v", False)
                    work.append(("end_if", h))
                    work.append(("n", els))
                    work.append(("else", h))
                    work.append(("jmp", h))
                    work.append(("n", args[1]))
                    work.append(("if", h))
                    work.append(("n", args[0]))
                elif name == "IFERROR":
                    h = [0]
                    work.append(("end_iferr", h))
                    work.append(("n", args[1]))
                    work.append(("iferr", h))
                    work.append(("n", args[0]))
                else:
                    work.append(("i", (OP_CALL, fn, na)))
                    for a in reversed(args):
                        work.append(("n", a))
        elif tag == "i":
            code.append(item[1])
        elif tag == "if":
            item[1][0] = len(code)
            code.append(None)
        elif tag == "jmp":
            item[1][1] = len(code)
            code.append(None)
        elif tag == "else":
            item[1][2] = len(code)
        elif tag == "end_if":
            h = item[1]
            end = len(code)
            code[h[0]] = (OP_IF, h[2], end)
            code[h[1]] = (OP_JMP, end, 0)
        elif tag == "iferr":
            item[1][0] = len(code)
            code.append(None)
        else:  # end_iferr
            code[item[1][0]] = (OP_IFERR, len(code), 0)
    return tuple(code)


# ---------------------------------------------------------------------------
# cells
# ---------------------------------------------------------------------------


class _Cell:
    __slots__ = ("raw", "lit", "code", "items", "singles", "ranges", "maxr", "maxc")

    def __init__(self, raw, lit, code, items, singles, ranges):
        self.raw = raw
        self.lit = lit
        self.code = code
        self.items = items
        self.singles = singles
        self.ranges = ranges
        # largest row / column mentioned by a reference token (structural
        # edits strictly below / right of these cannot touch the text)
        mr = mc = 0
        if items:
            for it in items:
                for ep in it[1:]:
                    if ep[5] > mr:
                        mr = ep[5]
                    if ep[3] > mc:
                        mc = ep[3]
        self.maxr = mr
        self.maxc = mc


_PARSE_CODE = ((OP_CONST, E_PARSE, 0),)


def _make_cell(raw: str) -> _Cell:
    if raw[0] == "=":
        try:
            toks, items = _tokenize(raw, 1)
        except _ParseError:
            return _Cell(raw, None, _PARSE_CODE, None, (), ())
        try:
            code = _compile(_parse(toks))
        except _ParseError:
            return _Cell(raw, None, _PARSE_CODE, items, (), ())
        singles = set()
        ranges = set()
        for it in items:
            if it[0] == "c":
                ep = it[1]
                singles.add(_mkkey(ep[5], ep[3]))
            else:
                a, b = it[1], it[2]
                r1, r2 = (a[5], b[5]) if a[5] <= b[5] else (b[5], a[5])
                c1, c2 = (a[3], b[3]) if a[3] <= b[3] else (b[3], a[3])
                ranges.add((r1, c1, r2, c2))
        return _Cell(raw, None, code, items, tuple(singles), tuple(ranges))
    if raw[0] == "'":
        lit = raw[1:]
    else:
        lit = _to_number(raw)
        if lit is None:
            u = raw.upper()
            if u == "TRUE":
                lit = True
            elif u == "FALSE":
                lit = False
            else:
                lit = raw
    return _Cell(raw, lit, None, None, (), ())


def _ep_text(cabs: bool, col: int, rabs: bool, row: int) -> str:
    return ("$" if cabs else "") + _col_str(col) + ("$" if rabs else "") + str(row)


def _splice(raw: str, reps) -> str:
    if not reps:
        return raw
    reps.sort()
    out = []
    pos = 0
    for s, e, t in reps:
        out.append(raw[pos:s])
        out.append(t)
        pos = e
    out.append(raw[pos:])
    return "".join(out)


# dependency index tuning
_SMALL_AREA = 16
_TR = 6        # tile = 64 rows
_TC = 3        # x 8 columns
_MAX_TILES = 1024


def _tile(r: int, c: int) -> int:
    return ((r >> _TR) << 12) | ((c - 1) >> _TC)


def _bucket_keys(r1: int, c1: int, r2: int, c2: int):
    """Which bucket level / keys a (non-tiny) range is registered under."""
    tr1, tr2 = r1 >> _TR, r2 >> _TR
    tc1, tc2 = (c1 - 1) >> _TC, (c2 - 1) >> _TC
    ntc = tc2 - tc1 + 1
    if (tr2 - tr1 + 1) * ntc <= _MAX_TILES:
        return 0, [(tr << 12) | tc for tr in range(tr1, tr2 + 1) for tc in range(tc1, tc2 + 1)]
    if ntc <= 64:
        return 1, list(range(tc1, tc2 + 1))
    return 2, [0]


def _tarjan(nodes, succ):
    """Iterative Tarjan; returns SCCs in topological order (sources first)."""
    nodeset = set(nodes)
    index: dict = {}
    low: dict = {}
    onst: set = set()
    stk: list = []
    comps: list = []
    cnt = 0
    for root in nodes:
        if root in index:
            continue
        index[root] = low[root] = cnt
        cnt += 1
        stk.append(root)
        onst.add(root)
        work = [(root, iter(succ[root]))]
        while work:
            v, it = work[-1]
            descended = False
            for w in it:
                if w not in nodeset:
                    continue
                if w not in index:
                    index[w] = low[w] = cnt
                    cnt += 1
                    stk.append(w)
                    onst.add(w)
                    work.append((w, iter(succ[w])))
                    descended = True
                    break
                if w in onst and index[w] < low[v]:
                    low[v] = index[w]
            if descended:
                continue
            work.pop()
            if work:
                u = work[-1][0]
                if low[v] < low[u]:
                    low[u] = low[v]
            if low[v] == index[v]:
                comp = []
                while True:
                    w = stk.pop()
                    onst.discard(w)
                    comp.append(w)
                    if w == v:
                        break
                comps.append(comp)
    comps.reverse()
    return comps


def _same(a, b) -> bool:
    return type(a) is type(b) and a == b


# ---------------------------------------------------------------------------
# Sheet
# ---------------------------------------------------------------------------


class Sheet:
    def __init__(self) -> None:
        self._cells: dict[int, _Cell] = {}
        self._val: dict = {}
        self._dep1: dict[int, set] = {}
        # range buckets: [tiles (64x8), column strips (8 wide), global]
        self._rb: list[dict[int, set]] = [{}, {}, {}]

    # ----------------------------------------------------------------- API
    def set(self, addr: str, raw: str) -> list[str]:
        r, c = _parse_api_addr(addr)
        if not isinstance(raw, str):
            raise TypeError("raw must be a str")
        key = _mkkey(r, c)
        old = self._cells.get(key)
        if (old.raw if old is not None else "") == raw:
            return []
        self._assign(key, raw)
        return [_addr(k) for k in sorted(self._recalc([key]), key=_rowmajor)]

    def get(self, addr: str) -> float | str | bool | CellError | None:
        r, c = _parse_api_addr(addr)
        return self._val.get(_mkkey(r, c))

    def get_raw(self, addr: str) -> str:
        r, c = _parse_api_addr(addr)
        cell = self._cells.get(_mkkey(r, c))
        return cell.raw if cell is not None else ""

    def insert_rows(self, at: int, count: int = 1) -> None:
        self._structural(0, True, at, count)

    def delete_rows(self, at: int, count: int = 1) -> None:
        self._structural(0, False, at, count)

    def insert_cols(self, at: int, count: int = 1) -> None:
        self._structural(1, True, at, count)

    def delete_cols(self, at: int, count: int = 1) -> None:
        self._structural(1, False, at, count)

    def copy(self, src: str, dst: str) -> list[str]:
        if not isinstance(src, str):
            raise ValueError("source must be a string")
        parts = src.split(":")
        if len(parts) == 1:
            r1, c1 = _parse_api_addr(parts[0])
            r2, c2 = r1, c1
        elif len(parts) == 2:
            ra, ca = _parse_api_addr(parts[0])
            rb, cb = _parse_api_addr(parts[1])
            r1, r2 = min(ra, rb), max(ra, rb)
            c1, c2 = min(ca, cb), max(ca, cb)
        else:
            raise ValueError(f"malformed range: {src!r}")
        dr0, dc0 = _parse_api_addr(dst)
        if dr0 + (r2 - r1) > MAX_ROW or dc0 + (c2 - c1) > MAX_COL:
            raise ValueError("destination block leaves the grid")
        dr = dr0 - r1
        dc = dc0 - c1
        cells = self._cells
        area = (r2 - r1 + 1) * (c2 - c1 + 1)

        writes: dict[int, str] = {}
        if area <= 4 * len(cells) + 64:
            for r in range(r1, r2 + 1):
                for c in range(c1, c2 + 1):
                    cell = cells.get(_mkkey(r, c))
                    writes[_mkkey(r + dr, c + dc)] = (
                        self._shifted_raw(cell, dr, dc) if cell is not None else "")
        else:
            src_hit = []
            dst_hit = []
            for k in cells:
                r = k & _RMASK
                c = (k >> _RSH) + 1
                if r1 <= r <= r2 and c1 <= c <= c2:
                    src_hit.append(k)
                if r1 + dr <= r <= r2 + dr and c1 + dc <= c <= c2 + dc:
                    dst_hit.append(k)
            for k in dst_hit:
                writes[k] = ""
            for k in src_hit:
                r = k & _RMASK
                c = (k >> _RSH) + 1
                writes[_mkkey(r + dr, c + dc)] = self._shifted_raw(cells[k], dr, dc)

        seeds = []
        for k, raw in writes.items():
            old = cells.get(k)
            if (old.raw if old is not None else "") != raw:
                self._assign(k, raw)
                seeds.append(k)
        if not seeds:
            return []
        return [_addr(k) for k in sorted(self._recalc(seeds), key=_rowmajor)]

    # ------------------------------------------------------------ internals
    def _assign(self, key: int, raw: str) -> None:
        old = self._cells.get(key)
        if old is not None and old.code is not None:
            self._unregister(key, old)
        if raw == "":
            self._cells.pop(key, None)
            return
        cell = _make_cell(raw)
        self._cells[key] = cell
        if cell.code is not None:
            self._register(key, cell)

    def _register(self, fkey: int, cell: _Cell) -> None:
        dep1 = self._dep1
        for k in cell.singles:
            s = dep1.get(k)
            if s is None:
                dep1[k] = {fkey}
            else:
                s.add(fkey)
        for (r1, c1, r2, c2) in cell.ranges:
            if (r2 - r1 + 1) * (c2 - c1 + 1) <= _SMALL_AREA:
                for r in range(r1, r2 + 1):
                    for c in range(c1, c2 + 1):
                        k = _mkkey(r, c)
                        s = dep1.get(k)
                        if s is None:
                            dep1[k] = {fkey}
                        else:
                            s.add(fkey)
                continue
            ent = (r1, c1, r2, c2, fkey)
            level, bkeys = _bucket_keys(r1, c1, r2, c2)
            buckets = self._rb[level]
            for bk in bkeys:
                s = buckets.get(bk)
                if s is None:
                    buckets[bk] = {ent}
                else:
                    s.add(ent)

    def _unregister(self, fkey: int, cell: _Cell) -> None:
        dep1 = self._dep1
        for k in cell.singles:
            s = dep1.get(k)
            if s is not None:
                s.discard(fkey)
                if not s:
                    del dep1[k]
        for (r1, c1, r2, c2) in cell.ranges:
            if (r2 - r1 + 1) * (c2 - c1 + 1) <= _SMALL_AREA:
                for r in range(r1, r2 + 1):
                    for c in range(c1, c2 + 1):
                        k = _mkkey(r, c)
                        s = dep1.get(k)
                        if s is not None:
                            s.discard(fkey)
                            if not s:
                                del dep1[k]
                continue
            ent = (r1, c1, r2, c2, fkey)
            level, bkeys = _bucket_keys(r1, c1, r2, c2)
            buckets = self._rb[level]
            for bk in bkeys:
                s = buckets.get(bk)
                if s is not None:
                    s.discard(ent)
                    if not s:
                        del buckets[bk]

    def _rebuild_index(self) -> None:
        self._dep1 = {}
        self._rb = [{}, {}, {}]
        for k, cell in self._cells.items():
            if cell.code is not None:
                self._register(k, cell)

    def _dependents(self, key: int):
        s = self._dep1.get(key)
        rb = self._rb
        if not (rb[0] or rb[1] or rb[2]):
            return s if s is not None else ()
        r = key & _RMASK
        c = (key >> _RSH) + 1
        res = None
        for level, bk in ((0, _tile(r, c)), (1, (c - 1) >> _TC), (2, 0)):
            t = rb[level].get(bk)
            if t:
                for (r1, c1, r2, c2, f) in t:
                    if r1 <= r <= r2 and c1 <= c <= c2:
                        if res is None:
                            res = set(s) if s else set()
                        res.add(f)
        if res is None:
            return s if s is not None else ()
        return res

    def _rvals(self, g: Rng) -> list:
        """Non-empty values inside a range, row-major."""
        vals = self._val
        r1, c1, r2, c2 = g.r1, g.c1, g.r2, g.c2
        w = c2 - c1 + 1
        area = (r2 - r1 + 1) * w
        if area <= 64 or area <= 4 * len(vals):
            get = vals.get
            if w == 1:
                base = (c1 - 1) << _RSH
                seq = map(get, range(base | r1, (base | r2) + 1))
            else:
                # one contiguous C-level scan per column, zipped back to row-major
                seq = _chain.from_iterable(zip(*[
                    map(get, range((c << _RSH) | r1, ((c << _RSH) | r2) + 1))
                    for c in range(c1 - 1, c2)]))
            return [v for v in seq if v is not None]
        lo_c, hi_c = c1 - 1, c2 - 1
        ks = [k for k in vals
              if r1 <= (k & _RMASK) <= r2 and lo_c <= (k >> _RSH) <= hi_c]
        ks.sort(key=_rowmajor)
        return [vals[k] for k in ks]

    def _eval(self, code):
        get = self._val.get
        if len(code) == 1:
            op, a, _ = code[0]
            v = get(a) if op == OP_REF else a
        else:
            st = []
            push = st.append
            pc = 0
            n = len(code)
            while pc < n:
                op, a, b = code[pc]
                if op == OP_REF:
                    push(get(a))
                elif op == OP_CONST:
                    push(a)
                elif op == OP_BIN:
                    y = st.pop()
                    st[-1] = a(st[-1], y)
                elif op == OP_CALL:
                    cut = len(st) - b
                    args = st[cut:]
                    del st[cut:]
                    push(a(self, args))
                elif op == OP_NEG:
                    st[-1] = _neg(st[-1])
                elif op == OP_POS:
                    st[-1] = _num(st[-1])
                elif op == OP_IF:
                    t = _truth(st.pop())
                    if type(t) is CellError:
                        push(t)
                        pc = b
                    elif t:
                        pc += 1
                    else:
                        pc = a
                    continue
                elif op == OP_JMP:
                    pc = a
                    continue
                else:  # OP_IFERR
                    if type(st[-1]) is CellError:
                        st.pop()
                        pc += 1
                    else:
                        pc = a
                    continue
                pc += 1
            v = st[-1]
        if v is None:
            return 0.0
        if type(v) is Rng:
            return E_VALUE
        return v

    def _store(self, key: int, new) -> bool:
        vals = self._val
        old = vals.get(key)
        if new is None:
            if old is None:
                return False
            del vals[key]
            return True
        vals[key] = new
        return not _same(old, new)

    def _compute(self, key: int):
        cell = self._cells.get(key)
        if cell is None:
            return None
        if cell.code is None:
            return cell.lit
        return self._eval(cell.code)

    def _recalc(self, seeds) -> list[int]:
        """Recompute seeds and their transitive dependents; return changed keys."""
        # 1. collect the affected set with its (dependent) edges
        succ: dict = {}
        order = list(dict.fromkeys(seeds))
        seen = set(order)
        i = 0
        deps_of = self._dependents
        while i < len(order):
            k = order[i]
            i += 1
            ds = deps_of(k)
            succ[k] = ds
            for d in ds:
                if d not in seen:
                    seen.add(d)
                    order.append(d)
        changed = []
        if len(order) == 1:
            k = order[0]
            if k not in succ[k]:
                if self._store(k, self._compute(k)):
                    changed.append(k)
                return changed
        # 2. Kahn topological pass with change cut-off
        indeg = dict.fromkeys(order, 0)
        for k in order:
            for d in succ[k]:
                indeg[d] += 1
        # A node is recomputed when it is a seed, when one of its precedents
        # changed value, or when it currently holds #CYCLE! (it may have been a
        # cycle member whose cycle this edit broke: its inputs can be unchanged
        # while its value must change).
        need = set(seeds)
        ready = [k for k in order if indeg[k] == 0]
        done = 0
        store = self._store
        compute = self._compute
        vget = self._val.get
        while ready:
            k = ready.pop()
            done += 1
            ds = succ[k]
            if k in need or vget(k) == E_CYCLE:
                if store(k, compute(k)):
                    changed.append(k)
                    need.update(ds)
            for d in ds:
                indeg[d] -= 1
                if indeg[d] == 0:
                    ready.append(d)
        if done == len(order):
            return changed
        # 3. cycles (and everything downstream of them)
        rest = [k for k in order if indeg[k] > 0]
        for comp in _tarjan(rest, succ):
            if len(comp) > 1 or comp[0] in succ[comp[0]]:
                for k in comp:
                    if store(k, E_CYCLE):
                        changed.append(k)
            else:
                k = comp[0]
                if store(k, compute(k)):
                    changed.append(k)
        return changed

    # ------------------------------------------------------------- copy
    def _shifted_raw(self, cell: _Cell, dr: int, dc: int) -> str:
        raw = cell.raw
        items = cell.items
        if not items or (dr == 0 and dc == 0):
            return raw
        reps = []
        for it in items:
            if it[0] == "c":
                s, e, ca, col, ra, row = it[1]
                nc = col if ca else col + dc
                nr = row if ra else row + dr
                if not (1 <= nc <= MAX_COL and 1 <= nr <= MAX_ROW):
                    reps.append((s, e, "#REF!"))
                elif nc != col or nr != row:
                    reps.append((s, e, _ep_text(ca, nc, ra, nr)))
            else:
                eps = []
                ok = True
                for (s, e, ca, col, ra, row) in (it[1], it[2]):
                    nc = col if ca else col + dc
                    nr = row if ra else row + dr
                    if not (1 <= nc <= MAX_COL and 1 <= nr <= MAX_ROW):
                        ok = False
                        break
                    eps.append((s, e, ca, col, ra, row, nc, nr))
                if not ok:
                    reps.append((it[1][0], it[2][1], "#REF!"))
                    continue
                for (s, e, ca, col, ra, row, nc, nr) in eps:
                    if nc != col or nr != row:
                        reps.append((s, e, _ep_text(ca, nc, ra, nr)))
        return _splice(raw, reps)

    # ------------------------------------------------------- structural
    def _structural(self, axis: int, insert: bool, at, count) -> None:
        if isinstance(at, bool) or isinstance(count, bool) \
                or not isinstance(at, int) or not isinstance(count, int):
            raise ValueError("at and count must be integers")
        limit = MAX_ROW if axis == 0 else MAX_COL
        if not (1 <= at <= limit):
            raise ValueError(f"position out of range: {at}")
        if count < 0:
            raise ValueError(f"negative count: {count}")
        if count == 0:
            return

        if insert:
            a, n = at, count

            def mp(x):
                if x < a:
                    return x
                y = x + n
                return y if y <= limit else None

            def mr(lo, hi):
                if lo >= a:
                    lo2, hi2 = lo + n, hi + n
                elif hi >= a:
                    lo2, hi2 = lo, hi + n
                else:
                    return lo, hi
                if hi2 > limit:
                    return None
                return lo2, hi2
        else:
            a = at
            b = min(at + count - 1, limit)
            n = b - a + 1

            def mp(x):
                if x < a:
                    return x
                if x > b:
                    return x - n
                return None

            def mr(lo, hi):
                nlo = lo if lo < a else (b + 1 if lo <= b else lo)
                nhi = hi if hi > b else (a - 1 if hi >= a else hi)
                if nlo > nhi:
                    return None
                return mp(nlo), mp(nhi)

        if insert:
            def gone(x):
                return False

            def touched(lo, hi):          # range grows
                return lo < a <= hi
        else:
            def gone(x):
                return a <= x <= b

            def touched(lo, hi):          # range loses lines
                return not (b < lo or a > hi)

        row_axis = axis == 0
        # index into ep tuples: ep = (s, e, cabs, col, rabs, row)
        vi = 5 if row_axis else 3

        def retext(ep, nv):
            if row_axis:
                return _ep_text(ep[2], ep[3], ep[4], nv)
            return _ep_text(ep[2], nv, ep[4], ep[5])

        def new_ep(ep, ns, ne, nv):
            if row_axis:
                return (ns, ne, ep[2], ep[3], ep[4], nv)
            return (ns, ne, ep[2], nv, ep[4], ep[5])

        def shift_ep(ep, d):
            return ep if not d else (ep[0] + d, ep[1] + d) + ep[2:]

        def map_key(k):
            if row_axis:
                nr = mp(k & _RMASK)
                return None if nr is None else (k & ~_RMASK) | nr
            nc = mp((k >> _RSH) + 1)
            return None if nc is None else ((nc - 1) << _RSH) | (k & _RMASK)

        def map_rng(r1, c1, r2, c2):
            if row_axis:
                res = mr(r1, r2)
                return None if res is None else (res[0], c1, res[1], c2)
            res = mr(c1, c2)
            return None if res is None else (r1, res[0], r2, res[1])

        def rewrite(cell):
            """-> None if the text is unchanged, else (raw, items, impure).

            ``impure`` means the formula's meaning changed beyond a plain
            translation (a reference died or a range grew/shrank), so its value
            must be recomputed.
            """
            raw = cell.raw
            parts = []
            pos = 0
            delta = 0
            items = []
            impure = False
            for it in cell.items:
                if it[0] == "c":
                    ep = it[1]
                    old = ep[vi]
                    nv = mp(old)
                    if nv is None:
                        parts.append(raw[pos:ep[0]])
                        parts.append("#REF!")
                        pos = ep[1]
                        delta += 5 - (ep[1] - ep[0])
                        impure = True
                    elif nv != old:
                        t = retext(ep, nv)
                        parts.append(raw[pos:ep[0]])
                        parts.append(t)
                        pos = ep[1]
                        ns = ep[0] + delta
                        items.append(("c", new_ep(ep, ns, ns + len(t), nv)))
                        delta += len(t) - (ep[1] - ep[0])
                    else:
                        items.append(("c", shift_ep(ep, delta)) if delta else it)
                    continue
                e1, e2 = it[1], it[2]
                v1, v2 = e1[vi], e2[vi]
                lo, hi = (v1, v2) if v1 <= v2 else (v2, v1)
                res = mr(lo, hi)
                if res is None:
                    parts.append(raw[pos:e1[0]])
                    parts.append("#REF!")
                    pos = e2[1]
                    delta += 5 - (e2[1] - e1[0])
                    impure = True
                    continue
                if touched(lo, hi):
                    impure = True
                n1, n2 = res if v1 <= v2 else (res[1], res[0])
                eps = []
                # an endpoint is rewritten when its coordinate changes or when
                # its own line was deleted (it then moved to the nearest
                # surviving line inside the range, possibly the same number)
                for ep, old, nv in ((e1, v1, n1), (e2, v2, n2)):
                    if nv != old or gone(old):
                        t = retext(ep, nv)
                        parts.append(raw[pos:ep[0]])
                        parts.append(t)
                        pos = ep[1]
                        ns = ep[0] + delta
                        eps.append(new_ep(ep, ns, ns + len(t), nv))
                        delta += len(t) - (ep[1] - ep[0])
                    else:
                        eps.append(shift_ep(ep, delta))
                items.append(("r", eps[0], eps[1]))
            if not parts:
                return None
            parts.append(raw[pos:])
            return "".join(parts), items, impure

        def remap_code(code):
            out = []
            for ins in code:
                op = ins[0]
                if op == OP_REF:
                    nk = map_key(ins[1])
                    out.append((OP_CONST, E_REF, 0) if nk is None else (OP_REF, nk, 0))
                elif op == OP_CONST and type(ins[1]) is Rng:
                    g = ins[1]
                    t = map_rng(g.r1, g.c1, g.r2, g.c2)
                    out.append((OP_CONST, E_REF, 0) if t is None else (OP_CONST, Rng(*t), 0))
                else:
                    out.append(ins)
            return tuple(out)

        new_cells: dict[int, _Cell] = {}
        new_vals: dict = {}
        vals = self._val
        dirty = []
        for k, cell in self._cells.items():
            nk = map_key(k)
            if nk is None:
                continue
            if cell.items and (cell.maxr if row_axis else cell.maxc) >= a:
                res = rewrite(cell)
                if res is not None:
                    nraw, nitems, impure = res
                    singles = set()
                    for x in cell.singles:
                        y = map_key(x)
                        if y is not None:
                            singles.add(y)
                    ranges = set()
                    for t in cell.ranges:
                        y = map_rng(*t)
                        if y is not None:
                            ranges.add(y)
                    cell = _Cell(nraw, None, remap_code(cell.code), nitems,
                                 tuple(singles), tuple(ranges))
                    if impure:
                        dirty.append(nk)
            new_cells[nk] = cell
            v = vals.get(k)
            if v is not None:
                new_vals[nk] = v
        self._cells = new_cells
        self._val = new_vals
        self._rebuild_index()
        if dirty:
            self._recalc(dirty)
