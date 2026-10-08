"""Formula compilation and evaluation.

A formula is tokenized, parsed into a small AST by a shunting-yard parser and
compiled to a flat stack-machine program. None of these steps (nor evaluation)
recurse, so formula depth is bounded only by memory.
"""

from __future__ import annotations

from collections.abc import Callable

from . import CellError
from ._functions import FUNCTIONS, LAZY
from ._lexer import (
    BOOL,
    COMMA,
    ERR,
    FUNC,
    LPAREN,
    NAME,
    NUM,
    OP,
    RANGE,
    REF,
    RPAREN,
    STR,
    CellRef,
    LexError,
    RangeRef,
    Token,
    tokenize,
)
from ._operands import Box, Operand, Pos, Reader, scalar
from ._values import (
    DIV0,
    PARSE,
    VALUE,
    Value,
    compare,
    finite,
    to_bool,
    to_number,
    to_text,
)
from ._values import (
    NAME as NAME_ERROR,
)
from ._values import (
    REF as REF_ERROR,
)

# -- operators ---------------------------------------------------------------


def _arith(fn: Callable[[float, float], float]) -> Callable[[Value, Value], Value]:
    def op(a: Value, b: Value) -> Value:
        x = to_number(a)
        if type(x) is not float:
            return x
        y = to_number(b)
        if type(y) is not float:
            return y
        return fn(x, y)  # type: ignore[arg-type]

    return op


def _add(x: float, y: float) -> Value:
    return finite(x + y)


def _sub(x: float, y: float) -> Value:
    return finite(x - y)


def _mul(x: float, y: float) -> Value:
    return finite(x * y)


def _div(x: float, y: float) -> Value:
    if y == 0:
        return DIV0
    return finite(x / y)


def _pow(x: float, y: float) -> Value:
    try:
        r = x**y
    except ZeroDivisionError:
        return DIV0
    except OverflowError:
        return VALUE
    if type(r) is not float:  # complex result of a negative base
        return VALUE
    return finite(r)


def _concat(a: Value, b: Value) -> Value:
    x = to_text(a)
    if type(x) is not str:
        return x
    y = to_text(b)
    if type(y) is not str:
        return y
    return x + y  # type: ignore[operator]


def _comparison(symbol: str) -> Callable[[Value, Value], Value]:
    def op(a: Value, b: Value) -> Value:
        if isinstance(a, CellError):
            return a
        if isinstance(b, CellError):
            return b
        return compare(symbol, a, b)

    return op


BINARY: dict[str, Callable[[Value, Value], Value]] = {
    "+": _arith(_add),
    "-": _arith(_sub),
    "*": _arith(_mul),
    "/": _arith(_div),
    "^": _arith(_pow),
    "&": _concat,
}
for _sym in ("=", "<>", "<", ">", "<=", ">="):
    BINARY[_sym] = _comparison(_sym)

# Compiled code refers to operators and functions by index, so instructions are
# tuples of atomic values that the garbage collector stops tracking.
_BINARY_INDEX = {sym: i for i, sym in enumerate(BINARY)}
_BINARY_TABLE = tuple(BINARY.values())
_FUNCTION_TABLE: list[Callable[[list[Operand], Reader], Value]] = []
_FUNCTION_INDEX: dict[str, int] = {}
for _name, (_fn, _lo, _hi) in FUNCTIONS.items():
    if callable(_fn):
        _FUNCTION_INDEX[_name] = len(_FUNCTION_TABLE)
        _FUNCTION_TABLE.append(_fn)  # type: ignore[arg-type]

PRECEDENCE = {
    "=": 1,
    "<>": 1,
    "<": 1,
    ">": 1,
    "<=": 1,
    ">=": 1,
    "&": 2,
    "+": 3,
    "-": 3,
    "*": 4,
    "/": 4,
    "^": 5,
}


# -- parsing -----------------------------------------------------------------
#
# AST nodes are tuples: ("const", value), ("ref", CellRef), ("range", RangeRef),
# ("unary", op, operand), ("binary", op, left, right), ("call", name, [args]).


class ParseError(Exception):
    pass


def _operand_node(tok: Token) -> tuple:
    if tok.kind == NUM:
        return ("const", finite(tok.value))  # type: ignore[arg-type]
    if tok.kind in (STR, BOOL, ERR):
        return ("const", tok.value)
    if tok.kind == NAME:
        return ("const", NAME_ERROR)
    ref = tok.value
    if not ref.in_grid:  # type: ignore[union-attr]
        return ("const", REF_ERROR)
    return (tok.kind, ref)


_OPERAND_KINDS = frozenset((NUM, STR, BOOL, ERR, NAME, REF, RANGE))


