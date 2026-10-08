"""insert_rows / delete_rows / insert_cols / delete_cols."""

import pytest

from gridcalc import CellError, Sheet


def is_err(v, code):
    return isinstance(v, CellError) and v.code == code


def is_num(v, x):
    return type(v) is float and v == pytest.approx(x)


def column_sheet():
    """A2..A6 = 10,20,30,40,50 and B10 = =SUM(A2:A6) (=150)."""
    s = Sheet()
    for i, v in zip(range(2, 7), [10, 20, 30, 40, 50]):
        s.set(f"A{i}", str(v))
    s.set("B10", "=SUM(A2:A6)")
    return s


def row_sheet():
    """B1..F1 = 1..5 and A3 = =SUM(B1:F1) (=15)."""
    s = Sheet()
    for col, v in zip("BCDEF", range(1, 6)):
        s.set(f"{col}1", str(v))
    s.set("A3", "=SUM(B1:F1)")
    return s


# --- return value / basic movement -------------------------------------------------

def test_structural_edits_return_none():
    s = Sheet()
    s.set("A1", "1")
    assert s.insert_rows(1) is None
    assert s.delete_rows(1) is None
    assert s.insert_cols(1) is None
    assert s.delete_cols(1) is None


def test_insert_rows_moves_cells_down():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    s.insert_rows(2)
    assert is_num(s.get("A1"), 1.0)
    assert s.get("A2") is None
    assert is_num(s.get("A3"), 2.0)


def test_insert_rows_rewrites_references():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    s.set("A3", "=A1+A2")
    s.insert_rows(2)
    assert s.get_raw("A4") == "=A1+A3"
    assert is_num(s.get("A4"), 3.0)
    assert s.get_raw("A3") == "2"


def test_insert_multiple_rows():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    s.set("B1", "=A2+A1")
    s.insert_rows(2, 3)
    assert is_num(s.get("A5"), 2.0)
    assert s.get_raw("B1") == "=A5+A1"
    assert is_num(s.get("B1"), 3.0)


def test_delete_rows_moves_cells_up_and_rewrites():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    s.set("A3", "3")
    s.set("A4", "=A1+A3")
    s.delete_rows(2)
    assert is_num(s.get("A2"), 3.0)
    assert s.get_raw("A3") == "=A1+A2"
    assert is_num(s.get("A3"), 4.0)
    assert s.get("A4") is None


def test_delete_multiple_rows_shifts_reference_below():
    s = Sheet()
    s.set("A10", "4")
    s.set("C5", "=A10*2")
    s.delete_rows(2, 3)
    assert s.get_raw("C2") == "=A7*2"
    assert is_num(s.get("C2"), 8.0)


def test_insert_cols_rewrites_references():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "2")
    s.set("C1", "=A1+B1")
    s.insert_cols(2)
    assert s.get_raw("D1") == "=A1+C1"
    assert is_num(s.get("D1"), 3.0)
    assert is_num(s.get("C1"), 2.0)
    assert s.get("B1") is None


def test_delete_cols_moves_cells_left():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "2")
    s.set("C1", "3")
    s.set("D1", "=C1*10")
    s.delete_cols(2)
    assert is_num(s.get("B1"), 3.0)
    assert s.get_raw("C1") == "=B1*10"
    assert is_num(s.get("C1"), 30.0)
    assert s.get("D1") is None


# --- $ markers -------------------------------------------------------------------------

def test_dollar_refs_still_shift_on_insert_rows():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    s.set("A3", "3")
    s.set("B5", "=$A$1+A$2+$A3")
    s.insert_rows(1)
    assert s.get_raw("B6") == "=$A$2+A$3+$A4"
    assert is_num(s.get("B6"), 6.0)


def test_dollar_refs_shift_on_delete_rows():
    s = Sheet()
    s.set("A10", "4")
    s.set("C5", "=$A$10*2")
    s.delete_rows(2, 3)
    assert s.get_raw("C2") == "=$A$7*2"
    assert is_num(s.get("C2"), 8.0)


def test_dollar_refs_shift_on_insert_cols():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "2")
    s.set("C1", "=$A$1+$B1")
    s.insert_cols(1)
    assert s.get_raw("D1") == "=$B$1+$C1"
    assert is_num(s.get("D1"), 3.0)


# --- #REF! for deleted single references ------------------------------------------------

def test_reference_to_deleted_row_becomes_ref():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    s.set("B1", "=A2*2")
    s.delete_rows(2)
    assert s.get_raw("B1") == "=#REF!*2"
    assert is_err(s.get("B1"), "#REF!")


