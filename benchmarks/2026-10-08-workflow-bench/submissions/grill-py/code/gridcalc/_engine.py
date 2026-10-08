"""The calculation engine behind ``Sheet``: cell storage and recalculation."""

from __future__ import annotations

from collections.abc import Collection, Iterable, Iterator

from ._address import (
    MAX_COL,
    MAX_ROW,
    ArgumentTypeError,
    format_addr,
    parse_addr,
    parse_block,
)
from ._depgraph import DependencyIndex
from ._formula import Formula
from ._operands import Box, Pos
from ._rewrite import AxisEdit, StructuralTransform, copy_transform, rewrite
from ._values import CYCLE, Value, classify_literal, same_value


class Cell:
    __slots__ = ("cyclic", "formula", "raw", "value")

    def __init__(self, raw: str, value: Value, formula: Formula | None) -> None:
        self.raw = raw
        self.value = value
        self.formula = formula
        self.cyclic = False  # currently a member of a dependency cycle


class Engine:
    def __init__(self) -> None:
        self.cells: dict[Pos, Cell] = {}
        self.index = DependencyIndex()

    # -- Reader protocol (used by formula evaluation) ------------------------

    def value_at(self, pos: Pos) -> Value:
        cell = self.cells.get(pos)
        return None if cell is None else cell.value

    def range_values(self, box: Box) -> Iterator[Value]:
        top, left, bottom, right = box
        cells = self.cells
        if _dense(box, len(cells)):
            get = cells.get
            for row in range(top, bottom + 1):
                for col in range(left, right + 1):
                    cell = get((row, col))
                    if cell is not None:
                        yield cell.value
        else:  # a huge, sparsely populated range
            for pos in sorted(self._populated(box)):
                yield cells[pos].value

    # -- reading ---------------------------------------------------------

    def get(self, addr: str) -> Value:
        return self.value_at(parse_addr(addr))

    def get_raw(self, addr: str) -> str:
        cell = self.cells.get(parse_addr(addr))
        return "" if cell is None else cell.raw

    # -- writing ---------------------------------------------------------

    def set(self, addr: str, raw: str) -> list[str]:
        pos = parse_addr(addr)
        if not isinstance(raw, str):
            raise TypeError(f"raw must be a str, not {type(raw).__name__}")
        old = {pos: self.value_at(pos)}
        self._store(pos, raw)
        return self._recalc(old)

    def copy(self, src: str, dst: str) -> list[str]:
        top, left, bottom, right = parse_block(src)
        dst_row, dst_col = parse_addr(dst)
        d_row, d_col = dst_row - top, dst_col - left
        if bottom + d_row > MAX_ROW or right + d_col > MAX_COL:
            raise ValueError(f"copy of {src!r} to {dst!r} would leave the grid")
        transform = copy_transform(d_row, d_col)
        # Read the whole source block before writing anything.
        writes: dict[Pos, str] = {}
        for pos in self._populated((top, left, bottom, right)):
            cell = self.cells[pos]
            raw = cell.raw
            if cell.formula is not None and cell.formula.ok:
                raw = rewrite(raw, transform)
            writes[(pos[0] + d_row, pos[1] + d_col)] = raw
        for pos in self._populated((dst_row, dst_col, bottom + d_row, right + d_col)):
            writes.setdefault(pos, "")
        old = {pos: self.value_at(pos) for pos in writes}
        for pos, raw in writes.items():
            self._store(pos, raw)
        return self._recalc(old)

    def insert(self, rows: bool, at: int, count: int) -> None:
        self._restructure(rows, AxisEdit(at, count, _limit(rows), deleting=False))

    def delete(self, rows: bool, at: int, count: int) -> None:
        self._restructure(rows, AxisEdit(at, count, _limit(rows), deleting=True))

    def _restructure(self, rows: bool, edit: AxisEdit) -> None:
        _check_axis_edit(edit)
        transform = StructuralTransform(edit, rows)
        moved: list[tuple[Pos, Cell]] = []
        # Shifted references still point at the same cells, and ranges only gain
        # empty cells, so values change only where a reference lost cells.
        lossy: dict[Pos, Value] = {}
        for (row, col), cell in self.cells.items():
            index = edit.point(row if rows else col)
            if index is None:
                continue  # deleted, or pushed off the grid
            pos = (index, col) if rows else (row, index)
            formula = cell.formula
            if (
                formula is not None
                and formula.ok
                and formula.reach[0 if rows else 1] >= edit.at
            ):
                raw, lost_cells = transform.rewrite(cell.raw)
                if raw != cell.raw:
                    relocated = formula.relocated(
                        transform.move_pos, transform.move_box
                    )
                    rewritten = Cell(raw, cell.value, relocated)
                    rewritten.cyclic = cell.cyclic
                    cell = rewritten
                if lost_cells:
                    lossy[pos] = cell.value
            moved.append((pos, cell))
        self.cells = {}
        self.index = DependencyIndex()
        for pos, cell in moved:
            self.cells[pos] = cell
            if cell.formula is not None:
                self.index.add(pos, cell.formula.refs, cell.formula.boxes)
        self._recalc(lossy)

    def _populated(self, box: Box) -> list[Pos]:
        """Positions of the populated cells in ``box``."""
        top, left, bottom, right = box
        cells = self.cells
        if _dense(box, len(cells)):
            return [
                (row, col)
                for row in range(top, bottom + 1)
                for col in range(left, right + 1)
                if (row, col) in cells
            ]
        return [
            pos for pos in cells if top <= pos[0] <= bottom and left <= pos[1] <= right
        ]

    def _store(self, pos: Pos, raw: str) -> None:
        """Replace the contents of ``pos`` without recalculating anything."""
        old = self.cells.pop(pos, None)
        if old is not None and old.formula is not None:
            self.index.remove(pos, old.formula.refs, old.formula.boxes)
        if raw == "":
            return
        if raw[0] == "=":
            formula = Formula(raw)
            self.cells[pos] = Cell(raw, None, formula)
            self.index.add(pos, formula.refs, formula.boxes)
        else:
            self.cells[pos] = Cell(raw, classify_literal(raw), None)

    # -- recalculation ---------------------------------------------------

    def _recalc(self, old: dict[Pos, Value]) -> list[str]:
        """Recalculate after the cells in ``old`` (mapped to their previous values)
        were rewritten. Returns the sorted addresses whose values changed.
        """
        dependents_of = self.index.dependents
        if len(old) == 1:
            (pos,) = old
            if not dependents_of(pos):  # the common case: nothing reads this cell
                changed: list[Pos] = []
                self._settle(pos, False, old, {}, {pos}, changed)
                return [format_addr(*pos) for pos in changed]

        # Everything downstream of the edited cells, and the edges among them.
        order = list(old)
        seen = set(order)
        succ: dict[Pos, Collection[Pos]] = {}
        for u in order:  # grows while iterating
            deps = dependents_of(u)
            if deps:
                succ[u] = deps
                for v in deps:
                    if v not in seen:
                        seen.add(v)
                        order.append(v)

        # Order the acyclic part with Kahn's algorithm; whatever it cannot order is
        # on a cycle or downstream of one, and only that goes through Tarjan.
        indegree = dict.fromkeys(order, 0)
        for targets in succ.values():
            for v in targets:
                indegree[v] += 1
        ready = [pos for pos in order if not indegree[pos]]
        for u in ready:  # grows while iterating
            for v in succ.get(u, ()):
                indegree[v] -= 1
                if not indegree[v]:
                    ready.append(v)
        leftover = [pos for pos in order if indegree[pos]]

        changed = []
        dirty = set(old)
        for pos in ready:
            self._settle(pos, False, old, succ, dirty, changed)
        if leftover:
            for component in reversed(_strongly_connected(leftover, succ)):
                first = component[0]
                cyclic = len(component) > 1 or first in succ.get(first, ())
                for pos in component:
                    self._settle(pos, cyclic, old, succ, dirty, changed)
        changed.sort()
        return [format_addr(*pos) for pos in changed]

    def _settle(
        self,
        pos: Pos,
        cyclic: bool,
        old: dict[Pos, Value],
        succ: dict[Pos, Collection[Pos]],
        dirty: set[Pos],
        changed: list[Pos],
    ) -> None:
        """Give ``pos`` its final value once everything it reads is settled."""
        cell = self.cells.get(pos)
        if cyclic:
            previous = old.get(pos, cell.value)  # type: ignore[union-attr]
            cell.value, cell.cyclic = CYCLE, True  # type: ignore[union-attr]
            new = CYCLE
        elif cell is None or cell.formula is None:  # an edited literal or cleared cell
            previous = old[pos]
            new = None if cell is None else cell.value
        elif pos in dirty or cell.cyclic:
            previous = old.get(pos, cell.value)
            new = cell.value = cell.formula.evaluate(self)
            cell.cyclic = False
        else:
            return  # none of its inputs changed
        if not same_value(previous, new):
            changed.append(pos)
            dirty.update(succ.get(pos, ()))


