"""Timing / scale tests.

Limits are deliberately generous: an incremental O(affected-cells) engine finishes each
of these in well under the limit even on a slow machine, while an engine that recalculates
the whole sheet on every edit (O(cells) per set) needs orders of magnitude longer.
"""

import time

import pytest

from gridcalc import CellError, Sheet


def is_err(v, code):
    return isinstance(v, CellError) and v.code == code


def is_num(v, x):
    return type(v) is float and v == pytest.approx(x)


class Deadline:
    """Fails the test as soon as the budget is exceeded (so a quadratic engine fails
    quickly instead of running for hours)."""

    def __init__(self, seconds, what):
        self.limit = seconds
        self.what = what
        self.t0 = time.perf_counter()

    def elapsed(self):
        return time.perf_counter() - self.t0

    def check(self):
        e = self.elapsed()
        if e > self.limit:
            pytest.fail(f"{self.what} exceeded {self.limit:.0f}s (at {e:.1f}s)")


def build_chain(n, seconds=60.0):
    d = Deadline(seconds, f"building a {n}-cell chain")
    s = Sheet()
    s.set("A1", "1")
    for i in range(2, n + 1):
        s.set(f"A{i}", f"=A{i - 1}+1")
        if i % 500 == 0:
            d.check()
    d.check()
    return s


def test_long_chain_50k():
    n = 50_000
    s = build_chain(n)
    assert is_num(s.get(f"A{n}"), float(n))

    t0 = time.perf_counter()
    changed = s.set("A1", "2")
    t_update = time.perf_counter() - t0
    assert t_update < 15.0, f"propagating through a {n}-cell chain took {t_update:.1f}s"
    assert len(changed) == n
    assert changed[0] == "A1"
    assert changed[-1] == f"A{n}"
    assert is_num(s.get(f"A{n}"), float(n + 1))
    assert is_num(s.get("A25000"), 25001.0)


def build_big_sheet(rows, seconds=60.0):
    """5 columns x rows cells:
    A_i = i, B_i = A_i*2, C_i = B_i+A_i, D_i = IF(C_i>10,C_i,0), E_i = SUM(A_i:D_i)
    """
    d = Deadline(seconds, f"building {rows * 5} cells")
    s = Sheet()
    for i in range(1, rows + 1):
        if i % 100 == 0:
            d.check()
        s.set(f"A{i}", str(i))
        s.set(f"B{i}", f"=A{i}*2")
        s.set(f"C{i}", f"=B{i}+A{i}")
        s.set(f"D{i}", f"=IF(C{i}>10,C{i},0)")
        s.set(f"E{i}", f"=SUM(A{i}:D{i})")
    d.check()
    return s


def test_many_unrelated_edits_in_large_sheet():
    rows = 10_000  # 50,000 populated cells
    s = build_big_sheet(rows)
    assert is_num(s.get("E1"), 6.0)
    assert is_num(s.get(f"E{rows}"), 90000.0)

    d = Deadline(10.0, "3000 unrelated edits")
    for i in range(1, 3001):
        changed = s.set(f"H{i}", str(i))
        assert changed == [f"H{i}"]
        if i % 50 == 0:
            d.check()
    d.check()
    assert is_num(s.get("H3000"), 3000.0)
    assert is_num(s.get("E5000"), 90000.0 / 2)


def test_many_small_fanout_edits_in_large_sheet():
    rows = 10_000
    s = build_big_sheet(rows)
    d = Deadline(10.0, "2000 edits with 4 dependents each")
    for i in range(1, 2001):
        s.set(f"A{i}", str(i + 1))
        if i % 50 == 0:
            d.check()
    d.check()
    # A=6: B=12, C=18, D=18, E=54
    assert is_num(s.get("E5"), 54.0)
    changed = s.set("A5", "100")
    assert changed == ["A5", "B5", "C5", "D5", "E5"]
    assert is_num(s.get("E5"), 900.0)


def test_nesting_depth_200_parentheses():
    s = Sheet()
    s.set("A1", "=" + "(" * 200 + "1" + ")" * 200)
    assert is_num(s.get("A1"), 1.0)


def test_nesting_depth_200_with_operators():
    s = Sheet()
    s.set("A1", "=" + "(1+" * 200 + "1" + ")" * 200)
    assert is_num(s.get("A1"), 201.0)


def test_nesting_depth_200_inside_function():
    s = Sheet()
    s.set("A1", "=SUM(" + "(" * 200 + "2" + ")" * 200 + ",3)")
    assert is_num(s.get("A1"), 5.0)


def test_long_cycle_20k_detected_and_broken():
    n = 20_000
    s = build_chain(n)
    t0 = time.perf_counter()
    changed = s.set("A1", f"=A{n}+1")
    t_cycle = time.perf_counter() - t0
    assert t_cycle < 20.0, f"closing a {n}-cell cycle took {t_cycle:.1f}s"
    assert len(changed) == n
    assert is_err(s.get("A1"), "#CYCLE!")
    assert is_err(s.get(f"A{n}"), "#CYCLE!")

    t0 = time.perf_counter()
    s.set("A1", "1")
    t_break = time.perf_counter() - t0
    assert t_break < 20.0, f"breaking a {n}-cell cycle took {t_break:.1f}s"
    assert is_num(s.get(f"A{n}"), float(n))
