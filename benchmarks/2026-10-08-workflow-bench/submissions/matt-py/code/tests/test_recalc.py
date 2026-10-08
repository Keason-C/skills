import time

from gridcalc import CellError, Sheet

CYCLE = CellError("#CYCLE!")


def test_dependents_update_and_are_reported_sorted():
    s = Sheet()
    s.set("A1", "1")
    s.set("B2", "=A1*2")
    s.set("C1", "=B2+A1")
    s.set("A3", "=SUM(A1:A2)")
    assert s.set("A1", "5") == ["A1", "C1", "B2", "A3"]
    assert s.get("C1") == 15.0
    assert s.get("A3") == 5.0


def test_unchanged_values_not_reported():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "=A1>0")
    assert s.set("A1", "2") == ["A1"]
    assert s.set("B1", "=A1>-1") == []
    assert s.get_raw("B1") == "=A1>-1"


def test_range_dependency_on_initially_empty_cell():
    s = Sheet()
    s.set("B1", "=SUM(A1:A100)")
    assert s.set("A50", "7") == ["B1", "A50"]
    assert s.get("B1") == 7.0
    assert s.set("A50", "") == ["B1", "A50"]
    assert s.get("B1") == 0.0


def test_error_values_compare_by_code():
    s = Sheet()
    s.set("A1", "=1/0")
    s.set("B1", "=A1+1")
    assert s.set("A1", "=2/0") == []
    assert s.set("A1", "=#VALUE!") == ["A1", "B1"]


def test_self_reference_is_cycle():
    s = Sheet()
    assert s.set("A1", "=A1+1") == ["A1"]
    assert s.get("A1") == CYCLE
    s.set("B1", "=SUM(A1:B1)")
    assert s.get("B1") == CYCLE


def test_cycle_members_and_dependents():
    s = Sheet()
    s.set("A1", "=B1")
    s.set("B1", "=C1")
    s.set("D1", "=IFERROR(A1, \"caught\")")
    s.set("E1", "=A1+1")
    changed = s.set("C1", "=A1")
    assert changed == ["A1", "B1", "C1", "D1", "E1"]
    assert s.get("A1") == CYCLE and s.get("B1") == CYCLE and s.get("C1") == CYCLE
    assert s.get("D1") == "caught"
    assert s.get("E1") == CYCLE  # propagated error
    s.set("B1", "5")
    assert s.get("A1") == 5.0 and s.get("C1") == 5.0 and s.get("E1") == 6.0
    assert s.get("D1") == 5.0


def test_cycle_through_untaken_if_branch():
    s = Sheet()
    s.set("A1", "=IF(TRUE, 1, B1)")
    s.set("B1", "=A1")
    assert s.get("A1") == CYCLE
    assert s.get("B1") == CYCLE


def test_iferror_on_own_cycle_still_cycle():
    s = Sheet()
    s.set("A1", "=IFERROR(A1, 0)")
    assert s.get("A1") == CYCLE


def test_long_chain_no_recursion_error():
    s = Sheet()
    n = 30000
    s.set("A1", "1")
    for i in range(2, n + 1):
        s.set(f"A{i}", f"=A{i-1}+1")
    assert s.get(f"A{n}") == float(n)
    changed = s.set("A1", "2")
    assert len(changed) == n
    assert s.get(f"A{n}") == float(n + 1)
    s.set("A1", f"=A{n}")
    assert s.get("A1") == CYCLE and s.get(f"A{n}") == CYCLE
    s.set("A1", "0")
    assert s.get(f"A{n}") == float(n - 1)


def test_unrelated_edits_are_fast():
    s = Sheet()
    for r in range(1, 10001):
        s.set(f"A{r}", str(r))
        s.set(f"B{r}", f"=A{r}*2")
        s.set(f"C{r}", f"=SUM(A{r}:B{r})")
        s.set(f"D{r}", f"=IF(C{r}>10, \"big\", \"small\")")
        s.set(f"E{r}", f"=B{r}&D{r}")
    start = time.perf_counter()
    for i in range(3000):
        s.set(f"G{i + 1}", str(i))
    assert time.perf_counter() - start < 2.0
    start = time.perf_counter()
    for i in range(3000):
        s.set(f"A{i + 1}", str(i))
    assert time.perf_counter() - start < 3.0
    assert s.get("E2") == "2small"


def test_edits_beside_many_tall_ranges_are_fast():
    s = Sheet()
    for r in range(1, 20001):
        s.set(f"A{r}", "1")
    for i in range(1, 2001):
        s.set(f"B{i}", f"=SUM(A$1:A{10 * i})")
    start = time.perf_counter()
    for i in range(3000):
        s.set(f"C{i + 1}", str(i))
    assert time.perf_counter() - start < 0.5


def test_sheet_exposes_only_the_public_api():
    public = {name for name in dir(Sheet) if not name.startswith("_")}
    assert public == {"set", "get", "get_raw", "insert_rows", "delete_rows", "insert_cols", "delete_cols", "copy"}
