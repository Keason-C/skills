"""Formula tokenizer.

Tokens carry their span in the source text so that structural edits and copies
can rewrite reference tokens in place while preserving every other byte.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from ._address import MAX_COL, MAX_ROW, letters_to_col
from ._values import ERRORS

# Token kinds
NUM = "num"
STR = "str"
BOOL = "bool"
ERR = "err"
REF = "ref"
RANGE = "range"
FUNC = "func"  # a name immediately followed by "(" (the "(" is part of the token)
NAME = "name"  # a bare identifier that is not a reference or boolean
OP = "op"
LPAREN = "("
RPAREN = ")"
COMMA = ","


class LexError(Exception):
    pass


class RefPart(NamedTuple):
    """One endpoint coordinate of a reference: a 1-based index and its ``$`` flag."""

    index: int
    absolute: bool


class CellRef(NamedTuple):
    row: RefPart
    col: RefPart

    @property
    def pos(self) -> tuple[int, int]:
        return self.row.index, self.col.index

    @property
    def in_grid(self) -> bool:
        return 1 <= self.row.index <= MAX_ROW and 1 <= self.col.index <= MAX_COL


class RangeRef(NamedTuple):
    """A rectangular range, normalised so ``top <= bottom`` and ``left <= right``.

    Each coordinate keeps its own ``$`` flag through normalisation.
    """

    top: RefPart
    left: RefPart
    bottom: RefPart
    right: RefPart

    @property
    def box(self) -> tuple[int, int, int, int]:
        return self.top.index, self.left.index, self.bottom.index, self.right.index

    @property
    def in_grid(self) -> bool:
        return (
            self.top.index >= 1
            and self.left.index >= 1
            and self.bottom.index <= MAX_ROW
            and self.right.index <= MAX_COL
        )

    @staticmethod
    def spanning(a: CellRef, b: CellRef) -> RangeRef:
        top, bottom = (a.row, b.row) if a.row.index <= b.row.index else (b.row, a.row)
        left, right = (a.col, b.col) if a.col.index <= b.col.index else (b.col, a.col)
        return RangeRef(top, left, bottom, right)


class Token(NamedTuple):
    kind: str
    text: str  # normalised payload: operator symbol, upper-case name, string body...
    start: int
    end: int
    value: object = None  # literal value, or CellRef/RangeRef for references


_REF = r"\$?[A-Za-z]+\$?[0-9]+(?![A-Za-z0-9_.])"
_TOKEN_RE = re.compile(
    r"""\s*(?:
      (?P<ref>"""
    + _REF
    + r""")
    | (?P<num>(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?)
    | (?P<word>[A-Za-z_][A-Za-z0-9_.]*)
    | (?P<str>"(?:[^"]|"")*")
    | (?P<err>(?i:\#(?:DIV/0!|VALUE!|REF!|NAME\?|CYCLE!|PARSE!)))
    | (?P<op><=|>=|<>|[-+*/^&=<>])
    | (?P<punct>[(),])
    )""",
    re.VERBOSE,
)
_REF_PARTS_RE = re.compile(r"(\$?)([A-Za-z]+)(\$?)([0-9]+)")
# What follows a reference: "(" (so it was a function name), ":" and a second
# reference (a range), or a ":" with nothing valid after it.
_AFTER_REF_RE = re.compile(r"\s*(?:(\()|:\s*(" + _REF + r")|(:))?")
_PAREN_RE = re.compile(r"\s*\(")
_PUNCT_KINDS = {"(": LPAREN, ")": RPAREN, ",": COMMA}


def _cell_ref(text: str) -> CellRef:
    col_abs, letters, row_abs, digits = _REF_PARTS_RE.fullmatch(text).groups()  # type: ignore[union-attr]
    if digits[0] == "0":
        raise LexError("row number with leading zero")
    # Clamp absurdly long coordinates; they are out of the grid either way.
    col = letters_to_col(letters) if len(letters) <= 4 else MAX_COL + 1
    row = int(digits) if len(digits) <= 8 else MAX_ROW + 1
    return CellRef(RefPart(row, bool(row_abs)), RefPart(col, bool(col_abs)))


def tokenize(text: str, offset: int = 0) -> list[Token]:
    """Tokenize formula ``text`` (without its leading ``=``).

    Token spans are shifted by ``offset`` so they index into the full raw string.
    Raises ``LexError`` on anything that is not a valid token.
    """
    tokens: list[Token] = []
    append = tokens.append
    match = _TOKEN_RE.match
    pos, n = 0, len(text)
    while True:
        m = match(text, pos)
        if m is None:
            if text[pos:].isspace() or pos == n:
                return tokens
            raise LexError(f"unexpected text at {pos}: {text[pos : pos + 10]!r}")
        kind = m.lastgroup
        start, pos = m.start(kind), m.end()
        lexeme = m.group(kind)
        if kind == "ref":
            after = _AFTER_REF_RE.match(text, pos)
            paren, second, bad_colon = after.groups()  # type: ignore[union-attr]
            if paren is not None and "$" not in lexeme:
                kind = "word"  # a function name such as LOG10(
            elif bad_colon is not None:
                raise LexError("malformed range")
            elif second is not None:
                pos = after.end()  # type: ignore[union-attr]
                rng = RangeRef.spanning(_cell_ref(lexeme), _cell_ref(second))
                append(Token(RANGE, "", start + offset, pos + offset, rng))
                continue
            else:
                append(Token(REF, "", start + offset, pos + offset, _cell_ref(lexeme)))
                continue
        if kind == "word":
            word = lexeme.upper()
            paren = _PAREN_RE.match(text, pos)
            if paren is not None:
                pos = paren.end()
                append(Token(FUNC, word, start + offset, pos + offset))
            elif word == "TRUE" or word == "FALSE":
                append(Token(BOOL, word, start + offset, pos + offset, word == "TRUE"))
            else:
                append(Token(NAME, word, start + offset, pos + offset))
        elif kind == "num":
            append(Token(NUM, lexeme, start + offset, pos + offset, float(lexeme)))
        elif kind == "op":
            append(Token(OP, lexeme, start + offset, pos + offset))
        elif kind == "punct":
            append(Token(_PUNCT_KINDS[lexeme], lexeme, start + offset, pos + offset))
        elif kind == "str":
            body = lexeme[1:-1].replace('""', '"')
            append(Token(STR, body, start + offset, pos + offset, body))
        else:  # err
            code = lexeme.upper()
            append(Token(ERR, code, start + offset, pos + offset, ERRORS[code]))
