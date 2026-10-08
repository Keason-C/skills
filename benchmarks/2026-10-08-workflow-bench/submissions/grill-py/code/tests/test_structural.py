import pytest

from gridcalc import CellError, Sheet

REF = CellError("#REF!")
PARSE = CellError("#PARSE!")


# -- inserting rows ------------------------------------------------------------


def test_insert_rows_moves_cells_and_rewrites_references():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    s.set("A3", "=A1+A2")
    assert s.insert_rows(2) is None
    assert s.get("A2") is None
    assert s.get_raw("A2") == ""
    assert s.get("A3") == 2.0
    assert s.get_raw("A4") == "=A1+A3"
    assert s.get("A4") == 3.0


def test_insert_multiple_rows():
    s = Sheet()
    s.set("B2", "x")
    s.set("C1", "=B2")
    s.insert_rows(1, 3)
    assert s.get("B5") == "x"
    assert s.get_raw("C4") == "=B5"
    assert s.get("C4") == "x"


@pytest.mark.parametrize(
    "formula, at, expected",
    [
        ("=$A$2", 1, "=$A$3"),
        ("=A$2+$A2", 2, "=A$3+$A3"),
        ("=a1+a5", 3, "=a1+A6"),
        ("=A1", 2, "=A1"),
        ("=SUM(A2:A4)", 1, "=SUM(A3:A5)"),
        ("=SUM(A2:A4)", 2, "=SUM(A3:A5)"),
        ("=SUM(A2:A4)", 3, "=SUM(A2:A5)"),
        ("=SUM(A2:A4)", 4, "=SUM(A2:A5)"),
        ("=SUM(A2:A4)", 5, "=SUM(A2:A4)"),
        ("=SUM(A4:A2)", 1, "=SUM(A3:A5)"),
        ("=SUM(A4:A2)", 9, "=SUM(A4:A2)"),
        ("=SUM($B3:A$1)", 1, "=SUM(A$2:$B4)"),
        ("=SUM( a2 : a4 )", 3, "=SUM( A2:A5 )"),
        ("=A5+XFE5+#REF!", 1, "=A6+XFE5+#REF!"),
        ("=A5+", 1, "=A5+"),
        ('="A5"&A5', 1, '="A5"&A6'),
    ],
)
def test_insert_rows_rewrites(formula, at, expected):
    s = Sheet()
    s.set("Z1", formula)
    s.insert_rows(at)
    moved = "Z2" if at == 1 else "Z1"
    assert s.get_raw(moved) == expected


def test_insert_rows_pushes_cells_off_grid():
    s = Sheet()
    s.set("A1048576", "bottom")
    s.set("A1048575", "next")
    s.set("B1", "=A1048576")
    s.set("C1", "=SUM(A5:A1048576)")
    s.set("D1", "=SUM(A1048576:B1048576)")
    s.insert_rows(1)
    assert s.get("A1048576") == "next"
    assert s.get_raw("B2") == "=#REF!"
    assert s.get("B2") == REF
    assert s.get_raw("C2") == "=SUM(A6:A1048576)"
    assert s.get_raw("D2") == "=SUM(#REF!)"


def test_insert_rows_values_recalculate():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    s.set("A3", "=SUM(A1:A2)")
    s.insert_rows(2)
    s.set("A2", "10")
    assert s.get_raw("A4") == "=SUM(A1:A3)"
    assert s.get("A4") == 13.0


# -- deleting rows -------------------------------------------------------------


@pytest.mark.parametrize(
    "formula, at, count, expected",
    [
        ("=A2+1", 2, 1, "=#REF!+1"),
        ("=A5", 2, 2, "=A3"),
        ("=$A$5", 2, 2, "=$A$3"),
        ("=A1", 2, 2, "=A1"),
        ("=SUM(A2:A6)", 3, 2, "=SUM(A2:A4)"),
        ("=SUM(A2:A6)", 2, 1, "=SUM(A2:A5)"),
        ("=SUM(A2:A6)", 1, 2, "=SUM(A1:A4)"),
        ("=SUM(A2:A6)", 6, 1, "=SUM(A2:A5)"),
        ("=SUM(A2:A6)", 5, 3, "=SUM(A2:A4)"),
        ("=SUM(A2:A6)", 1, 7, "=SUM(#REF!)"),
        ("=SUM(A2:A6)", 2, 5, "=SUM(#REF!)"),
        ("=SUM(A2:A6)", 7, 5, "=SUM(A2:A6)"),
        ("=SUM(A2:A2)", 2, 1, "=SUM(#REF!)"),
        ("=SUM($A$2:A$6)", 3, 1, "=SUM($A$2:A$5)"),
        ("=A2+A3+A4", 3, 1, "=A2+#REF!+A3"),
    ],
)
def test_delete_rows_rewrites(formula, at, count, expected):
    s = Sheet()
    s.set("Z20", formula)
    s.delete_rows(at, count)
    assert s.get_raw(f"Z{20 - count}") == expected


