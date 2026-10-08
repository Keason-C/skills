"""Rewriting reference tokens inside formula text (for copy and structural edits).

Only tokens whose target changes are rewritten; everything else in the raw
text is preserved byte for byte.
"""

from __future__ import annotations

from collections.abc import Callable

from ._address import MAX_COL, MAX_ROW, col_to_letters
from ._lexer import RANGE, REF, CellRef, RangeRef, RefPart, tokenize
from ._operands import Box, Pos

REF_TOKEN = "#REF!"

# Maps a reference to its new text, or None to leave the token untouched.
Transform = Callable[[CellRef | RangeRef], str | None]


def rewrite(raw: str, transform: Transform) -> str:
    """Apply ``transform`` to every in-grid reference token of formula ``raw``.

    ``raw`` must be a formula that parses.
    """
    parts: list[str] = []
    last = 0
    for tok in tokenize(raw[1:], offset=1):
        if tok.kind not in (REF, RANGE) or not tok.value.in_grid:  # type: ignore[union-attr]
            continue
        new = transform(tok.value)  # type: ignore[arg-type]
        if new is not None:
            parts.append(raw[last : tok.start])
            parts.append(new)
            last = tok.end
    if not parts:
        return raw
    parts.append(raw[last:])
    return "".join(parts)


def format_ref(row: RefPart, col: RefPart) -> str:
    return (
        f"{'$' if col.absolute else ''}{col_to_letters(col.index)}"
        f"{'$' if row.absolute else ''}{row.index}"
    )


def format_range(rng: RangeRef) -> str:
    return f"{format_ref(rng.top, rng.left)}:{format_ref(rng.bottom, rng.right)}"


def _replacement(old: CellRef | RangeRef, new: CellRef | RangeRef) -> str | None:
    if new == old:
        return None
    if isinstance(new, CellRef):
        return format_ref(new.row, new.col)
    return format_range(new)


# -- copy ----------------------------------------------------------------------


def _offset(part: RefPart, delta: int, limit: int) -> RefPart | None:
    if part.absolute or delta == 0:
        return part
    index = part.index + delta
    return RefPart(index, False) if 1 <= index <= limit else None


def copy_transform(d_row: int, d_col: int) -> Transform:
    """References as seen from a cell moved by ``(d_row, d_col)`` (``$`` parts fixed)."""

    def transform(ref: CellRef | RangeRef) -> str | None:
        if isinstance(ref, CellRef):
            row = _offset(ref.row, d_row, MAX_ROW)
            col = _offset(ref.col, d_col, MAX_COL)
            if row is None or col is None:
                return REF_TOKEN
            return _replacement(ref, CellRef(row, col))
        top = _offset(ref.top, d_row, MAX_ROW)
        bottom = _offset(ref.bottom, d_row, MAX_ROW)
        left = _offset(ref.left, d_col, MAX_COL)
        right = _offset(ref.right, d_col, MAX_COL)
        if top is None or bottom is None or left is None or right is None:
            return REF_TOKEN
        return _replacement(
            ref, RangeRef.spanning(CellRef(top, left), CellRef(bottom, right))
        )

    return transform


# -- structural edits ------------------------------------------------------------


class AxisEdit:
    """Insertion or deletion of ``count`` rows (or columns) starting at ``at``."""

    def __init__(self, at: int, count: int, limit: int, deleting: bool) -> None:
        self.at = at
        self.count = count
        self.limit = limit
        self.deleting = deleting

    def point(self, i: int) -> int | None:
        """New index of row/column ``i``, or None if it is deleted or pushed off."""
        at, count = self.at, self.count
        if i < at:
            return i
        if self.deleting:
            return None if i < at + count else i - count
        return i + count if i + count <= self.limit else None

    def span(self, lo: int, hi: int) -> tuple[int, int] | None:
        """New extent of ``lo..hi`` (keeping surviving cells), or None if none survive."""
        at, count = self.at, self.count
        if self.deleting:
            end = at + count - 1
            first = end + 1 if at <= lo <= end else lo
            last = at - 1 if at <= hi <= end else hi
            if first > last:
                return None
            return self.point(first), self.point(last)  # type: ignore[return-value]
        if at <= lo:
            lo, hi = lo + count, hi + count
        elif at <= hi:
            hi += count
        if lo > self.limit:
            return None
        return lo, min(hi, self.limit)


class StructuralTransform:
    """References after rows (``rows=True``) or columns are inserted/deleted.

    ``$`` markers do not prevent shifting; they are carried over unchanged.
    """

    def __init__(self, edit: AxisEdit, rows: bool) -> None:
        self.edit = edit
        self.rows = rows
        self._lossy = False

    def rewrite(self, raw: str) -> tuple[str, bool]:
        """Formula ``raw`` with its references moved, and whether any reference
        lost cells (became ``#REF!``, or a range shrank or was clamped): only
        then can the formula's value change.
        """
        self._lossy = False
        return rewrite(raw, self), self._lossy

    def move_pos(self, pos: Pos) -> Pos | None:
        row, col = pos
        if self.rows:
            row = self.edit.point(row)  # type: ignore[assignment]
            return None if row is None else (row, col)
        col = self.edit.point(col)  # type: ignore[assignment]
        return None if col is None else (row, col)

    def move_box(self, box: Box) -> Box | None:
        top, left, bottom, right = box
        if self.rows:
            extent = self.edit.span(top, bottom)
            return None if extent is None else (extent[0], left, extent[1], right)
        extent = self.edit.span(left, right)
        return None if extent is None else (top, extent[0], bottom, extent[1])

    def __call__(self, ref: CellRef | RangeRef) -> str | None:
        edit, rows = self.edit, self.rows
        if isinstance(ref, CellRef):
            part = ref.row if rows else ref.col
            index = edit.point(part.index)
            if index is None:
                self._lossy = True
                return REF_TOKEN
            moved = RefPart(index, part.absolute)
            new = CellRef(moved, ref.col) if rows else CellRef(ref.row, moved)
            return _replacement(ref, new)
        lo, hi = (ref.top, ref.bottom) if rows else (ref.left, ref.right)
        extent = edit.span(lo.index, hi.index)
        if extent is None:
            self._lossy = True
            return REF_TOKEN
        if edit.deleting:
            if lo.index < edit.at + edit.count and hi.index >= edit.at:
                self._lossy = True  # some of its rows/columns were deleted
        elif edit.at <= hi.index and hi.index + edit.count > edit.limit:
            self._lossy = True  # clamped at the edge of the grid
        new_lo = RefPart(extent[0], lo.absolute)
        new_hi = RefPart(extent[1], hi.absolute)
        if rows:
            return _replacement(ref, RangeRef(new_lo, ref.left, new_hi, ref.right))
        return _replacement(ref, RangeRef(ref.top, new_lo, ref.bottom, new_hi))
