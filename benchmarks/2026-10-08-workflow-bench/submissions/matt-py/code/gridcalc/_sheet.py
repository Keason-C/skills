"""The Sheet: cell storage, dependency graph and incremental recalculation."""

from __future__ import annotations

from itertools import product
from operator import itemgetter

from . import CellError
from ._address import MAX_COL, MAX_ROW, format_addr, parse_addr
from ._evaluator import evaluate
from ._formula import Formula, compile_formula
from ._rewrite import copy_shift, delete_span, insert_span, rewrite, structural
from ._values import CYCLE, parse_literal, same_value

Key = tuple[int, int]  # (row, col)
Rect = tuple[int, int, int, int]  # (r1, c1, r2, c2), normalised


class _ValueStore(dict):
    """Computed values by Key (empty cells absent); also the read interface
    the evaluator uses (see `_evaluator.Cells`)."""

    def value(self, row: int, col: int):
        return self.get((row, col))

    def range_values(self, r1: int, c1: int, r2: int, c2: int) -> list:
        if (r2 - r1 + 1) * (c2 - c1 + 1) <= 2 * len(self):
            cells = product(range(r1, r2 + 1), range(c1, c2 + 1))  # row-major
            return [v for v in map(self.get, cells) if v is not None]
        inside = [(k, v) for k, v in self.items() if r1 <= k[0] <= r2 and c1 <= k[1] <= c2]
        inside.sort(key=itemgetter(0))
        return [v for _, v in inside]


class _RangeIndex:
    """Finds the formulas whose range arguments cover a given cell.

    Multi-resolution bucketing, chosen separately per axis: a range is
    registered with the finest row resolution at which it spans at most
    MAX_SPAN row buckets, and likewise for columns. A lookup checks one
    bucket per resolution pair in use, so it only scans ranges of comparable
    shape near the cell (tall single-column ranges never collide with the
    next column).
    """

    ROW_SHIFTS = (4, 7, 10, 13, 16, 21)  # the last one covers every row
    COL_SHIFTS = (0, 2, 4, 6, 8, 10, 15)  # the last one covers every column
    MAX_SPAN = 4

    def __init__(self) -> None:
        self._buckets: dict[tuple[int, int, int, int], set[tuple[Rect, Key]]] = {}
        self._level_use: dict[tuple[int, int], int] = {}  # (row shift, col shift) -> entries

    @classmethod
    def _shift(cls, lo: int, hi: int, shifts: tuple[int, ...]) -> int:
        for shift in shifts:
            if (hi >> shift) - (lo >> shift) < cls.MAX_SPAN:
                return shift
        raise AssertionError("span larger than the grid")

    def _bucket_keys(self, rect: Rect):
        r1, c1, r2, c2 = rect
        rs = self._shift(r1, r2, self.ROW_SHIFTS)
        cs = self._shift(c1, c2, self.COL_SHIFTS)
        keys = [
            (rs, cs, br, bc) for br in range(r1 >> rs, (r2 >> rs) + 1) for bc in range(c1 >> cs, (c2 >> cs) + 1)
        ]
        return (rs, cs), keys

    def add(self, rect: Rect, owner: Key) -> None:
        level, keys = self._bucket_keys(rect)
        self._level_use[level] = self._level_use.get(level, 0) + 1
        for k in keys:
            self._buckets.setdefault(k, set()).add((rect, owner))

    def remove(self, rect: Rect, owner: Key) -> None:
        level, keys = self._bucket_keys(rect)
        self._level_use[level] -= 1
        if not self._level_use[level]:
            del self._level_use[level]
        for k in keys:
            bucket = self._buckets[k]
            bucket.discard((rect, owner))
            if not bucket:
                del self._buckets[k]

    def owners_covering(self, row: int, col: int) -> list[Key]:
        out = []
        buckets = self._buckets
        for rs, cs in self._level_use:
            bucket = buckets.get((rs, cs, row >> rs, col >> cs))
            if bucket:
                for (r1, c1, r2, c2), owner in bucket:
                    if r1 <= row <= r2 and c1 <= col <= c2:
                        out.append(owner)
        return out