def test_delete_rows_moves_cells_up_and_drops_deleted():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "doomed")
    s.set("A3", "3")
    s.set("B2", "=A3")
    s.delete_rows(2)
    assert s.get("A1") == 1.0
    assert s.get("A2") == 3.0
    assert s.get("A3") is None
    assert s.get_raw("B2") == ""


def test_reference_to_deleted_cell_evaluates_to_ref_and_propagates():
    s = Sheet()
    s.set("A2", "5")
    s.set("B1", "=A2*2")
    s.set("C1", "=B1+1")
    s.delete_rows(2)
    assert s.get_raw("B1") == "=#REF!*2"
    assert s.get("B1") == REF
    assert s.get("C1") == REF


def test_delete_rows_shrinks_range_and_recalculates():
    s = Sheet()
    for r in range(1, 6):
        s.set(f"A{r}", str(r))
    s.set("B1", "=SUM(A1:A5)")
    s.delete_rows(2, 2)
    assert s.get_raw("B1") == "=SUM(A1:A3)"
    assert s.get("B1") == 1.0 + 4.0 + 5.0


def test_delete_rows_breaks_cycle():
    s = Sheet()
    s.set("A1", "=A2")
    s.set("A2", "=A1")
    s.delete_rows(2)
    assert s.get_raw("A1") == "=#REF!"
    assert s.get("A1") == REF


def test_parse_error_formula_moves_but_text_is_untouched():
    s = Sheet()
    s.set("A5", "=A6+")
    s.delete_rows(1)
    assert s.get_raw("A4") == "=A6+"
    assert s.get("A4") == PARSE


# -- columns -------------------------------------------------------------------


@pytest.mark.parametrize(
    "op, at, count, formula, expected",
    [
        ("insert_cols", 2, 1, "=B1+$B$1+A1", "=C1+$C$1+A1"),
        ("insert_cols", 3, 2, "=SUM(B1:D1)", "=SUM(B1:F1)"),
        ("insert_cols", 2, 1, "=SUM(B1:D1)", "=SUM(C1:E1)"),
        ("insert_cols", 5, 1, "=SUM(B1:D1)", "=SUM(B1:D1)"),
        ("delete_cols", 2, 1, "=B1+C1", "=#REF!+B1"),
        ("delete_cols", 3, 1, "=SUM(B1:D1)", "=SUM(B1:C1)"),
        ("delete_cols", 2, 3, "=SUM(B1:D1)", "=SUM(#REF!)"),
        ("delete_cols", 26, 1, "=AA1", "=Z1"),
    ],
)
def test_column_edits_rewrite(op, at, count, formula, expected):
    s = Sheet()
    s.set("A100", formula)
    getattr(s, op)(at, count)
    assert s.get_raw("A100") == expected


def test_insert_cols_moves_cells():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "2")
    s.set("C1", "=A1+B1")
    s.insert_cols(2)
    assert s.get("B1") is None
    assert s.get("C1") == 2.0
    assert s.get_raw("D1") == "=A1+C1"
    assert s.get("D1") == 3.0


def test_insert_cols_pushes_cells_off_grid():
    s = Sheet()
    s.set("XFD1", "edge")
    s.set("A1", "=XFD1")
    s.insert_cols(1)
    assert s.get("XFD1") is None
    assert s.get_raw("B1") == "=#REF!"


def test_delete_cols_moves_cells_left():
    s = Sheet()
    s.set("A1", "a")
    s.set("C1", "c")
    s.set("D1", "=C1")
    s.delete_cols(2)
    assert s.get("B1") == "c"
    assert s.get_raw("C1") == "=B1"
    assert s.get("C1") == "c"


