"""copy(src_range, dst_top_left)."""

import pytest

from gridcalc import CellError, Sheet


def is_err(v, code):
    return isinstance(v, CellError) and v.code == code


def is_num(v, x):
    return type(v) is float and v == pytest.approx(x)


# --- reference adjustment ----------------------------------------------------------

def test_relative_reference_shifted():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    s.set("B1", "=A1*2")
    assert s.copy("B1", "B2") == ["B2"]
    assert s.get_raw("B2") == "=A2*2"
    assert is_num(s.get("B2"), 4.0)


def test_source_unchanged_after_copy():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "=A1*2")
    s.copy("B1", "B2")
    assert s.get_raw("B1") == "=A1*2"
    assert is_num(s.get("B1"), 2.0)


def test_dollar_anchors():
    s = Sheet()
    s.set("B1", "=$A$1+A$1+$A1+A1")
    s.copy("B1", "C3")
    assert s.get_raw("C3") == "=$A$1+B$1+$A3+B3"


def test_dollar_anchors_values():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "10")
    s.set("A3", "100")
    s.set("B3", "1000")
    s.set("B2", "=$A$1+A$1+$A1+A1")
    s.copy("B2", "C4")
    # $A$1 + B$1 + $A3 + B3
    assert is_num(s.get("C4"), 1111.0)


def test_range_reference_shifted():
    s = Sheet()
    s.set("A2", "3")
    s.set("B2", "4")
    s.set("C1", "=SUM(A1:B1)")
    s.copy("C1", "C2")
    assert s.get_raw("C2") == "=SUM(A2:B2)"
    assert is_num(s.get("C2"), 7.0)


def test_range_reference_mixed_anchors():
    s = Sheet()
    s.set("B1", "=SUM($A1:A$5)")
    s.copy("B1", "C3")
    assert s.get_raw("C3") == "=SUM($A3:B$5)"


def test_string_literal_not_rewritten():
    s = Sheet()
    s.set("B1", '=IF(A1>0,"A1",A2)')
    s.copy("B1", "C1")
    assert s.get_raw("C1") == '=IF(B1>0,"A1",B2)'


def test_reference_leaving_grid_left_becomes_ref():
    s = Sheet()
    s.set("B1", "=A1+1")
    s.copy("B1", "A1")
    assert s.get_raw("A1") == "=#REF!+1"
    assert is_err(s.get("A1"), "#REF!")


def test_reference_leaving_grid_top_becomes_ref():
    s = Sheet()
    s.set("A2", "=A1+1")
    s.copy("A2", "B1")
    assert s.get_raw("B1") == "=#REF!+1"
    assert is_err(s.get("B1"), "#REF!")


def test_reference_leaving_grid_right_becomes_ref():
    s = Sheet()
    s.set("A1", "=B1+1")
    s.copy("A1", "XFD1")
    assert s.get_raw("XFD1") == "=#REF!+1"
    assert is_err(s.get("XFD1"), "#REF!")


def test_absolute_reference_survives_far_copy():
    s = Sheet()
    s.set("A1", "5")
    s.set("B2", "=$A$1*2")
    s.copy("B2", "XFD1")
    assert s.get_raw("XFD1") == "=$A$1*2"
    assert is_num(s.get("XFD1"), 10.0)


def test_copy_to_last_cell_of_grid():
    s = Sheet()
    s.set("A1", "7")
    assert s.copy("A1", "XFD1048576") == ["XFD1048576"]
    assert is_num(s.get("XFD1048576"), 7.0)


# --- literals and blocks ------------------------------------------------------------------

def test_literal_raw_copied_exactly():
    s = Sheet()
    s.set("A1", "'123")
    s.set("A2", " 42 ")
    s.copy("A1:A2", "C1")
    assert s.get_raw("C1") == "'123"
    assert s.get("C1") == "123"
    assert s.get_raw("C2") == " 42 "
    assert is_num(s.get("C2"), 42.0)


