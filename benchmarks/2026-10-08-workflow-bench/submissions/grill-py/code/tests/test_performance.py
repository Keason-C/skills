"""Timing tests standing in for the acceptance suite's (budgets from the spec)."""

import time

from gridcalc import Sheet


def build_large_sheet(rows=10_000):
    """About 50,000 populated cells: numbers, text, single refs, ranges, IFs,
    plus whole-column totals."""
    s = Sheet()
    for r in range(1, rows + 1):
        s.set(f"A{r}", str(r))
        s.set(f"B{r}", f"=A{r}*2")
        s.set(f"C{r}", f"=SUM(A{r}:B{r})")
        s.set(f"D{r}", f"label {r}")
        s.set(f"E{r}", f"=IF(C{r}>100, B{r}, D{r})")
    s.set("F1", f"=SUM(A1:A{rows})")
    s.set("F2", f"=AVERAGE(B1:C{rows})")
    return s


def test_building_large_sheet_is_reasonable():
    start = time.perf_counter()
    s = build_large_sheet()
    elapsed = time.perf_counter() - start
    assert s.get("F1") == sum(range(1, 10_001))
    assert elapsed < 5.0, f"{elapsed:.2f}s"


def test_many_unrelated_edits_on_large_sheet_are_fast():
    s = build_large_sheet()
    start = time.perf_counter()
    for i in range(5_000):
        s.set(f"H{i + 1}", str(i))
    for i in range(5_000):
        s.set(f"J{i % 100 + 1}", f"=H{i % 100 + 1}*2")
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"{elapsed:.2f}s"
    assert s.get("E10000") == 20_000.0


def test_edits_with_few_dependents_on_large_sheet_are_fast():
    s = build_large_sheet()
    s.set("F1", "")
    s.set("F2", "")
    start = time.perf_counter()
    for r in range(1, 2_001):
        s.set(f"D{r}", f"new {r}")  # read by E{r}
        s.set(f"A{r}", str(r + 1))  # read by B{r}, C{r}, E{r}
    elapsed = time.perf_counter() - start
    assert elapsed < 1.0, f"{elapsed:.2f}s"
    assert s.get("E2000") == 4002.0


def test_long_chain_build_and_head_edit():
    n = 50_000
    start = time.perf_counter()
    s = Sheet()
    s.set("A1", "1")
    for r in range(2, n + 1):
        s.set(f"A{r}", f"=A{r - 1}+1")
    changed = s.set("A1", "2")
    elapsed = time.perf_counter() - start
    assert len(changed) == n
    assert s.get(f"A{n}") == float(n + 1)
    assert elapsed < 3.0, f"{elapsed:.2f}s"


def test_long_cycle_is_detected_without_recursion():
    n = 50_000
    s = Sheet()
    for r in range(n - 1, 0, -1):
        s.set(f"A{r}", f"=A{r + 1}")
    start = time.perf_counter()
    s.set(f"A{n}", "=A1")
    s.set(f"A{n}", "1")
    elapsed = time.perf_counter() - start
    assert s.get("A1") == 1.0
    assert elapsed < 2.0, f"{elapsed:.2f}s"


def test_structural_edit_on_large_sheet():
    s = build_large_sheet()
    start = time.perf_counter()
    s.insert_rows(5_000)
    s.delete_rows(5_000)
    elapsed = time.perf_counter() - start
    assert s.get("F1") == sum(range(1, 10_001))
    assert s.get_raw("F1") == "=SUM(A1:A10000)"
    assert elapsed < 3.0, f"{elapsed:.2f}s"
