from __future__ import annotations

from ._grid import Addr, Rect

_TILE_ROWS = 64
_TILE_COLS = 16
_MAX_TILES = 256


def _tiles(rect: Rect) -> list[tuple[int, int]] | None:
    r1, c1, r2, c2 = rect
    rows = range(r1 // _TILE_ROWS, r2 // _TILE_ROWS + 1)
    cols = range(c1 // _TILE_COLS, c2 // _TILE_COLS + 1)
    if len(rows) * len(cols) > _MAX_TILES:
        return None
    return [(tr, tc) for tr in rows for tc in cols]


class RangeIndex:
    def __init__(self) -> None:
        self._tiles: dict[tuple[int, int], dict[Rect, set[Addr]]] = {}
        self._untiled: dict[Rect, set[Addr]] = {}

    def _buckets(self, rect: Rect, create: bool):
        tiles = _tiles(rect)
        if tiles is None:
            return [self._untiled]
        if create:
            return [self._tiles.setdefault(t, {}) for t in tiles]
        return [self._tiles[t] for t in tiles if t in self._tiles]

    def add(self, rect: Rect, dependent: Addr) -> None:
        for bucket in self._buckets(rect, create=True):
            bucket.setdefault(rect, set()).add(dependent)

    def remove(self, rect: Rect, dependent: Addr) -> None:
        for bucket in self._buckets(rect, create=False):
            dependents = bucket.get(rect)
            if dependents is not None:
                dependents.discard(dependent)
                if not dependents:
                    del bucket[rect]

    def query(self, addr: Addr) -> list[Addr]:
        row, col = addr
        found = []
        tile = self._tiles.get((row // _TILE_ROWS, col // _TILE_COLS))
        for bucket in (tile, self._untiled):
            if not bucket:
                continue
            for (r1, c1, r2, c2), dependents in bucket.items():
                if r1 <= row <= r2 and c1 <= col <= c2:
                    found.extend(dependents)
        return found
