"""Formula text -> tokens -> AST -> flat code.

Everything here is iterative (shunting-yard parsing, explicit-stack compilation)
so arbitrarily deep nesting cannot raise RecursionError.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from . import CellError
from ._address import col_to_num, in_grid
from ._values import NAME, PARSE, REF, VALUE

# ---------------------------------------------------------------- tokens

_TOKEN_RE = re.compile(
    r"""
      (?P<ws>\s+)
    | (?P<str>"(?:[^"]|"")*")
    | (?P<err>\#(?:DIV/0!|VALUE!|REF!|NAME\?|CYCLE!|PARSE!))
    | (?P<num>(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)
    | (?P<ref>
        (?P<a>(?P<a_cabs>\$?)(?P<a_col>[A-Za-z]{1,3})(?P<a_rabs>\$?)(?P<a_row>[0-9]+))
        (?:\s*:\s*
        (?P<b>(?P<b_cabs>\$?)(?P<b_col>[A-Za-z]{1,3})(?P<b_rabs>\$?)(?P<b_row>[0-9]+)))?
        (?![A-Za-z0-9_.(\$])
      )
    | (?P<ident>[A-Za-z_][A-Za-z0-9_.]*)
    | (?P<op><>|<=|>=|[=<>&+\-*/^])
    | (?P<punct>[(),])
    """,
    re.VERBOSE | re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class Endpoint:
    """One corner of a reference as written: coordinates plus `$` markers."""

    row: int
    col: int
    row_abs: bool
    col_abs: bool


@dataclass(slots=True)
class Token:
    kind: str  # num str bool err ref func name op ( ) ,
    start: int
    end: int
    value: object = None
    # for kind == "ref": one endpoint (single cell) or two (range), and the
    # (start, end) text span of each endpoint
    ends: tuple[Endpoint, ...] = ()
    spans: tuple[tuple[int, int], ...] = ()


def _endpoint(m: re.Match, p: str) -> Endpoint:
    return Endpoint(int(m[p + "_row"]), col_to_num(m[p + "_col"]), m[p + "_rabs"] == "$", m[p + "_cabs"] == "$")


def tokenize(text: str, offset: int = 0, lenient: bool = False) -> tuple[list[Token], bool]:
    """Tokenize formula body `text`. Returns (tokens, ok). On an unreadable
    character, stops with ok=False, or with `lenient` skips the character
    (so references after it are still found). Positions are shifted by
    `offset` so they index into the full raw string."""
    tokens: list[Token] = []
    ok = True
    i, n = 0, len(text)
    match = _TOKEN_RE.match
    while i < n:
        m = match(text, i)
        if m is None:
            if not lenient:
                return tokens, False
            ok = False
            i += 1
            continue
        kind = m.lastgroup
        j = m.end()
        start, end = i + offset, j + offset
        if kind == "ws":
            pass
        elif kind == "ref":
            if m["b"] is None:
                tokens.append(Token("ref", start, end, None, (_endpoint(m, "a"),), ((start, end),)))
            else:
                spans = ((start, m.end("a") + offset), (m.start("b") + offset, end))
                tokens.append(Token("ref", start, end, None, (_endpoint(m, "a"), _endpoint(m, "b")), spans))
        elif kind == "op":
            tokens.append(Token("op", start, end, m.group()))
        elif kind == "punct":
            tokens.append(Token(m.group(), start, end))
        elif kind == "num":
            tokens.append(Token("num", start, end, float(m.group())))
        elif kind == "str":
            tokens.append(Token("str", start, end, m.group()[1:-1].replace('""', '"')))
        elif kind == "err":
            tokens.append(Token("err", start, end, m.group().upper()))
        else:  # identifier: function name, boolean or unknown name
            word = m.group().upper()
            k = j
            while k < n and text[k].isspace():
                k += 1
            if k < n and text[k] == "(":
                j = k + 1
                tokens.append(Token("func", start, j + offset, word))
            elif word in ("TRUE", "FALSE"):
                tokens.append(Token("bool", start, end, word == "TRUE"))
            else:
                tokens.append(Token("name", start, end, word))
        i = j
    return tokens, ok


# ---------------------------------------------------------------- parsing

_BINARY_PREC = {"=": 1, "<>": 1, "<": 1, ">": 1, "<=": 1, ">=": 1, "&": 2, "+": 3, "-": 3, "*": 4, "/": 4, "^": 5}
_UNARY_PREC = 6


class ParseError(Exception):
    pass


def _ref_node(tok: Token):
    """AST node for a reference token; ranges are normalised top-left first."""
    if any(not in_grid(e.row, e.col) for e in tok.ends):
        return ("const", REF)
    if len(tok.ends) == 1:
        e = tok.ends[0]
        return ("ref", e.row, e.col)
    a, b = tok.ends
    return ("range", min(a.row, b.row), min(a.col, b.col), max(a.row, b.row), max(a.col, b.col))


def parse(text: str):
    """Parse a formula body (without the leading '=') into an AST.

    AST nodes are tuples: ("const", value), ("ref", r, c),
    ("range", r1, c1, r2, c2), ("unary", op, x), ("bin", op, a, b),
    ("call", NAME, [args]). Raises ParseError.
    """
    tokens, ok = tokenize(text)
    if not ok or not tokens:
        raise ParseError
    out: list = []
    ops: list = []  # ("bin", op) | ("unary", op) | ("paren",) | ["func", name, nargs]
    expect_operand = True

    def reduce_top():
        item = ops.pop()
        if item[0] == "bin":
            b = out.pop()
            a = out.pop()
            out.append(("bin", item[1], a, b))
        else:
            out.append(("unary", item[1], out.pop()))

    for tok in tokens:
        kind = tok.kind
        if kind in ("num", "str", "bool", "err", "ref", "name"):
            if not expect_operand:
                raise ParseError
            if kind == "ref":
                out.append(_ref_node(tok))
            elif kind == "err":
                out.append(("const", CellError(tok.value)))
            elif kind == "name":
                out.append(("const", NAME))
            elif kind == "num" and tok.value == float("inf"):
                out.append(("const", VALUE))
            else:
                out.append(("const", tok.value))
            expect_operand = False
        elif kind == "op":
            op = tok.value
            if expect_operand:
                if op not in ("+", "-"):
                    raise ParseError
                ops.append(("unary", op))
                continue
            prec = _BINARY_PREC[op]
            while ops and ops[-1][0] in ("bin", "unary"):
                top_prec = _UNARY_PREC if ops[-1][0] == "unary" else _BINARY_PREC[ops[-1][1]]
                if top_prec < prec:
                    break
                reduce_top()
            ops.append(("bin", op))
            expect_operand = True
        elif kind == "(":
            if not expect_operand:
                raise ParseError
            ops.append(("paren",))
        elif kind == "func":
            if not expect_operand:
                raise ParseError
            ops.append(["func", tok.value, 0, len(out)])
        elif kind == ",":
            if expect_operand:
                raise ParseError
            while ops and ops[-1][0] in ("bin", "unary"):
                reduce_top()
            if not ops or ops[-1][0] != "func":
                raise ParseError
            ops[-1][2] += 1
            expect_operand = True
        else:  # ")"
            if expect_operand:
                # only an empty argument list, e.g. SUM(), may close here
                if not (ops and ops[-1][0] == "func" and ops[-1][2] == 0):
                    raise ParseError
                _, name, _, _ = ops.pop()
                out.append(("call", name, []))
                expect_operand = False
                continue
            while ops and ops[-1][0] in ("bin", "unary"):
                reduce_top()
            if not ops:
                raise ParseError
            top = ops.pop()
            if top[0] == "func":
                _, name, nargs, base = top
                args = out[base:]
                del out[base:]
                if len(args) != nargs + 1:
                    raise ParseError
                out.append(("call", name, args))
    if expect_operand:
        raise ParseError
    while ops:
        if ops[-1][0] not in ("bin", "unary"):
            raise ParseError
        reduce_top()
    if len(out) != 1:
        raise ParseError
    return out[0]


# ---------------------------------------------------------------- compiling

# name -> (min args, max args or None)
ARITY = {
    "SUM": (1, None),
    "AVERAGE": (1, None),
    "MIN": (1, None),
    "MAX": (1, None),
    "COUNT": (1, None),
    "IF": (2, 3),
    "AND": (1, None),
    "OR": (1, None),
    "NOT": (1, 1),
    "IFERROR": (2, 2),
    "ROUND": (2, 2),
    "ABS": (1, 1),
    "LEN": (1, 1),
    "CONCAT": (1, None),
}

_AGGREGATES = frozenset({"SUM", "AVERAGE", "MIN", "MAX", "COUNT"})


@dataclass(slots=True)
class Formula:
    """A compiled formula and its static dependencies."""

    code: list = field(default_factory=list)
    parsed: bool = True
    refs: list[tuple[int, int]] = field(default_factory=list)
    ranges: list[tuple[int, int, int, int]] = field(default_factory=list)


def _collect_deps(root, formula: Formula) -> None:
    stack = [root]
    while stack:
        node = stack.pop()
        t = node[0]
        if t == "ref":
            formula.refs.append((node[1], node[2]))
        elif t == "range":
            formula.ranges.append(node[1:])
        elif t == "unary":
            stack.append(node[2])
        elif t == "bin":
            stack.append(node[2])
            stack.append(node[3])
        elif t == "call":
            stack.extend(node[2])


def compile_formula(body: str) -> Formula:
    """Compile a formula body (text after '=')."""
    formula = Formula()
    try:
        root = parse(body)
    except ParseError:
        formula.code = [("const", PARSE)]
        formula.parsed = False
        return formula
    _collect_deps(root, formula)
    formula.refs = list(dict.fromkeys(formula.refs))
    formula.ranges = list(dict.fromkeys(formula.ranges))

    code: list = []
    labels: dict[int, int] = {}
    next_label = 0
    stack: list = [("node", root)]
    while stack:
        item = stack.pop()
        if item[0] == "emit":
            code.append(item[1])
            continue
        if item[0] == "label":
            labels[item[1]] = len(code)
            continue
        node = item[1]
        t = node[0]
        if t in ("const", "ref", "range"):
            code.append(node)
            continue
        if t == "unary":
            seq = [("node", node[2]), ("emit", ("unary", node[1]))]
        elif t == "bin":
            seq = [("node", node[2]), ("node", node[3]), ("emit", ("bin", node[1]))]
        else:
            name, args = node[1], node[2]
            arity = ARITY.get(name)
            if arity is None:
                code.append(("const", NAME))
                continue
            lo, hi = arity
            if len(args) < lo or (hi is not None and len(args) > hi):
                code.append(("const", VALUE))
                continue
            if name == "IF":
                l_else, l_end = next_label, next_label + 1
                next_label += 2
                else_part = ("node", args[2]) if len(args) == 3 else ("emit", ("const", False))
                seq = [
                    ("node", args[0]),
                    ("emit", ("jump_if_false", l_else, l_end)),
                    ("node", args[1]),
                    ("emit", ("jump", l_end)),
                    ("label", l_else),
                    else_part,
                    ("label", l_end),
                ]
            elif name == "IFERROR":
                l_end = next_label
                next_label += 1
                seq = [
                    ("node", args[0]),
                    ("emit", ("jump_if_ok", l_end)),
                    ("node", args[1]),
                    ("label", l_end),
                ]
            else:
                if name in _AGGREGATES:
                    # a single reference argument behaves like a 1-cell range
                    args = [("range", a[1], a[2], a[1], a[2]) if a[0] == "ref" else a for a in args]
                seq = [("node", a) for a in args]
                seq.append(("emit", ("call", name, len(args))))
        stack.extend(reversed(seq))

    for i, ins in enumerate(code):
        if ins[0] == "jump_if_false":
            code[i] = (ins[0], labels[ins[1]], labels[ins[2]])
        elif ins[0] in ("jump", "jump_if_ok"):
            code[i] = (ins[0], labels[ins[1]])
    formula.code = code
    return formula