def test_block_copy():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "=A1+1")
    s.set("A2", "x")
    s.set("B2", "=B1*2")
    changed = s.copy("A1:B2", "D5")
    assert changed == ["D5", "E5", "D6", "E6"]
    assert s.get_raw("E5") == "=D5+1"
    assert s.get_raw("E6") == "=E5*2"
    assert is_num(s.get("D5"), 1.0)
    assert is_num(s.get("E5"), 2.0)
    assert s.get("D6") == "x"
    assert is_num(s.get("E6"), 4.0)


def test_block_copy_lowercase_addresses():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "2")
    assert s.copy("a1:b1", "c3") == ["C3", "D3"]


def test_empty_source_clears_destination():
    s = Sheet()
    s.set("C1", "9")
    assert s.copy("A1", "C1") == ["C1"]
    assert s.get("C1") is None
    assert s.get_raw("C1") == ""


def test_empty_cells_in_block_clear_destination():
    s = Sheet()
    s.set("A1", "1")
    s.set("C1", "x")
    s.set("C2", "y")
    s.copy("A1:A2", "C1")
    assert is_num(s.get("C1"), 1.0)
    assert s.get("C2") is None
    assert s.get_raw("C2") == ""


# --- overlapping copies ---------------------------------------------------------------------

def test_overlapping_copy_down_reads_source_first():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    s.set("A3", "3")
    s.copy("A1:A3", "A2")
    assert [s.get(f"A{i}") for i in range(1, 5)] == [1.0, 1.0, 2.0, 3.0]


def test_overlapping_copy_right_reads_source_first():
    s = Sheet()
    s.set("A1", "x")
    s.set("B1", "y")
    s.set("C1", "z")
    s.copy("A1:C1", "B1")
    assert [s.get(a) for a in ("A1", "B1", "C1", "D1")] == ["x", "x", "y", "z"]


def test_overlapping_copy_up():
    s = Sheet()
    s.set("A2", "2")
    s.set("A3", "3")
    s.set("A4", "4")
    s.copy("A2:A4", "A1")
    assert [s.get(f"A{i}") for i in range(1, 5)] == [2.0, 3.0, 4.0, 4.0]


def test_overlapping_copy_with_formulas():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "=A1+1")
    s.copy("A1:A2", "A2")
    assert s.get_raw("A2") == "1"
    assert s.get_raw("A3") == "=A2+1"
    assert is_num(s.get("A3"), 2.0)


def test_overlapping_2d_copy_and_return():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "2")
    s.set("A2", "3")
    s.set("B2", "4")
    changed = s.copy("A1:B2", "B2")
    assert changed == ["B2", "C2", "B3", "C3"]
    assert [s.get(a) for a in ("A1", "B1", "A2")] == [1.0, 2.0, 3.0]
    assert [s.get(a) for a in ("B2", "C2", "B3", "C3")] == [1.0, 2.0, 3.0, 4.0]


# --- return value and recalculation ------------------------------------------------------

def test_return_includes_dependents():
    s = Sheet()
    s.set("A1", "3")
    s.set("D1", "=C1*2")
    assert s.copy("A1", "C1") == ["C1", "D1"]
    assert is_num(s.get("D1"), 6.0)


def test_return_excludes_unchanged_values():
    s = Sheet()
    s.set("A1", "5")
    s.set("C1", "=2+3")
    assert s.copy("A1", "C1") == []
    assert s.get_raw("C1") == "5"


def test_copy_onto_itself_returns_empty():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "=A1+1")
    assert s.copy("A1:B1", "A1") == []
    assert s.get_raw("B1") == "=A1+1"


def test_copied_formula_tracks_new_dependency():
    s = Sheet()
    s.set("B1", "=A1*2")
    s.copy("B1", "B2")
    assert s.set("A2", "7") == ["A2", "B2"]
    assert is_num(s.get("B2"), 14.0)
