from __future__ import annotations

import functools
import sys
from collections.abc import Callable, Iterable, Iterator
from typing import NamedTuple

from ._errors import CYCLE, VALUE, CellError
from ._formula import Formula, Ref, compile_formula, order_corners, rewrite
from ._grid import MAX_COL, MAX_ROW, Addr, Rect, format_addr, in_grid, parse_addr, parse_block
from ._index import RangeIndex
from ._values import Value, parse_literal, same


class _Cell:
    __slots__ = ("raw", "literal", "formula")

    def __init__(self, raw: str) -> None:
        self.raw = raw
        self.formula: Formula | None = compile_formula(raw[1:]) if raw.startswith("=") else None
        self.literal: Value = None if self.formula else parse_literal(raw)


_RECURSION_LIMIT = 20000


def _raised_recursion_limit(method):
    @functools.wraps(method)
    def wrapper(*args, **kwargs):
        previous = sys.getrecursionlimit()
        if previous >= _RECURSION_LIMIT:
            return method(*args, **kwargs)
        sys.setrecursionlimit(_RECURSION_LIMIT)
        try:
            return method(*args, **kwargs)
        finally:
            sys.setrecursionlimit(previous)

    return wrapper


class Sheet:
    def __init__(self) -> None:
        self._cells: dict[Addr, _Cell] = {}
        self._values: dict[Addr, Value] = {}
        self._ref_dependents: dict[Addr, set[Addr]] = {}
        self._range_dependents = RangeIndex()

    @_raised_recursion_limit
    def set(self, addr: str, raw: str) -> list[str]:
        if not isinstance(raw, str):
            raise TypeError(f"raw must be a str, not {type(raw).__name__}")
        a = parse_addr(addr)
        self._store(a, raw)
        return self._recalc([a])

    def get(self, addr: str) -> float | str | bool | CellError | None:
        return self._values.get(parse_addr(addr))

    def get_raw(self, addr: str) -> str:
        cell = self._cells.get(parse_addr(addr))
        return "" if cell is None else cell.raw

    def insert_rows(self, at: int, count: int = 1) -> None:
        self._check_axis(at, count, MAX_ROW, deleting=False)
        self._restructure(0, *_inserter(at, count, MAX_ROW))

    def delete_rows(self, at: int, count: int = 1) -> None:
        self._check_axis(at, count, MAX_ROW, deleting=True)
        self._restructure(0, *_deleter(at, count))

    def insert_cols(self, at: int, count: int = 1) -> None:
        self._check_axis(at, count, MAX_COL, deleting=False)
        self._restructure(1, *_inserter(at, count, MAX_COL))

    def delete_cols(self, at: int, count: int = 1) -> None:
        self._check_axis(at, count, MAX_COL, deleting=True)
        self._restructure(1, *_deleter(at, count))

    @_raised_recursion_limit
    def copy(self, src: str, dst: str) -> list[str]:
        r1, c1, r2, c2 = parse_block(src)
        dr0, dc0 = parse_addr(dst)
        dr, dc = dr0 - r1, dc0 - c1
        if not in_grid(r2 + dr, c2 + dc):
            raise ValueError(f"copy destination runs past the grid edge: {dst!r}")

        def on_ref(ref: Ref) -> Ref | None:
            row = ref.row if ref.row_abs else ref.row + dr
            col = ref.col if ref.col_abs else ref.col + dc
            return ref._replace(row=row, col=col) if in_grid(row, col) else None

        def on_range(a: Ref, b: Ref) -> tuple[Ref, Ref] | None:
            na, nb = on_ref(a), on_ref(b)
            return None if na is None or nb is None else order_corners(na, nb)

        writes = {
            (row + dr, col + dc): _shift_raw(cell, on_ref, on_range)
            for (row, col), cell in self._cells_in((r1, c1, r2, c2))
        }
        for a, _ in self._cells_in((r1 + dr, c1 + dc, r2 + dr, c2 + dc)):
            writes.setdefault(a, "")
        for a, raw in writes.items():
            self._store(a, raw)
        return self._recalc(writes)

    def value(self, row: int, col: int) -> Value:
        return self._values.get((row, col))

    def iter_rect(self, rect: Rect) -> Iterator[Value]:
        r1, c1, r2, c2 = rect
        values = self._values
        if (r2 - r1 + 1) * (c2 - c1 + 1) > len(values):
            inside = [a for a in values if r1 <= a[0] <= r2 and c1 <= a[1] <= c2]
            inside.sort()
            for a in inside:
                yield values[a]
            return
        get = values.get
        cols = range(c1, c2 + 1)
        for row in range(r1, r2 + 1):
            for col in cols:
                v = get((row, col))
                if v is not None:
                    yield v

    def _cells_in(self, rect: Rect) -> list[tuple[Addr, _Cell]]:
        r1, c1, r2, c2 = rect
        cells = self._cells
        if (r2 - r1 + 1) * (c2 - c1 + 1) <= len(cells):
            found = []
            for row in range(r1, r2 + 1):
                for col in range(c1, c2 + 1):
                    cell = cells.get((row, col))
                    if cell is not None:
                        found.append(((row, col), cell))
            return found
        return sorted(
            (a, cell) for a, cell in cells.items() if r1 <= a[0] <= r2 and c1 <= a[1] <= c2
        )

    def _store(self, a: Addr, raw: str) -> None:
        old = self._cells.pop(a, None)
        if old is not None and old.formula is not None:
            for ref in old.formula.refs:
                dependents = self._ref_dependents[ref]
                dependents.discard(a)
                if not dependents:
                    del self._ref_dependents[ref]
            for rect in old.formula.rects:
                self._range_dependents.remove(rect, a)
        if raw == "":
            return
        cell = _Cell(raw)
        self._cells[a] = cell
        if cell.formula is not None:
            for ref in cell.formula.refs:
                self._ref_dependents.setdefault(ref, set()).add(a)
            for rect in cell.formula.rects:
                self._range_dependents.add(rect, a)

    def _dependents(self, a: Addr) -> list[Addr]:
        found = self._range_dependents.query(a)
        direct = self._ref_dependents.get(a)
        if direct:
            found.extend(direct)
        return found

    def _evaluate(self, a: Addr) -> Value:
        cell = self._cells.get(a)
        if cell is None:
            return None
        if cell.formula is None:
            return cell.literal
        try:
            v = cell.formula.node.eval(self)
        except RecursionError:
            return VALUE
        return 0.0 if v is None else v

    def _recalc(self, roots: Iterable[Addr]) -> list[str]:
        changed = []
        values = self._values
        for component, cyclic in _components_in_eval_order(roots, self._dependents):
            for a in component:
                new = CYCLE if cyclic else self._evaluate(a)
                old = values.get(a)
                if new is None:
                    values.pop(a, None)
                else:
                    values[a] = new
                if not same(old, new):
                    changed.append(a)
        changed.sort()
        return [format_addr(a) for a in changed]

    @staticmethod
    def _check_axis(at: int, count: int, limit: int, *, deleting: bool) -> None:
        if not 1 <= at <= limit:
            raise ValueError(f"position out of range: {at!r}")
        if count < 1:
            raise ValueError(f"count must be at least 1: {count!r}")
        if deleting and at + count - 1 > limit:
            raise ValueError("deletion runs past the grid edge")

    @_raised_recursion_limit
    def _restructure(self, axis: int, point: PointMap, span: SpanMap) -> None:
        def on_ref(ref: Ref) -> Ref | None:
            moved = point(ref[axis])
            return None if moved is None else ref._replace(**{_AXIS[axis]: moved})

        def on_range(a: Ref, b: Ref) -> tuple[Ref, Ref] | None:
            moved = span(a[axis], b[axis])
            if moved is None:
                return None
            field = _AXIS[axis]
            return a._replace(**{field: moved[0]}), b._replace(**{field: moved[1]})

        moved_cells = []
        for a, cell in self._cells.items():
            coord = point(a[axis])
            if coord is not None:
                new_addr = (coord, a[1]) if axis == 0 else (a[0], coord)
                moved_cells.append((new_addr, _shift_raw(cell, on_ref, on_range)))
        self.__init__()
        for a, raw in moved_cells:
            self._store(a, raw)
        self._recalc(list(self._cells))


