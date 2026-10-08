"""Rewriting reference tokens inside formula text (structural edits, copy).

Only tokens whose target changes are rewritten; they are emitted in canonical
upper case (ranges normalised top-left first, `$` markers kept with their row
or column part). Everything else in the text is preserved byte for byte.
"""

from __future__ import annotations

from typing import Callable

from ._address import in_grid, num_to_col
from ._formula import Token, tokenize

REF_TOKEN = "#REF!"

# A part is (coordinate, is_absolute).
Part = tuple[int, bool]
# Maps a normalised (lo, hi) span on the edited axis to a new span or None.
SpanMap = Callable[[int, int], "tuple[int, int] | None"]


def _fmt(col: Part, row: Part) -> str:
    return f"{'$' if col[1] else ''}{num_to_col(col[0])}{'$' if row[1] else ''}{row[0]}"


def rewrite(raw: str, fn: Callable[[Token], "str | tuple[str, ...] | None"]) -> str:
    """Apply `fn` to every reference token of formula `raw` (which starts
    with '='). `fn` returns None to keep the token, a string to replace the
    whole token, or one string per endpoint to replace just the endpoints
    (keeping any whitespace around a range's colon)."""
    # Lenient: a formula that does not parse still has its references kept
    # pointing at the same cells.
    tokens, _ = tokenize(raw[1:], offset=1, lenient=True)
    pieces: list[str] = []
    pos = 0
    for tok in tokens:
        if tok.kind != "ref" or not all(in_grid(e.row, e.col) for e in tok.ends):
            continue
        new = fn(tok)
        if new is None:
            continue
        if isinstance(new, str):
            pieces.append(raw[pos : tok.start])
            pieces.append(new)
            pos = tok.end
            continue
        for (start, end), text in zip(tok.spans, new):
            pieces.append(raw[pos:start])
            pieces.append(text)
            pos = end
    if not pieces:
        return raw
    pieces.append(raw[pos:])
    return "".join(pieces)


def _ordered(a: Part, b: Part) -> tuple[Part, Part]:
    return (a, b) if a[0] <= b[0] else (b, a)


def _normalised(tok: Token) -> tuple[Part, Part, Part, Part]:
    """(left, top, right, bottom) parts of a reference token."""
    a = tok.ends[0]
    b = tok.ends[-1]
    left, right = _ordered((a.col, a.col_abs), (b.col, b.col_abs))
    top, bottom = _ordered((a.row, a.row_abs), (b.row, b.row_abs))
    return left, top, right, bottom


def structural(axis: str, span_map: SpanMap) -> Callable[[Token], str | None]:
    """Token rewriter for a row (axis "row") or column ("col") edit."""

    def fn(tok: Token) -> str | None:
        left, top, right, bottom = _normalised(tok)
        lo, hi = (top, bottom) if axis == "row" else (left, right)
        new = span_map(lo[0], hi[0])
        if new is None:
            return REF_TOKEN
        if new == (lo[0], hi[0]):
            return None
        lo, hi = (new[0], lo[1]), (new[1], hi[1])
        if axis == "row":
            top, bottom = lo, hi
        else:
            left, right = lo, hi
        if len(tok.ends) == 1:
            return (_fmt(left, top),)
        return _fmt(left, top), _fmt(right, bottom)

    return fn


def insert_span(at: int, count: int, limit: int) -> SpanMap:
    def span_map(lo: int, hi: int):
        if at <= lo:
            lo, hi = lo + count, hi + count
        elif at <= hi:
            hi += count
        if lo > limit:
            return None
        return lo, min(hi, limit)

    return span_map


def delete_span(at: int, count: int) -> SpanMap:
    last = at + count - 1

    def span_map(lo: int, hi: int):
        if at <= lo and hi <= last:
            return None
        new_lo = lo if lo < at else (at if lo <= last else lo - count)
        new_hi = hi if hi < at else (at - 1 if hi <= last else hi - count)
        return new_lo, new_hi

    return span_map


def copy_shift(dr: int, dc: int) -> Callable[[Token], str | None]:
    """Token rewriter for pasting a formula `dr` rows / `dc` cols away."""

    def shift(part: Part, delta: int) -> Part:
        return part if part[1] else (part[0] + delta, False)

    def fn(tok: Token) -> str | None:
        ends = []
        for e in tok.ends:
            col, row = shift((e.col, e.col_abs), dc), shift((e.row, e.row_abs), dr)
            if not in_grid(row[0], col[0]):
                return REF_TOKEN
            ends.append((col, row, e))
        if all(c[0] == e.col and r[0] == e.row for c, r, e in ends):
            return None
        if len(ends) == 1:
            return (_fmt(ends[0][0], ends[0][1]),)
        (ca, ra, _), (cb, rb, _) = ends
        left, right = _ordered(ca, cb)
        top, bottom = _ordered(ra, rb)
        return _fmt(left, top), _fmt(right, bottom)

    return fn