def parse(tokens: list[Token]) -> tuple:
    out: list[tuple] = []
    # Operator stack entries: ("binary", op, prec), ("unary", op), ("paren",),
    # ("func", name, [argc]).
    ops: list[tuple] = []

    def reduce() -> None:
        entry = ops.pop()
        if entry[0] == "unary":
            out.append(("unary", entry[1], out.pop()))
        else:
            right = out.pop()
            out.append(("binary", entry[1], out.pop(), right))

    def reduce_to_group() -> tuple:
        while ops and ops[-1][0] in ("unary", "binary"):
            reduce()
        if not ops:
            raise ParseError("unbalanced parenthesis or stray comma")
        return ops[-1]

    def close_call(entry: tuple) -> None:
        ops.pop()
        argc = entry[2][0]
        args = out[len(out) - argc :]
        del out[len(out) - argc :]
        out.append(("call", entry[1], args))

    expect_operand = True
    for tok in tokens:
        kind = tok.kind
        if expect_operand:
            if kind in _OPERAND_KINDS:
                out.append(_operand_node(tok))
                expect_operand = False
            elif kind == OP and tok.text in ("+", "-"):
                ops.append(("unary", tok.text))
            elif kind == LPAREN:
                ops.append(("paren",))
            elif kind == FUNC:
                ops.append(("func", tok.text, [0]))
            elif kind == RPAREN and ops and ops[-1][0] == "func" and ops[-1][2][0] == 0:
                close_call(ops[-1])  # NAME() with no arguments
                expect_operand = False
            else:
                raise ParseError(f"unexpected {tok.kind}")
        elif kind == OP:
            prec = PRECEDENCE[tok.text]
            while ops and (
                ops[-1][0] == "unary" or (ops[-1][0] == "binary" and ops[-1][2] >= prec)
            ):
                reduce()
            ops.append(("binary", tok.text, prec))
            expect_operand = True
        elif kind == RPAREN:
            group = reduce_to_group()
            if group[0] == "paren":
                ops.pop()
            else:
                group[2][0] += 1
                close_call(group)
        elif kind == COMMA:
            group = reduce_to_group()
            if group[0] != "func":
                raise ParseError("comma outside a function call")
            group[2][0] += 1
            expect_operand = True
        else:
            raise ParseError("missing operator")
    if expect_operand:
        raise ParseError("incomplete formula")
    while ops:
        if ops[-1][0] not in ("unary", "binary"):
            raise ParseError("unclosed parenthesis")
        reduce()
    return out[0]


# -- code generation -----------------------------------------------------------

PUSH, NEG, POS, BIN, CALL, JUMP_IF, JUMP, ON_ERROR, SCALAR = range(9)


class _Label:
    __slots__ = ("pc",)

    def __init__(self) -> None:
        self.pc = -1


def generate(root: tuple) -> list[tuple[int, object]]:
    code: list[tuple[int, object]] = []
    emit = code.append
    jumps: list[int] = []  # indices of instructions whose argument holds labels
    work: list[tuple] = [root]
    while work:
        item = work.pop()
        tag = item[0]
        if tag == "const":
            emit((PUSH, item[1]))
        elif tag == "ref":
            ref: CellRef = item[1]
            emit((PUSH, ref.pos))
        elif tag == "binary":
            work.append(("emit", BIN, _BINARY_INDEX[item[1]]))
            work.append(item[3])
            work.append(item[2])
        elif tag == "emit":
            if item[1] in (JUMP_IF, JUMP, ON_ERROR):
                jumps.append(len(code))
            emit((item[1], item[2]))
        elif tag == "range":
            rng: RangeRef = item[1]
            emit((PUSH, rng.box))
        elif tag == "unary":
            work.append(("emit", NEG if item[1] == "-" else POS, None))
            work.append(item[2])
        elif tag == "label":
            item[1].pc = len(code)
        else:
            work.extend(reversed(_call_sequence(item[1], item[2])))
    for i in jumps:
        op, arg = code[i]
        if type(arg) is _Label:
            code[i] = (op, arg.pc)
        else:
            code[i] = (op, tuple(label.pc for label in arg))  # type: ignore[attr-defined]
    return code


