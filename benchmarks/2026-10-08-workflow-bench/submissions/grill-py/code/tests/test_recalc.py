from gridcalc import CellError, Sheet

CYCLE = CellError("#CYCLE!")
DIV0 = CellError("#DIV/0!")


def test_dependents_recalculate_and_are_reported_sorted():
    s = Sheet()
    s.set("A1", "1")
    s.set("B2", "=A1*2")
    s.set("C1", "=A1+B2")
    s.set("A3", "=C1")
    assert s.set("A1", "5") == ["A1", "C1", "B2", "A3"]
    assert s.get("B2") == 10.0
    assert s.get("C1") == 15.0
    assert s.get("A3") == 15.0


def test_change_list_orders_by_row_then_column():
    s = Sheet()
    s.set("AA1", "=B2")
    s.set("C1", "=B2")
    s.set("A2", "=B2")
    assert s.set("B2", "1") == ["C1", "AA1", "A2", "B2"]


def test_unchanged_values_are_not_reported():
    s = Sheet()
    s.set("A1", "2")
    s.set("B1", "=A1>0")
    s.set("C1", "=B1")
    assert s.set("A1", "3") == ["A1"]
    assert s.set("A1", "=1+2") == []
    assert s.set("B1", "=TRUE") == []


def test_formula_cell_reported_when_its_own_value_changes():
    s = Sheet()
    assert s.set("A1", "=1+1") == ["A1"]
    assert s.set("A1", "=4/2") == []
    assert s.set("A1", "") == ["A1"]


def test_errors_with_same_code_are_equal():
    s = Sheet()
    s.set("A1", "=1/0")
    s.set("B1", "=A1+1")
    assert s.set("A1", "=2/0") == []


def test_float_and_bool_differ():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "=A1")
    assert s.set("A1", "TRUE") == ["A1", "B1"]
    assert s.get("B1") is True


def test_formula_referencing_cleared_cell():
    s = Sheet()
    s.set("A1", "7")
    s.set("B1", "=A1")
    assert s.set("A1", "") == ["A1", "B1"]
    assert s.get("B1") == 0.0


def test_range_dependents_recalculate():
    s = Sheet()
    s.set("A1", "=SUM(B1:C10)")
    assert s.set("C7", "4") == ["A1", "C7"]
    assert s.set("B10", "1") == ["A1", "B10"]
    assert s.set("D10", "1") == ["D10"]
    assert s.get("A1") == 5.0


def test_huge_range_dependency():
    s = Sheet()
    s.set("A1", "=COUNT(B1:XFD1048576)")
    assert s.set("XFD1048576", "1") == ["A1", "XFD1048576"]
    assert s.get("A1") == 1.0


def test_dependencies_are_static_regardless_of_if_branch():
    s = Sheet()
    s.set("A1", "=IF(TRUE, 1, B1)")
    s.set("B1", "=A1")
    assert s.get("A1") == CYCLE
    assert s.get("B1") == CYCLE


def test_unknown_function_arguments_are_still_dependencies():
    s = Sheet()
    s.set("A1", "=NOPE(A1)")
    assert s.get("A1") == CYCLE


def test_unparseable_formula_has_no_dependencies():
    s = Sheet()
    s.set("A1", "=A1+")
    assert s.get("A1") == CellError("#PARSE!")


# -- cycles --------------------------------------------------------------------


def test_self_reference_is_cycle():
    s = Sheet()
    assert s.set("A1", "=A1+1") == ["A1"]
    assert s.get("A1") == CYCLE


def test_self_reference_through_range_is_cycle():
    s = Sheet()
    s.set("B2", "=SUM(A1:C3)")
    assert s.get("B2") == CYCLE


def test_cycle_members_and_dependents():
    s = Sheet()
    s.set("A1", "=B1")
    s.set("B1", "=C1")
    s.set("D1", "=A1+1")
    s.set("E1", "=IFERROR(A1, 0)")
    s.set("C1", "=A1")
    assert s.get("A1") == CYCLE
    assert s.get("B1") == CYCLE
    assert s.get("C1") == CYCLE
    assert s.get("D1") == CYCLE  # propagated, not itself on the cycle
    assert s.get("E1") == 0.0


def test_iferror_on_cycle_member_is_still_cycle():
    s = Sheet()
    s.set("A1", "=IFERROR(B1, 5)")
    s.set("B1", "=A1")
    assert s.get("A1") == CYCLE
    assert s.get("B1") == CYCLE


def test_breaking_cycle_restores_values():
    s = Sheet()
    s.set("A1", "=B1+1")
    s.set("B1", "=C1+1")
    s.set("D1", "=A1*10")
    assert s.set("C1", "=A1+1") == ["A1", "B1", "C1", "D1"]
    assert s.get("D1") == CYCLE
    changed = s.set("B1", "5")
    assert changed == ["A1", "B1", "C1", "D1"]
    assert (s.get("A1"), s.get("B1"), s.get("C1"), s.get("D1")) == (6.0, 5.0, 7.0, 60.0)


def test_breaking_cycle_by_editing_any_member():
    s = Sheet()
    s.set("A1", "=B1")
    s.set("B1", "=A1")
    s.set("A1", "3")
    assert s.get("A1") == 3.0
    assert s.get("B1") == 3.0


def test_cycle_report_does_not_repeat_unchanged_cycle_cells():
    s = Sheet()
    s.set("A1", "=B1")
    s.set("B1", "=A1")
    assert s.set("A1", "=B1+0") == []


def test_two_independent_cycles():
    s = Sheet()
    s.set("A1", "=A2")
    s.set("A2", "=A1")
    s.set("B1", "=B2")
    s.set("B2", "=B1+A1")
    assert s.get("B2") == CYCLE
    s.set("A1", "1")
    assert s.get("A2") == 1.0
    assert s.get("B1") == CYCLE


def test_cycle_downstream_error_propagation_resolves():
    s = Sheet()
    s.set("A1", "=A1")
    s.set("B1", "=A1")
    s.set("C1", "=B1")
    assert s.get("C1") == CYCLE
    assert s.set("A1", "2") == ["A1", "B1", "C1"]
    assert s.get("C1") == 2.0


def test_long_chain_has_no_recursion_error():
    s = Sheet()
    n = 20000
    s.set("A1", "1")
    for r in range(2, n + 1):
        s.set(f"A{r}", f"=A{r - 1}+1")
    assert s.get(f"A{n}") == float(n)
    changed = s.set("A1", "10")
    assert len(changed) == n
    assert s.get(f"A{n}") == float(n + 9)


def test_long_cycle_has_no_recursion_error():
    s = Sheet()
    n = 20000
    for r in range(
        n - 1, 0, -1
    ):  # each new cell is the start of the chain: O(1) per set
        s.set(f"A{r}", f"=A{r + 1}")
    s.set(f"A{n}", "=A1")
    assert s.get("A1") == CYCLE
    assert s.get(f"A{n // 2}") == CYCLE
    s.set(f"A{n}", "4")
    assert s.get("A1") == 4.0


def test_chain_built_backwards():
    s = Sheet()
    s.set("A3", "=A2*2")
    s.set("A2", "=A1+1")
    assert s.set("A1", "1") == ["A1", "A2", "A3"]
    assert s.get("A3") == 4.0


def test_diamond_dependency_evaluates_once_in_order():
    s = Sheet()
    s.set("B1", "=A1+1")
    s.set("C1", "=A1*2")
    s.set("D1", "=B1+C1")
    s.set("A1", "3")
    assert s.get("D1") == 10.0