def _strongly_connected(nodes, succ: dict[Key, list[Key]]) -> list[list[Key]]:
    """Iterative Tarjan. Components are returned in topological order
    (a component comes before every component that depends on it)."""
    index: dict[Key, int] = {}
    low: dict[Key, int] = {}
    on_stack: set[Key] = set()
    stack: list[Key] = []
    components: list[list[Key]] = []
    counter = 0
    for root in nodes:
        if root in index:
            continue
        index[root] = low[root] = counter
        counter += 1
        stack.append(root)
        on_stack.add(root)
        work = [(root, iter(succ[root]))]
        while work:
            node, it = work[-1]
            for w in it:
                if w not in index:
                    index[w] = low[w] = counter
                    counter += 1
                    stack.append(w)
                    on_stack.add(w)
                    work.append((w, iter(succ[w])))
                    break
                if w in on_stack and index[w] < low[node]:
                    low[node] = index[w]
            else:
                work.pop()
                if work:
                    parent = work[-1][0]
                    if low[node] < low[parent]:
                        low[parent] = low[node]
                if low[node] == index[node]:
                    component = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        component.append(w)
                        if w == node:
                            break
                    components.append(component)
    components.reverse()
    return components


class Sheet:
    def __init__(self) -> None:
        self._raw: dict[Key, str] = {}
        self._values = _ValueStore()
        self._formulas: dict[Key, Formula] = {}
        self._ref_dependents: dict[Key, set[Key]] = {}
        self._range_index = _RangeIndex()

    # ------------------------------------------------------------ public API

    def set(self, addr: str, raw: str) -> list[str]:
        key = parse_addr(addr)
        if not isinstance(raw, str):
            raise TypeError("raw must be a str")
        self._store(key, raw)
        return self._recalc([key])

    def get(self, addr: str) -> float | str | bool | CellError | None:
        return self._values.get(parse_addr(addr))

    def get_raw(self, addr: str) -> str:
        return self._raw.get(parse_addr(addr), "")

    def insert_rows(self, at: int, count: int = 1) -> None:
        self._structural("row", at, count, insert=True)

    def delete_rows(self, at: int, count: int = 1) -> None:
        self._structural("row", at, count, insert=False)

    def insert_cols(self, at: int, count: int = 1) -> None:
        self._structural("col", at, count, insert=True)

    def delete_cols(self, at: int, count: int = 1) -> None:
        self._structural("col", at, count, insert=False)

    def copy(self, src: str, dst: str) -> list[str]:
        r1, c1, r2, c2 = _parse_range(src)
        dr0, dc0 = parse_addr(dst.replace("$", ""))
        dr, dc = dr0 - r1, dc0 - c1
        if r2 + dr > MAX_ROW or c2 + dc > MAX_COL:
            raise ValueError("destination block extends beyond the grid")
        shift = copy_shift(dr, dc)
        block = []
        for r in range(r1, r2 + 1):
            for c in range(c1, c2 + 1):
                raw = self._raw.get((r, c), "")
                if raw.startswith("="):
                    raw = rewrite(raw, shift)
                block.append(((r + dr, c + dc), raw))
        for key, raw in block:
            self._store(key, raw)
        return self._recalc([key for key, _ in block])

    # ------------------------------------------------------------ internals

    def _store(self, key: Key, raw: str) -> None:
        """Replace a cell's raw content and dependency registrations (no recalc)."""
        old = self._formulas.pop(key, None)
        if old is not None:
            self._unregister(key, old)
        if raw == "":
            self._raw.pop(key, None)
            return
        self._raw[key] = raw
        if raw.startswith("="):
            self._register(key, compile_formula(raw[1:]))

    def _register(self, key: Key, formula: Formula) -> None:
        self._formulas[key] = formula
        for ref in formula.refs:
            self._ref_dependents.setdefault(ref, set()).add(key)
        for rect in formula.ranges:
            self._range_index.add(rect, key)

    def _unregister(self, key: Key, formula: Formula) -> None:
        for ref in formula.refs:
            deps = self._ref_dependents[ref]
            deps.discard(key)
            if not deps:
                del self._ref_dependents[ref]
        for rect in formula.ranges:
            self._range_index.remove(rect, key)

    def _dependents(self, key: Key) -> list[Key]:
        out = list(self._ref_dependents.get(key, ()))
        out.extend(self._range_index.owners_covering(*key))
        return out

    def _recalc(self, seeds) -> list[str]:
        """Recompute `seeds` and every formula that transitively depends on
        them. Returns the sorted addresses whose value changed."""
        values = self._values
        formulas = self._formulas
        old: dict = {}
        frontier: list[Key] = []
        for key in dict.fromkeys(seeds):
            if key in formulas:
                frontier.append(key)
                continue
            old[key] = values.get(key)
            if key in self._raw:
                values[key] = parse_literal(self._raw[key])
            else:
                values.pop(key, None)
            frontier.extend(self._dependents(key))

        # Only formulas need ordering: literals were settled above.
        succ: dict[Key, list[Key]] = {key: [] for key in frontier}
        pending = list(succ)
        while pending:
            key = pending.pop()
            nexts = self._dependents(key)
            succ[key] = nexts
            for w in nexts:
                if w not in succ:
                    succ[w] = []
                    pending.append(w)

        for key in succ:
            old[key] = values.get(key)
        for component in _strongly_connected(list(succ), succ):
            if len(component) > 1 or component[0] in succ[component[0]]:
                for key in component:
                    values[key] = CYCLE
            else:
                key = component[0]
                values[key] = evaluate(formulas[key].code, values)

        changed = [key for key, before in old.items() if not same_value(before, values.get(key))]
        changed.sort()
        return [format_addr(r, c) for r, c in changed]

    def _structural(self, axis: str, at: int, count: int, insert: bool) -> None:
        """Insert/delete rows or columns.

        Cells move with their values. Only formulas with a dependency on the
        edited span are rewritten and recompiled; those, plus formulas that
        depended on removed cells, are the seeds of an incremental recalc.
        """
        limit = MAX_ROW if axis == "row" else MAX_COL
        if type(at) is not int or type(count) is not int:
            raise ValueError("at and count must be integers")
        if at < 1 or at > limit or count < 1:
            raise ValueError("invalid structural edit arguments")
        span_map = insert_span(at, count, limit) if insert else delete_span(at, count)
        token_fn = structural(axis, span_map)
        idx = 0 if axis == "row" else 1

        def move(key: Key) -> Key | None:
            pos = key[idx]
            if pos >= at:
                if insert:
                    pos += count
                    if pos > limit:
                        return None
                elif pos < at + count:
                    return None
                else:
                    pos -= count
            return (pos, key[1]) if idx == 0 else (key[0], pos)

        def affected(formula: Formula) -> bool:
            if not formula.parsed:
                return True  # its references are in the text but not tracked
            for ref in formula.refs:
                x = ref[idx]
                if span_map(x, x) != (x, x):
                    return True
            for rect in formula.ranges:
                span = (rect[idx], rect[idx + 2])
                if span_map(*span) != span:
                    return True
            return False

        new_raw: dict[Key, str] = {}
        new_values = _ValueStore()
        kept: dict[Key, Formula] = {}
        seeds: list[Key] = []
        removed: list[Key] = []
        for key, raw in self._raw.items():
            new_key = move(key)
            if new_key is None:
                removed.append(key)
                continue
            formula = self._formulas.get(key)
            if formula is not None:
                if affected(formula):
                    new_text = rewrite(raw, token_fn)
                    if new_text != raw:
                        raw = new_text
                        formula = None
                        seeds.append(new_key)
                if formula is not None:
                    kept[new_key] = formula
            new_raw[new_key] = raw
            if key in self._values:
                new_values[new_key] = self._values[key]
        for key in removed:
            for dependent in self._dependents(key):
                new_key = move(dependent)
                if new_key is not None:
                    seeds.append(new_key)

        self._raw = new_raw
        self._values = new_values
        self._formulas = {}
        self._ref_dependents = {}
        self._range_index = _RangeIndex()
        for key, raw in new_raw.items():
            if raw.startswith("="):
                formula = kept.get(key)
                self._register(key, formula if formula is not None else compile_formula(raw[1:]))
        self._recalc(seeds)


def _parse_range(text: str) -> Rect:
    """API range/address with optional `$` markers -> normalised rect."""
    text = text.replace("$", "")
    parts = text.split(":")
    if len(parts) > 2:
        raise ValueError(f"invalid range: {text!r}")
    ra, ca = parse_addr(parts[0])
    rb, cb = parse_addr(parts[-1])
    return min(ra, rb), min(ca, cb), max(ra, rb), max(ca, cb)