def test_reference_to_deleted_col_becomes_ref():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "2")
    s.set("C1", "=A1*B1")
    s.delete_cols(1)
    assert s.get_raw("B1") == "=#REF!*A1"
    assert is_err(s.get("B1"), "#REF!")


def test_ref_error_propagates_to_dependents():
    s = Sheet()
    s.set("A2", "2")
    s.set("B1", "=A2*2")
    s.set("C1", "=B1+1")
    s.delete_rows(2)
    assert is_err(s.get("C1"), "#REF!")


def test_deleted_formula_cell_dependents_get_ref():
    s = Sheet()
    s.set("B2", "=1+1")
    s.set("C5", "=B2*2")
    s.delete_rows(2)
    assert s.get_raw("C4") == "=#REF!*2"
    assert is_err(s.get("C4"), "#REF!")


# --- range rules: rows ------------------------------------------------------------------

def test_delete_rows_inside_range_shrinks_it():
    s = Sheet()
    for i in range(1, 6):
        s.set(f"A{i}", str(i))
    s.set("B1", "=SUM(A1:A5)")
    s.delete_rows(3)
    assert s.get_raw("B1") == "=SUM(A1:A4)"
    assert is_num(s.get("B1"), 12.0)


def test_delete_first_row_of_range():
    s = column_sheet()
    s.delete_rows(2)
    assert s.get_raw("B9") == "=SUM(A2:A5)"
    assert is_num(s.get("B9"), 140.0)


def test_delete_last_row_of_range():
    s = column_sheet()
    s.delete_rows(6)
    assert s.get_raw("B9") == "=SUM(A2:A5)"
    assert is_num(s.get("B9"), 100.0)


def test_delete_rows_spanning_last_endpoint_and_beyond():
    s = column_sheet()
    s.delete_rows(5, 3)
    assert s.get_raw("B7") == "=SUM(A2:A4)"
    assert is_num(s.get("B7"), 60.0)


def test_delete_rows_spanning_first_endpoint_from_above():
    s = column_sheet()
    s.delete_rows(1, 3)
    assert s.get_raw("B7") == "=SUM(A1:A3)"
    assert is_num(s.get("B7"), 120.0)


def test_delete_all_rows_of_range_gives_ref():
    s = column_sheet()
    s.delete_rows(2, 5)
    assert s.get_raw("B5") == "=SUM(#REF!)"
    assert is_err(s.get("B5"), "#REF!")


def test_insert_rows_strictly_inside_range_grows_it():
    s = column_sheet()
    s.insert_rows(4, 2)
    assert s.get_raw("B12") == "=SUM(A2:A8)"
    assert is_num(s.get("B12"), 150.0)


def test_insert_at_last_row_of_range_grows_it():
    s = column_sheet()
    s.insert_rows(6)
    assert s.get_raw("B11") == "=SUM(A2:A7)"
    assert is_num(s.get("B11"), 150.0)
    assert is_num(s.get("A7"), 50.0)


def test_insert_at_first_row_of_range_shifts_it():
    s = column_sheet()
    s.insert_rows(2)
    assert s.get_raw("B11") == "=SUM(A3:A7)"
    assert is_num(s.get("B11"), 150.0)


def test_insert_above_range_shifts_it():
    s = column_sheet()
    s.insert_rows(1)
    assert s.get_raw("B11") == "=SUM(A3:A7)"


def test_insert_directly_below_range_leaves_it():
    s = column_sheet()
    s.insert_rows(7)
    assert s.get_raw("B11") == "=SUM(A2:A6)"
    assert is_num(s.get("B11"), 150.0)


def test_grown_range_includes_new_row_values():
    s = column_sheet()
    s.insert_rows(4)
    s.set("A4", "100")
    assert is_num(s.get("B11"), 250.0)


def test_dollar_range_shrinks_and_keeps_markers():
    s = Sheet()
    for i, v in zip(range(2, 7), [10, 20, 30, 40, 50]):
        s.set(f"A{i}", str(v))
    s.set("B10", "=SUM($A$2:$A$6)")
    s.delete_rows(3)
    assert s.get_raw("B9") == "=SUM($A$2:$A$5)"
    assert is_num(s.get("B9"), 130.0)


def test_two_dimensional_range_delete_row():
    s = Sheet()
    n = 1
    for r in range(1, 4):
        for c in "ABC":
            s.set(f"{c}{r}", str(n))
            n += 1
    s.set("E10", "=SUM(A1:C3)")
    s.delete_rows(2)
    assert s.get_raw("E9") == "=SUM(A1:C2)"
    assert is_num(s.get("E9"), 30.0)


# --- range rules: columns ---------------------------------------------------------------

def test_delete_first_col_of_range():
    s = row_sheet()
    s.delete_cols(2)
    assert s.get_raw("A3") == "=SUM(B1:E1)"
    assert is_num(s.get("A3"), 14.0)