_AXIS = ("row", "col")

PointMap = Callable[[int], int | None]
SpanMap = Callable[[int, int], tuple[int, int] | None]


class Component(NamedTuple):
    members: list[Addr]
    cyclic: bool


def _shift_raw(cell: _Cell, on_ref, on_range) -> str:
    if cell.formula is None:
        return cell.raw
    return "=" + rewrite(cell.raw[1:], cell.formula.tokens, on_ref, on_range)


def _inserter(at: int, count: int, limit: int) -> tuple[PointMap, SpanMap]:
    def point(v: int) -> int | None:
        if v < at:
            return v
        return v + count if v + count <= limit else None

    def span(first: int, last: int) -> tuple[int, int] | None:
        if at <= first:
            return (first + count, min(last + count, limit)) if first + count <= limit else None
        if at <= last:
            return first, min(last + count, limit)
        return first, last

    return point, span


def _deleter(at: int, count: int) -> tuple[PointMap, SpanMap]:
    end = at + count - 1

    def point(v: int) -> int | None:
        if v < at:
            return v
        return v - count if v > end else None

    def span(first: int, last: int) -> tuple[int, int] | None:
        if at <= first and last <= end:
            return None
        new_first = first if first < at else (at if first <= end else first - count)
        new_last = last if last < at else (at - 1 if last <= end else last - count)
        return new_first, new_last

    return point, span


def _components_in_eval_order(
    roots: Iterable[Addr], successors: Callable[[Addr], list[Addr]]
) -> list[Component]:
    index: dict[Addr, int] = {}
    low: dict[Addr, int] = {}
    on_stack: set[Addr] = set()
    stack: list[Addr] = []
    self_loops: set[Addr] = set()
    found: list[Component] = []
    counter = 0

    for root in roots:
        if root in index:
            continue
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        work = [(root, iter(successors(root)))]
        while work:
            v, edges = work[-1]
            for w in edges:
                if w == v:
                    self_loops.add(v)
                elif w not in index:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(successors(w))))
                    break
                elif w in on_stack and index[w] < low[v]:
                    low[v] = index[w]
            else:
                work.pop()
                if work:
                    u = work[-1][0]
                    if low[v] < low[u]:
                        low[u] = low[v]
                if low[v] == index[v]:
                    component = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        component.append(w)
                        if w == v:
                            break
                    found.append(Component(component, len(component) > 1 or v in self_loops))
    found.reverse()
    return found