def _dense(box: Box, populated: int) -> bool:
    """Whether scanning every position of ``box`` beats filtering all cells."""
    top, left, bottom, right = box
    return (bottom - top + 1) * (right - left + 1) <= 4 * populated


def _limit(rows: bool) -> int:
    return MAX_ROW if rows else MAX_COL


def _check_axis_edit(edit: AxisEdit) -> None:
    for name, value in (("at", edit.at), ("count", edit.count)):
        if type(value) is not int:
            raise ArgumentTypeError(
                f"{name} must be an int, not {type(value).__name__}"
            )
    if not 1 <= edit.at <= edit.limit:
        raise ValueError(f"at={edit.at} is outside 1..{edit.limit}")
    if edit.count < 1:
        raise ValueError(f"count must be at least 1, not {edit.count}")
    if edit.deleting and edit.at + edit.count - 1 > edit.limit:
        raise ValueError("deletion extends past the edge of the grid")


def _strongly_connected(
    nodes: Iterable[Pos], succ: dict[Pos, Collection[Pos]]
) -> list[list[Pos]]:
    """Tarjan's algorithm, iteratively. Components come out sinks-first."""
    index: dict[Pos, int] = {}
    low: dict[Pos, int] = {}
    stack: list[Pos] = []
    on_stack: set[Pos] = set()
    components: list[list[Pos]] = []
    counter = 0
    empty: tuple[Pos, ...] = ()
    for root in nodes:
        if root in index:
            continue
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        work = [(root, iter(succ.get(root, empty)))]
        while work:
            v, children = work[-1]
            for w in children:
                if w not in index:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(succ.get(w, empty))))
                    break
                if w in on_stack:
                    low[v] = min(low[v], index[w])
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    low[parent] = min(low[parent], low[v])
                if low[v] == index[v]:
                    component = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        component.append(w)
                        if w == v:
                            break
                    components.append(component)
    return components
