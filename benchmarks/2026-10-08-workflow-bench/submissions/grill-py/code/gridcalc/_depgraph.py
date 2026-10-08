"""Reverse dependency index: which formula cells read a given cell.

Single references live in a plain dict. Ranges are indexed by a 2-D dyadic
decomposition: a range's rows and columns are each split into O(log n) aligned
power-of-two blocks, and the range is filed under every (column block, row
block) pair. A point lookup then probes one block per active level, so even a
range covering the whole grid costs a handful of entries, and lookups never
scan unrelated ranges.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection

from ._operands import Box, Pos


def _blocks(lo: int, hi: int) -> list[tuple[int, int]]:
    """Split ``lo..hi`` (inclusive) into aligned blocks ``(level, index)``.

    Block ``(k, i)`` covers ``i << k .. ((i + 1) << k) - 1``.
    """
    out = []
    while lo <= hi:
        level = (lo & -lo).bit_length() - 1 if lo else 0
        while lo + (1 << level) - 1 > hi:
            level -= 1
        out.append((level, lo >> level))
        lo += 1 << level
    return out


class DependencyIndex:
    def __init__(self) -> None:
        # A lone dependent is stored as a 1-tuple, which the garbage collector
        # stops tracking; a set is only made once a cell has two dependents.
        self._singles: dict[Pos, tuple[Pos] | set[Pos]] = {}
        self._buckets: dict[tuple[int, int, int, int], set[Pos]] = {}
        # How many bucket entries use each level; only used levels are probed.
        self._col_levels: Counter[int] = Counter()
        self._row_levels: Counter[int] = Counter()

    def add(self, cell: Pos, refs: tuple[Pos, ...], boxes: tuple[Box, ...]) -> None:
        singles = self._singles
        for ref in refs:
            current = singles.get(ref)
            if current is None:
                singles[ref] = (cell,)
            elif type(current) is tuple:
                if current[0] != cell:
                    singles[ref] = {current[0], cell}
            else:
                current.add(cell)  # type: ignore[union-attr]
        for key in self._box_keys(boxes):
            self._buckets.setdefault(key, set()).add(cell)
            self._col_levels[key[0]] += 1
            self._row_levels[key[2]] += 1

    def remove(self, cell: Pos, refs: tuple[Pos, ...], boxes: tuple[Box, ...]) -> None:
        singles = self._singles
        for ref in refs:
            current = singles[ref]
            if type(current) is tuple:
                del singles[ref]
                continue
            current.discard(cell)  # type: ignore[union-attr]
            if len(current) == 1:
                singles[ref] = (next(iter(current)),)
        for key in self._box_keys(boxes):
            dependents = self._buckets.get(key)
            if dependents is not None:
                dependents.discard(cell)
                if not dependents:
                    del self._buckets[key]
            for levels, level in (
                (self._col_levels, key[0]),
                (self._row_levels, key[2]),
            ):
                levels[level] -= 1
                if not levels[level]:
                    del levels[level]

    def dependents(self, pos: Pos) -> Collection[Pos]:
        """Formula cells that reference ``pos``. The result must not be mutated."""
        found = self._singles.get(pos)
        if not self._buckets:
            return found or ()
        row, col = pos
        result = set(found) if found else set()
        buckets = self._buckets
        for ck in self._col_levels:
            ci = col >> ck
            for rk in self._row_levels:
                hit = buckets.get((ck, ci, rk, row >> rk))
                if hit:
                    result |= hit
        return result

    @staticmethod
    def _box_keys(boxes: tuple[Box, ...]) -> list[tuple[int, int, int, int]]:
        keys = []
        for top, left, bottom, right in boxes:
            rows = _blocks(top, bottom)
            for ck, ci in _blocks(left, right):
                keys.extend((ck, ci, rk, ri) for rk, ri in rows)
        return keys
