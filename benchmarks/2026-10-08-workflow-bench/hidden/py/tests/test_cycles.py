"""Static cycle detection, propagation to dependents, and breaking cycles."""

import pytest

from gridcalc import CellError, Sheet


def is_err(v, code):
    return isinstance(v, CellError) and v.code == code


def is_num(v, x):
    return type(v) is float and v == pytest.approx(x)


def test_self_reference_is_cycle():
    s = Sheet()
    s.set("A1", "=A1+1")
    assert is_err(s.get("A1"), "#CYCLE!")


def test_bare_self_reference_is_cycle():
    s = Sheet()
    s.set("A1", "=A1")
    assert is_err(s.get("A1"), "#CYCLE!")


def test_iferror_does_not_hide_own_cycle():
    s = Sheet()
    s.set("A1", "=IFERROR(A1,5)")
    assert is_err(s.get("A1"), "#CYCLE!")


def test_two_cell_cycle():
    s = Sheet()
    s.set("A1", "=B1+1")
    s.set("B1", "=A1+1")
    assert is_err(s.get("A1"), "#CYCLE!")
    assert is_err(s.get("B1"), "#CYCLE!")


def test_three_cell_cycle():
    s = Sheet()
    s.set("A1", "=B1")
    s.set("B1", "=C1")
    s.set("C1", "=A1")
    for a in ("A1", "B1", "C1"):
        assert is_err(s.get(a), "#CYCLE!")


def test_dependent_of_cycle_gets_propagated_cycle_error():
    s = Sheet()
    s.set("A1", "=B1+1")
    s.set("B1", "=A1+1")
    s.set("C1", "=A1*2")
    s.set("D1", "=C1+1")
    assert is_err(s.get("C1"), "#CYCLE!")
    assert is_err(s.get("D1"), "#CYCLE!")


def test_dependent_of_cycle_can_catch_with_iferror():
    s = Sheet()
    s.set("A1", "=B1+1")
    s.set("B1", "=A1+1")
    s.set("C1", "=IFERROR(A1,5)")
    assert is_num(s.get("C1"), 5.0)


def test_cycle_through_untaken_if_branch_is_static():
    s = Sheet()
    s.set("A1", "=IF(FALSE,B1,1)")
    s.set("B1", "=A1+1")
    assert is_err(s.get("A1"), "#CYCLE!")
    assert is_err(s.get("B1"), "#CYCLE!")


def test_cycle_through_untaken_iferror_fallback_is_static():
    s = Sheet()
    s.set("A1", "=IFERROR(7,B1)")
    s.set("B1", "=A1+1")
    assert is_err(s.get("A1"), "#CYCLE!")
    assert is_err(s.get("B1"), "#CYCLE!")


def test_cycle_through_range():
    s = Sheet()
    s.set("A1", "=SUM(A2:A3)")
    s.set("A2", "1")
    s.set("A3", "=A1+1")
    assert is_err(s.get("A1"), "#CYCLE!")
    assert is_err(s.get("A3"), "#CYCLE!")
    assert is_num(s.get("A2"), 1.0)


def test_range_containing_itself_is_cycle():
    s = Sheet()
    s.set("A1", "1")
    s.set("A3", "2")
    s.set("A2", "=SUM(A1:A3)")
    assert is_err(s.get("A2"), "#CYCLE!")


def test_diamond_is_not_a_cycle():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "=A1+1")
    s.set("C1", "=A1*3")
    s.set("D1", "=B1+C1")
    assert is_num(s.get("D1"), 5.0)


def test_unrelated_cell_unaffected_by_cycle():
    s = Sheet()
    s.set("A1", "=B1+1")
    s.set("B1", "=A1+1")
    s.set("E5", "4")
    s.set("E6", "=E5*2")
    assert is_num(s.get("E6"), 8.0)


def test_closing_a_cycle_reports_all_members():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "=A1+1")
    s.set("C1", "=B1+1")
    changed = s.set("A1", "=C1+1")
    assert changed == ["A1", "B1", "C1"]
    for a in ("A1", "B1", "C1"):
        assert is_err(s.get(a), "#CYCLE!")


def test_breaking_cycle_by_literal_restores_values():
    s = Sheet()
    s.set("A1", "=B1+1")
    s.set("B1", "=A1+1")
    s.set("C1", "=A1*2")
    changed = s.set("B1", "5")
    assert changed == ["A1", "B1", "C1"]
    assert is_num(s.get("A1"), 6.0)
    assert is_num(s.get("B1"), 5.0)
    assert is_num(s.get("C1"), 12.0)


def test_breaking_cycle_by_clearing_restores_values():
    s = Sheet()
    s.set("A1", "=B1+1")
    s.set("B1", "=A1+1")
    s.set("B1", "")
    assert is_num(s.get("A1"), 1.0)
    assert s.get("B1") is None


def test_breaking_static_if_cycle_restores_values():
    s = Sheet()
    s.set("A1", "=IF(FALSE,B1,1)")
    s.set("B1", "=A1+1")
    s.set("B1", "3")
    assert is_num(s.get("A1"), 1.0)
    assert is_num(s.get("B1"), 3.0)


def test_breaking_three_cycle_restores_all():
    s = Sheet()
    s.set("A1", "=B1+1")
    s.set("B1", "=C1+1")
    s.set("C1", "=A1+1")
    s.set("C1", "10")
    assert is_num(s.get("C1"), 10.0)
    assert is_num(s.get("B1"), 11.0)
    assert is_num(s.get("A1"), 12.0)


def test_cycle_raw_text_unchanged():
    s = Sheet()
    s.set("A1", "=B1+1")
    s.set("B1", "=A1+1")
    assert s.get_raw("A1") == "=B1+1"


def test_long_cycle_detected_and_broken():
    n = 2000
    s = Sheet()
    s.set("A1", "1")
    for i in range(2, n + 1):
        s.set(f"A{i}", f"=A{i - 1}+1")
    s.set("A1", f"=A{n}+1")
    assert is_err(s.get("A1"), "#CYCLE!")
    assert is_err(s.get(f"A{n}"), "#CYCLE!")
    assert is_err(s.get(f"A{n // 2}"), "#CYCLE!")
    s.set("A1", "1")
    assert is_num(s.get(f"A{n}"), float(n))
