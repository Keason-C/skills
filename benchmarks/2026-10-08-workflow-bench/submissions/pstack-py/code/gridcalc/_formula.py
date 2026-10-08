from __future__ import annotations

import re
from functools import lru_cache
from typing import Callable, NamedTuple

from ._errors import NAME, PARSE, VALUE, CellError
from ._functions import FUNCTIONS
from ._grid import Addr, Rect, col_letters, in_grid, letters_col
from ._values import Context, Value, binary, finite, unary


class Ref(NamedTuple):
    row: int
    col: int
    row_abs: bool
    col_abs: bool

    def text(self) -> str:
        col_mark = "$" if self.col_abs else ""
        row_mark = "$" if self.row_abs else ""
        return f"{col_mark}{col_letters(self.col)}{row_mark}{self.row}"


def order_corners(a: Ref, b: Ref) -> tuple[Ref, Ref]:
    top, bottom = sorted([(a.row, a.row_abs), (b.row, b.row_abs)], key=lambda p: p[0])
    left, right = sorted([(a.col, a.col_abs), (b.col, b.col_abs)], key=lambda p: p[0])
    return Ref(top[0], left[0], top[1], left[1]), Ref(bottom[0], right[0], bottom[1], right[1])


class Token(NamedTuple):
    kind: str
    start: int
    end: int
    value: object = None


_WS_RE = re.compile(r"\s+")
_NUMBER_RE = re.compile(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?")
_STRING_RE = re.compile(r'"((?:[^"]|"")*)"')
_REF_RE = re.compile(r"(\$?)([A-Za-z]{1,3})(\$?)([1-9][0-9]*)(?![A-Za-z0-9_.(])")
_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_.]*")
_ERROR_RE = re.compile("|".join(re.escape(code) for code in CellError.CODES), re.IGNORECASE)
_DIGITS = frozenset("0123456789")
_OPERATORS = ("<=", ">=", "<>", "=", "<", ">", "&", "+", "-", "*", "/", "^")
_PUNCTUATION = {"(": "(", ")": ")", ",": ","}


def _match_ref(text: str, pos: int) -> tuple[Ref, int] | None:
    m = _REF_RE.match(text, pos)
    if m is None:
        return None
    ref = Ref(int(m[4]), letters_col(m[2]), bool(m[3]), bool(m[1]))
    return (ref, m.end()) if in_grid(ref.row, ref.col) else None


def _lex_word(text: str, pos: int) -> Token:
    hit = _match_ref(text, pos)
    if hit is not None:
        first, end = hit
        if end < len(text) and text[end] == ":":
            second = _match_ref(text, end + 1)
            if second is not None:
                return Token("range", pos, second[1], order_corners(first, second[0]))
        return Token("ref", pos, end, first)
    m = _NAME_RE.match(text, pos)
    if m is None:
        return Token("bad", pos, pos + 1)
    name, end = m[0].upper(), m.end()
    if end < len(text) and text[end] == "(":
        return Token("func", pos, end, name)
    if name in ("TRUE", "FALSE"):
        return Token("const", pos, end, name == "TRUE")
    return Token("name", pos, end, name)


def tokenize(text: str) -> list[Token]:
    tokens = []
    pos, n = 0, len(text)
    while pos < n:
        ws = _WS_RE.match(text, pos)
        if ws:
            pos = ws.end()
            continue
        ch = text[pos]
        if ch.isascii() and (ch.isalpha() or ch in "_$"):
            tok = _lex_word(text, pos)
        elif ch in _DIGITS or (ch == "." and text[pos + 1 : pos + 2] in _DIGITS):
            m = _NUMBER_RE.match(text, pos)
            tok = Token("const", pos, m.end(), finite(float(m[0])))
        elif ch == '"':
            m = _STRING_RE.match(text, pos)
            if m:
                tok = Token("const", pos, m.end(), m[1].replace('""', '"'))
            else:
                tok = Token("bad", pos, n)
        elif ch == "#":
            m = _ERROR_RE.match(text, pos)
            tok = Token("const", pos, m.end(), CellError(m[0].upper())) if m else Token("bad", pos, pos + 1)
        elif ch in _PUNCTUATION:
            tok = Token(_PUNCTUATION[ch], pos, pos + 1)
        else:
            op = next((op for op in _OPERATORS if text.startswith(op, pos)), None)
            tok = Token("op", pos, pos + len(op), op) if op else Token("bad", pos, pos + 1)
        tokens.append(tok)
        pos = tok.end
    return tokens


class Node:
    __slots__ = ()
    rect: Rect | None = None


class Const(Node):
    __slots__ = ("value",)

    def __init__(self, value: Value) -> None:
        self.value = value

    def eval(self, ctx: Context) -> Value:
        return self.value


class CellRef(Node):
    __slots__ = ("row", "col", "rect")

    def __init__(self, row: int, col: int) -> None:
        self.row, self.col = row, col
        self.rect = (row, col, row, col)

    def eval(self, ctx: Context) -> Value:
        return ctx.value(self.row, self.col)


class RangeRef(Node):
    __slots__ = ("rect",)

    def __init__(self, rect: Rect) -> None:
        self.rect = rect

    def eval(self, ctx: Context) -> Value:
        return VALUE