def test_delete_cols_inside_range_shrinks_it():
    s = row_sheet()
    s.delete_cols(3, 2)
    assert s.get_raw("A3") == "=SUM(B1:D1)"
    assert is_num(s.get("A3"), 10.0)


def test_delete_all_cols_of_range_gives_ref():
    s = row_sheet()
    s.delete_cols(2, 5)
    assert s.get_raw("A3") == "=SUM(#REF!)"
    assert is_err(s.get("A3"), "#REF!")


def test_insert_col_inside_range_grows_it():
    s = row_sheet()
    s.insert_cols(4)
    assert s.get_raw("A3") == "=SUM(B1:G1)"
    assert is_num(s.get("A3"), 15.0)


def test_insert_col_directly_right_of_range_leaves_it():
    s = row_sheet()
    s.insert_cols(7)
    assert s.get_raw("A3") == "=SUM(B1:F1)"


def test_insert_col_at_first_col_of_range_shifts_it():
    s = row_sheet()
    s.insert_cols(2)
    assert s.get_raw("A3") == "=SUM(C1:G1)"
    assert is_num(s.get("A3"), 15.0)


# --- raw text preservation ---------------------------------------------------------------

def test_string_literal_with_ref_like_text_untouched():
    s = Sheet()
    s.set("A1", "1")
    s.set("D10", '=IF(A1>0,"A1 ok",B2)')
    s.insert_rows(1)
    assert s.get_raw("D11") == '=IF(A2>0,"A1 ok",B3)'
    assert s.get("D11") == "A1 ok"


def test_number_spelling_preserved_around_rewritten_token():
    s = Sheet()
    s.set("A1", "2")
    s.set("D10", "=A1*1.50+0.5E1")
    s.insert_rows(1)
    assert s.get_raw("D11") == "=A2*1.50+0.5E1"
    assert is_num(s.get("D11"), 8.0)


def test_formula_without_affected_refs_unchanged():
    s = Sheet()
    s.set("A1", "1")
    s.set("B2", "2")
    s.set("C1", "=$A$1+B2")
    s.insert_rows(5)
    assert s.get_raw("C1") == "=$A$1+B2"


def test_only_affected_token_rewritten():
    s = Sheet()
    s.set("C1", "=A1+B5")
    s.insert_rows(3)
    assert s.get_raw("C1") == "=A1+B6"


def test_literal_text_that_looks_like_ref_not_rewritten():
    s = Sheet()
    s.set("A5", "A1")
    s.set("A6", " 42 ")
    s.insert_rows(1)
    assert s.get_raw("A6") == "A1"
    assert s.get_raw("A7") == " 42 "


# --- recalculation / dependencies after edits ------------------------------------------------

def test_dependencies_follow_moved_cells():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "=A1*10")
    s.insert_rows(1)
    assert s.get_raw("B2") == "=A2*10"
    assert s.set("A2", "3") == ["A2", "B2"]
    assert is_num(s.get("B2"), 30.0)


def test_dependencies_after_delete_rows():
    s = Sheet()
    s.set("A1", "1")
    s.set("A3", "3")
    s.set("B4", "=A3+1")
    s.delete_rows(2)
    assert s.get_raw("B3") == "=A2+1"
    s.set("A2", "10")
    assert is_num(s.get("B3"), 11.0)


# --- grid boundary ----------------------------------------------------------------------------

def test_cell_pushed_beyond_last_row_is_dropped():
    s = Sheet()
    s.set("A1048576", "5")
    s.insert_rows(1)
    assert s.get("A1048576") is None
    assert s.get_raw("A1048576") == ""


def test_cell_pushed_beyond_last_col_is_dropped():
    s = Sheet()
    s.set("XFD1", "x")
    s.insert_cols(1)
    assert s.get("XFD1") is None


def test_reference_pushed_beyond_grid_becomes_ref():
    s = Sheet()
    s.set("B1", "=A1048576+1")
    s.insert_rows(1)
    assert s.get_raw("B2") == "=#REF!+1"
    assert is_err(s.get("B2"), "#REF!")


def test_reference_shifted_to_last_row_ok():
    s = Sheet()
    s.set("A1048575", "7")
    s.set("B1", "=A1048575+1")
    s.insert_rows(1)
    assert s.get_raw("B2") == "=A1048576+1"
    assert is_num(s.get("B2"), 8.0)


def test_col_reference_pushed_beyond_grid_becomes_ref():
    s = Sheet()
    s.set("A1", "=XFD1+1")
    s.insert_cols(1)
    assert s.get_raw("B1") == "=#REF!+1"
    assert is_err(s.get("B1"), "#REF!")
