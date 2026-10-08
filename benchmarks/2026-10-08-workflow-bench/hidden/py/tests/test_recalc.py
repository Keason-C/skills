"""set() return values, incremental recalculation, API address handling."""

import pytest

from gridcalc import CellError, Sheet


def is_err(v, code):
    return isinstance(v, CellError) and v.code == code


def is_num(v, x):
    return type(v) is float and v == pytest.approx(x)


# --- return lists -------------------------------------------------------------------

def test_set_new_literal_reports_itself():
    s = Sheet()
    assert s.set("A1", "1") == ["A1"]


def test_set_reports_dependents():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "=A1*2")
    assert s.set("A1", "2") == ["A1", "B1"]
    assert is_num(s.get("B1"), 4.0)


def test_return_sorted_row_major_with_numeric_columns_and_rows():
    s = Sheet()
    s.set("A10", "=A1+4")
    s.set("A2", "=A1+3")
    s.set("AA1", "=A1+2")
    s.set("B1", "=A1+1")
    assert s.set("A1", "1") == ["A1", "B1", "AA1", "A2", "A10"]


def test_return_sorted_when_edited_cell_is_not_first():
    s = Sheet()
    s.set("A1", "=C3*2")
    s.set("Z9", "=C3+1")
    assert s.set("C3", "5") == ["A1", "C3", "Z9"]


def test_diamond_reported_without_duplicates():
    s = Sheet()
    s.set("B1", "=A1+1")
    s.set("C1", "=A1*2")
    s.set("D1", "=B1+C1")
    assert s.set("A1", "1") == ["A1", "B1", "C1", "D1"]
    assert is_num(s.get("D1"), 4.0)


def test_cascade_through_chain():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "=A1+1")
    s.set("A3", "=A2+1")
    s.set("A4", "=A3+1")
    assert s.set("A1", "10") == ["A1", "A2", "A3", "A4"]
    assert is_num(s.get("A4"), 13.0)


def test_unchanged_dependent_not_reported_and_stops_cascade():
    s = Sheet()
    s.set("A1", "5")
    s.set("B1", "=IF(A1>0,1,0)")
    s.set("C1", "=B1*10")
    assert s.set("A1", "6") == ["A1"]
    assert s.set("A1", "-1") == ["A1", "B1", "C1"]
    assert is_num(s.get("C1"), 0.0)


def test_raw_change_with_equal_value_not_reported():
    s = Sheet()
    s.set("A1", "2")
    assert s.set("A1", "=1+1") == []
    assert s.get_raw("A1") == "=1+1"


def test_different_spelling_same_number_not_reported():
    s = Sheet()
    s.set("A1", "1")
    assert s.set("A1", "1.0") == []


def test_number_to_boolean_is_a_change():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "=A1+0")
    assert s.set("A1", "TRUE") == ["A1"]
    assert s.get("A1") is True
    assert is_num(s.get("B1"), 1.0)


def test_zero_to_false_is_a_change():
    s = Sheet()
    s.set("A1", "0")
    assert s.set("A1", "FALSE") == ["A1"]


def test_number_to_text_is_a_change():
    s = Sheet()
    s.set("A1", "1")
    assert s.set("A1", "'1") == ["A1"]
    assert s.get("A1") == "1"


def test_same_error_code_is_not_a_change():
    s = Sheet()
    s.set("A1", "=1/0")
    s.set("B1", "=A1+1")
    assert s.set("A1", "=5/0") == []
    assert is_err(s.get("B1"), "#DIV/0!")


def test_different_error_code_is_a_change():
    s = Sheet()
    s.set("A1", "=1/0")
    s.set("B1", "=A1+1")
    assert s.set("A1", "=NOSUCHFUNC(1)") == ["A1", "B1"]
    assert is_err(s.get("B1"), "#NAME?")


def test_clearing_reports_cell_and_dependents():
    s = Sheet()
    s.set("A1", "3")
    s.set("B1", "=A1*2")
    assert s.set("A1", "") == ["A1", "B1"]
    assert s.get("A1") is None
    assert is_num(s.get("B1"), 0.0)


def test_new_formula_over_empty_reports_itself():
    s = Sheet()
    assert s.set("B1", "=A1+0") == ["B1"]
    assert is_num(s.get("B1"), 0.0)


# --- dependency tracking -------------------------------------------------------------

def test_filling_empty_cell_inside_range_recalculates():
    s = Sheet()
    s.set("A1", "=SUM(B1:B100)")
    assert s.set("B50", "5") == ["A1", "B50"]
    assert is_num(s.get("A1"), 5.0)


def test_reference_set_after_formula():
    s = Sheet()
    s.set("A1", "=B1*2")
    s.set("B1", "3")
    assert is_num(s.get("A1"), 6.0)


def test_old_dependencies_dropped_when_formula_replaced():
    s = Sheet()
    s.set("A1", "=B1+0")
    s.set("A1", "5")
    assert s.set("B1", "9") == ["B1"]
    assert is_num(s.get("A1"), 5.0)


def test_old_dependencies_dropped_when_formula_rewritten():
    s = Sheet()
    s.set("A1", "=B1+C1")
    s.set("A1", "=C1*2")
    assert s.set("B1", "9") == ["B1"]
    assert s.set("C1", "4") == ["A1", "C1"]
    assert is_num(s.get("A1"), 8.0)


def test_untaken_if_branch_is_still_a_dependency():
    s = Sheet()
    s.set("B1", "1")
    s.set("C1", "10")
    s.set("D1", "20")
    s.set("A1", "=IF(B1>0,C1,D1)")
    assert is_num(s.get("A1"), 10.0)
    assert s.set("D1", "30") == ["D1"]
    assert s.set("B1", "-1") == ["A1", "B1"]
    assert is_num(s.get("A1"), 30.0)


# --- API addresses ----------------------------------------------------------------------

def test_lowercase_address_set_returns_canonical():
    s = Sheet()
    assert s.set("b3", "5") == ["B3"]


def test_lowercase_and_uppercase_address_same_cell():
    s = Sheet()
    s.set("b3", "5")
    assert is_num(s.get("B3"), 5.0)
    assert is_num(s.get("b3"), 5.0)
    assert s.get_raw("b3") == "5"


def test_mixed_case_multi_letter_column():
    s = Sheet()
    s.set("aA10", "x")
    assert s.get("AA10") == "x"


def test_last_cell_of_grid_is_valid():
    s = Sheet()
    assert s.set("XFD1048576", "1") == ["XFD1048576"]
    assert is_num(s.get("xfd1048576"), 1.0)


@pytest.mark.parametrize(
    "addr",
    ["A0", "A1048577", "XFE1", "1A", "", "A", "11", "A1B", "A-1", "A1:B2", "AAAA1"],
)
def test_set_bad_address_raises(addr):
    s = Sheet()
    with pytest.raises(ValueError):
        s.set(addr, "1")


@pytest.mark.parametrize("addr", ["A0", "XFE1", "B1048577", "?"])
def test_get_bad_address_raises(addr):
    s = Sheet()
    with pytest.raises(ValueError):
        s.get(addr)


@pytest.mark.parametrize("addr", ["A0", "ZZZZ1"])
def test_get_raw_bad_address_raises(addr):
    s = Sheet()
    with pytest.raises(ValueError):
        s.get_raw(addr)