def _call_sequence(name: str, args: list[tuple]) -> list[tuple]:
    spec = FUNCTIONS.get(name)
    if spec is None:
        return [("const", NAME_ERROR)]
    fn, lo, hi = spec
    if not lo <= len(args) <= (hi if hi is not None else len(args)):
        return [("const", VALUE)]
    if fn is LAZY and name == "IF":
        otherwise, end = _Label(), _Label()
        fallback = args[2] if len(args) == 3 else ("const", False)
        return [
            args[0],
            ("emit", JUMP_IF, (otherwise, end)),
            args[1],
            ("emit", SCALAR, None),
            ("emit", JUMP, end),
            ("label", otherwise),
            fallback,
            ("emit", SCALAR, None),
            ("label", end),
        ]
    if fn is LAZY and name == "IFERROR":
        end = _Label()
        return [
            args[0],
            ("emit", SCALAR, None),
            ("emit", ON_ERROR, end),
            args[1],
            ("emit", SCALAR, None),
            ("label", end),
        ]
    return [*args, ("emit", CALL, (_FUNCTION_INDEX[name], len(args)))]


# -- compiled formulas -----------------------------------------------------------


class Formula:
    """A compiled formula and the cells it statically depends on."""

    __slots__ = ("boxes", "code", "ok", "reach", "refs")

    def __init__(self, raw: str) -> None:
        self.refs: tuple[Pos, ...] = ()
        self.boxes: tuple[Box, ...] = ()
        self.reach = (0, 0)  # furthest row and column referenced
        try:
            tokens = tokenize(raw[1:], offset=1)
            self.code = tuple(generate(parse(tokens)))
        except (LexError, ParseError):
            self.ok = False
            self.code = ((PUSH, PARSE),)
            return
        self.ok = True
        refs, boxes = set(), set()
        for tok in tokens:
            if tok.kind == REF and tok.value.in_grid:  # type: ignore[union-attr]
                ref: CellRef = tok.value  # type: ignore[assignment]
                refs.add(ref.pos)
            elif tok.kind == RANGE and tok.value.in_grid:  # type: ignore[union-attr]
                rng: RangeRef = tok.value  # type: ignore[assignment]
                boxes.add(rng.box)
        self.refs = tuple(refs)
        self.boxes = tuple(boxes)
        self.reach = _reach(refs, boxes)

    def relocated(
        self,
        move_pos: Callable[[Pos], Pos | None],
        move_box: Callable[[Box], Box | None],
    ) -> Formula:
        """This formula with every reference moved (None: the target is gone).

        Equivalent to recompiling the formula text with its reference tokens
        rewritten the same way, without tokenizing or parsing again.
        """
        new = Formula.__new__(Formula)
        new.ok = True
        code = []
        for op, arg in self.code:
            if op == PUSH and type(arg) is tuple:
                moved = move_pos(arg) if len(arg) == 2 else move_box(arg)  # type: ignore[arg-type]
                arg = REF_ERROR if moved is None else moved
            code.append((op, arg))
        new.code = tuple(code)
        refs = {pos for pos in map(move_pos, self.refs) if pos is not None}
        boxes = {box for box in map(move_box, self.boxes) if box is not None}
        new.refs = tuple(refs)
        new.boxes = tuple(boxes)
        new.reach = _reach(refs, boxes)
        return new

    def evaluate(self, reader: Reader) -> Value:
        code = self.code
        stack: list[Operand] = []
        push, pop = stack.append, stack.pop
        pc, n = 0, len(code)
        while pc < n:
            op, arg = code[pc]
            pc += 1
            if op == PUSH:
                push(arg)  # type: ignore[arg-type]
            elif op == BIN:
                b = scalar(pop(), reader)
                push(_BINARY_TABLE[arg](scalar(pop(), reader), b))  # type: ignore[index]
            elif op == CALL:
                fn, argc = arg  # type: ignore[misc]
                args = stack[len(stack) - argc :]
                del stack[len(stack) - argc :]
                push(_FUNCTION_TABLE[fn](args, reader))
            elif op == NEG or op == POS:
                x = to_number(scalar(pop(), reader))
                push(finite(-x) if op == NEG and type(x) is float else x)  # type: ignore[operator]
            elif op == SCALAR:
                push(scalar(pop(), reader))
            elif op == JUMP_IF:
                otherwise, end = arg  # type: ignore[misc]
                cond = to_bool(scalar(pop(), reader))
                if type(cond) is not bool:
                    push(cond)
                    pc = end
                elif not cond:
                    pc = otherwise
            elif op == JUMP:
                pc = arg  # type: ignore[assignment]
            else:  # ON_ERROR
                if isinstance(stack[-1], CellError):
                    pop()
                else:
                    pc = arg  # type: ignore[assignment]
        result = scalar(stack[-1], reader)
        return 0.0 if result is None else result


def _reach(refs: set[Pos], boxes: set[Box]) -> tuple[int, int]:
    corners = [*refs, *((box[2], box[3]) for box in boxes)]
    if not corners:
        return (0, 0)
    return max(r for r, _ in corners), max(c for _, c in corners)