def test_row_edits_leave_columns_alone_and_vice_versa():
    s = Sheet()
    s.set("A1", "=SUM(B2:D4)")
    s.insert_cols(10)
    s.insert_rows(10)
    assert s.get_raw("A1") == "=SUM(B2:D4)"


# -- validation ----------------------------------------------------------------


@pytest.mark.parametrize(
    "op, args",
    [
        ("insert_rows", (0,)),
        ("insert_rows", (1048577,)),
        ("insert_rows", (1, 0)),
        ("insert_rows", (1, -1)),
        ("delete_rows", (0,)),
        ("delete_rows", (1048576, 2)),
        ("delete_rows", (1, 0)),
        ("insert_cols", (16385,)),
        ("delete_cols", (16384, 2)),
        ("delete_cols", (0, 1)),
    ],
)
def test_invalid_structural_arguments_raise_value_error(op, args):
    with pytest.raises(ValueError):
        getattr(Sheet(), op)(*args)


@pytest.mark.parametrize(
    "op, args",
    [
        ("insert_rows", ("1",)),
        ("insert_rows", (True,)),
        ("delete_rows", (1.0,)),
        ("insert_cols", (1, 1.0)),
        ("delete_cols", (1, None)),
    ],
)
def test_non_int_structural_arguments_raise_type_error(op, args):
    with pytest.raises(TypeError):
        getattr(Sheet(), op)(*args)


def test_boundary_structural_edits_are_allowed():
    s = Sheet()
    s.set("A1048576", "x")
    s.set("XFD1", "y")
    s.delete_rows(1048576)
    s.delete_cols(16384)
    s.insert_rows(1048576, 5)
    s.insert_cols(16384)
    assert s.get("A1048576") is None
    assert s.get("XFD1") is None


# -- values after structural edits ------------------------------------------------

CYCLE = CellError("#CYCLE!")


def test_delete_breaks_cycle_through_range():
    s = Sheet()
    s.set("A1", "=SUM(A2:A3)")
    s.set("A2", "4")
    s.set("A3", "=A1")
    s.set("B1", "=A1*2")
    assert s.get("A1") == CYCLE
    s.delete_rows(3)
    assert s.get_raw("A1") == "=SUM(A2:A2)"
    assert s.get("A1") == 4.0
    assert s.get("B1") == 8.0


def test_untouched_cycle_survives_moving():
    s = Sheet()
    s.set("A5", "=A6")
    s.set("A6", "=A5")
    s.set("B1", "=A5")
    s.insert_rows(1)
    assert s.get_raw("A6") == "=A7"
    assert s.get("A6") == CYCLE
    assert s.get("A7") == CYCLE
    assert s.get_raw("B2") == "=A6"
    assert s.get("B2") == CYCLE
    s.set("A7", "1")
    assert s.get("A6") == 1.0
    assert s.get("B2") == 1.0


def test_insert_clamp_drops_values_from_range_sum():
    s = Sheet()
    s.set("A1048576", "5")
    s.set("A1048575", "7")
    s.set("B1", "=SUM(A1048575:A1048576)")
    s.set("C1", "=B1+1")
    assert s.get("B1") == 12.0
    s.insert_rows(1)
    assert s.get_raw("B2") == "=SUM(A1048576:A1048576)"
    assert s.get("B2") == 7.0
    assert s.get("C2") == 8.0


def test_values_unchanged_by_pure_shifts_stay_correct():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    s.set("A3", "=SUM(A1:A2)")
    s.set("B3", "=A3*10")
    s.insert_rows(2, 2)
    assert s.get_raw("A5") == "=SUM(A1:A4)"
    assert s.get("A5") == 3.0
    assert s.get("B5") == 30.0
    s.set("A2", "100")
    assert s.get("B5") == 1030.0
    s.delete_rows(1)
    assert s.get_raw("A4") == "=SUM(A1:A3)"
    assert s.get("B4") == 1020.0


def test_delete_cols_dependents_of_lossy_cells_update():
    s = Sheet()
    s.set("B1", "3")
    s.set("C1", "=B1")
    s.set("D1", "=C1+1")
    s.set("E1", "=CONCAT(C1:D1)")
    s.delete_cols(2)
    assert s.get_raw("B1") == "=#REF!"
    assert s.get("C1") == REF
    assert s.get("D1") == REF