class Unary(Node):
    __slots__ = ("op", "operand")

    def __init__(self, op: str, operand: Node) -> None:
        self.op, self.operand = op, operand

    def eval(self, ctx: Context) -> Value:
        return unary(self.op, self.operand.eval(ctx))


class Binary(Node):
    __slots__ = ("op", "left", "right")

    def __init__(self, op: str, left: Node, right: Node) -> None:
        self.op, self.left, self.right = op, left, right

    def eval(self, ctx: Context) -> Value:
        leftmost, chain = _unwind_left_operands(self)
        acc = leftmost.eval(ctx)
        for b in chain:
            if isinstance(acc, CellError):
                return acc
            acc = binary(b.op, acc, b.right.eval(ctx))
        return acc


def _unwind_left_operands(node: Binary) -> tuple[Node, list[Binary]]:
    chain = []
    while type(node) is Binary:
        chain.append(node)
        node = node.left
    chain.reverse()
    return node, chain


class Call(Node):
    __slots__ = ("impl", "args")

    def __init__(self, impl: Callable, args: list[Node]) -> None:
        self.impl, self.args = impl, args

    def eval(self, ctx: Context) -> Value:
        return self.impl(self.args, ctx)


_BINARY_LEVEL = {
    "=": 0, "<>": 0, "<": 0, ">": 0, "<=": 0, ">=": 0,
    "&": 1,
    "+": 2, "-": 2,
    "*": 3, "/": 3,
    "^": 4,
}


class _ParseError(Exception):
    pass


class _Parser:
    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Token | None:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self, kind: str) -> Token:
        tok = self.peek()
        if tok is None or tok.kind != kind:
            raise _ParseError
        self.pos += 1
        return tok

    def parse(self) -> Node:
        node = self.expr(0)
        if self.peek() is not None:
            raise _ParseError
        return node

    def expr(self, min_level: int) -> Node:
        left = self.prefix()
        while (tok := self.peek()) is not None and tok.kind == "op":
            level = _BINARY_LEVEL[tok.value]
            if level < min_level:
                break
            self.pos += 1
            left = Binary(tok.value, left, self.expr(level + 1))
        return left

    def prefix(self) -> Node:
        signs = []
        while (tok := self.peek()) is not None and tok.kind == "op" and tok.value in "+-":
            signs.append(tok.value)
            self.pos += 1
        node = self.primary()
        for sign in reversed(signs):
            node = Unary(sign, node)
        return node

    def primary(self) -> Node:
        tok = self.peek()
        if tok is None:
            raise _ParseError
        self.pos += 1
        match tok.kind:
            case "const":
                return Const(tok.value)
            case "ref":
                return CellRef(tok.value.row, tok.value.col)
            case "range":
                a, b = tok.value
                return RangeRef((a.row, a.col, b.row, b.col))
            case "name":
                return Const(NAME)
            case "func":
                return self.call(tok.value)
            case "(":
                node = self.expr(0)
                self.take(")")
                return node
        raise _ParseError

    def call(self, name: str) -> Node:
        self.take("(")
        args = []
        if (tok := self.peek()) is not None and tok.kind == ")":
            self.pos += 1
        else:
            args.append(self.expr(0))
            while self.peek() is not None and self.peek().kind == ",":
                self.pos += 1
                args.append(self.expr(0))
            self.take(")")
        fn = FUNCTIONS.get(name)
        if fn is None:
            return Const(NAME)
        if not fn.min_args <= len(args) <= fn.max_args:
            return Const(VALUE)
        return Call(fn.impl, args)


class Formula(NamedTuple):
    tokens: list[Token]
    node: Node
    refs: tuple[Addr, ...]
    rects: tuple[Rect, ...]


@lru_cache(maxsize=65536)
def compile_formula(body: str) -> Formula:
    tokens = tokenize(body)
    try:
        node = _Parser(tokens).parse()
    except (_ParseError, RecursionError):
        return Formula(tokens, Const(PARSE), (), ())
    refs = tuple(dict.fromkeys((t.value.row, t.value.col) for t in tokens if t.kind == "ref"))
    rects = tuple(
        dict.fromkeys(
            (a.row, a.col, b.row, b.col) for t in tokens if t.kind == "range" for a, b in [t.value]
        )
    )
    return Formula(tokens, node, refs, rects)


RefMap = Callable[[Ref], Ref | None]
RangeMap = Callable[[Ref, Ref], tuple[Ref, Ref] | None]


def rewrite(body: str, tokens: list[Token], on_ref: RefMap, on_range: RangeMap) -> str:
    out = []
    last = 0
    for tok in tokens:
        if tok.kind == "ref":
            new = on_ref(tok.value)
            text = "#REF!" if new is None else new.text()
        elif tok.kind == "range":
            new = on_range(*tok.value)
            text = "#REF!" if new is None else f"{new[0].text()}:{new[1].text()}"
        else:
            continue
        if new == tok.value:
            continue
        out.append(body[last : tok.start])
        out.append(text)
        last = tok.end
    out.append(body[last:])
    return "".join(out)
