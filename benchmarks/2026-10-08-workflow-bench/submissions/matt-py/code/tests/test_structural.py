import pytest

from gridcalc import CellError, Sheet

REF = CellError("#REF!")


def sheet(**cells):
    s = Sheet()
    for addr, raw in cells.items():
        s.set(addr, raw)
    return s


def test_insert_rows_moves_cells_and_rewrites_refs():
    s = sheet(A1="1", A2="2", A3="=A1+A2", B1="=$A$2*10")
    s.insert_rows(2)
    assert s.get_raw("A2") == ""
    assert s.get("A3") == 2.0
    assert s.get_raw("A4") == "=A1+A3"
    assert s.get("A4") == 3.0
    assert s.get_raw("B1") == "=$A$3*10"  # $ does not prevent shifting
    assert s.get("B1") == 20.0


def test_unchanged_tokens_kept_byte_for_byte():
    s = sheet(A1="1", A5="=a1 +  a9")
    s.insert_rows(3, 2)
    assert s.get_raw("A7") == "=a1 +  A11"


def test_delete_rows_single_ref_becomes_ref_error():
    s = sheet(A1="1", A2="2", A3="=A2*2", A4="=A1+1")
    s.delete_rows(2)
    assert s.get_raw("A2") == "=#REF!*2"
    assert s.get("A2") == REF
    assert s.get_raw("A3") == "=A1+1"
    assert s.get("A3") == 2.0


@pytest.mark.parametrize(
    "op,args,expected",
    [
        ("delete_rows", (3, 2), "=SUM(A2:A4)"),  # shrink from inside
        ("delete_rows", (1, 2), "=SUM(A1:A4)"),  # first endpoint deleted
        ("delete_rows", (5, 3), "=SUM(A2:A4)"),  # last endpoint deleted
        ("delete_rows", (2, 5), "=SUM(#REF!)"),  # whole range deleted
        ("delete_rows", (9, 1), "=SUM(A2:A6)"),  # below: unchanged
        ("insert_rows", (3, 2), "=SUM(A2:A8)"),  # strictly inside grows
        ("insert_rows", (6, 1), "=SUM(A2:A7)"),  # at last row grows
        ("insert_rows", (2, 1), "=SUM(A3:A7)"),  # at first row shifts
        ("insert_rows", (7, 1), "=SUM(A2:A6)"),  # directly below: unchanged
    ],
)
def test_range_rewriting_rows(op, args, expected):
    s = sheet(C10="=SUM(A2:A6)")
    getattr(s, op)(*args)
    found = [a for a in ("C7", "C8", "C9", "C10", "C11", "C12", "C5", "C4", "C3") if s.get_raw(a)]
    assert len(found) == 1
    assert s.get_raw(found[0]) == expected


def test_range_rewriting_columns_and_dollars():
    s = sheet(A10="=SUM($B$1:D$2)", B1="1", D2="2")
    s.insert_cols(3)
    assert s.get_raw("A10") == "=SUM($B$1:E$2)"
    assert s.get("A10") == 3.0
    s.delete_cols(2)
    assert s.get_raw("A10") == "=SUM($B$1:D$2)"
    assert s.get("A10") == 2.0
    s.delete_cols(2, 3)
    assert s.get_raw("A10") == "=SUM(#REF!)"
    assert s.get("A10") == REF


def test_reversed_range_normalised_only_when_rewritten():
    s = sheet(Z1="=SUM(b3:A1)", Z2="=SUM(D9:C8)")
    s.insert_rows(2)
    assert s.get_raw("Z1") == "=SUM(A1:B4)"
    assert s.get_raw("Z3") == "=SUM(C9:D10)"
    s2 = sheet(Z1="=SUM($B1:A$3)")
    s2.insert_rows(2)
    assert s2.get_raw("Z1") == "=SUM(A1:$B$4)"


def test_range_whitespace_preserved_on_rewrite():
    s = sheet(Z1="=SUM(A1 : A3)")
    s.insert_rows(2)
    assert s.get_raw("Z1") == "=SUM(A1 : A4)"


def test_dropped_off_grid():
    s = sheet(A1048576="5", A1="=A1048576", B1="=SUM(A1048570:A1048576)")
    s.insert_rows(10, 10)
    assert s.get("A1048576") is None
    assert s.get_raw("A1") == "=#REF!"
    assert s.get("A1") == REF
    # the whole range would start beyond the grid
    assert s.get_raw("B1") == "=SUM(#REF!)"
    assert s.get("B1") == REF


def test_shifted_range_end_clamped():
    s = sheet(B1="=SUM(A100:A1048500)")
    s.insert_rows(1, 100)
    assert s.get_raw("B101") == "=SUM(A200:A1048576)"


def test_range_end_clamped_drops_cells_and_recalculates():
    s = sheet(A1048576="5", B1="=SUM(A10:A1048576)")
    assert s.get("B1") == 5.0
    s.insert_rows(20, 3)
    assert s.get_raw("B1") == "=SUM(A10:A1048576)"
    assert s.get("B1") == 0.0


def test_structural_edit_restores_or_breaks_cycles():
    s = sheet(A1="=A2", A2="=A1", B1="=A1")
    s.delete_rows(2)
    assert s.get_raw("A1") == "=#REF!"
    assert s.get("A1") == REF
    assert s.get("B1") == REF


def test_parse_error_formula_refs_still_rewritten():
    s = sheet(A5="=A1+")
    s.insert_rows(1)
    assert s.get_raw("A6") == "=A2+"
    assert s.get("A6") == CellError("#PARSE!")


def test_strings_and_out_of_grid_refs_untouched():
    s = sheet(B2='="A1"&A1&XFE1')
    s.insert_rows(1)
    assert s.get_raw("B3") == '="A1"&A2&XFE1'


@pytest.mark.parametrize(
    "op,at,count",
    [("insert_rows", 0, 1), ("delete_rows", 1048577, 1), ("insert_cols", 16385, 1), ("delete_cols", 1, 0)],
)
def test_invalid_arguments(op, at, count):
    s = sheet(A1="1")
    with pytest.raises(ValueError):
        getattr(s, op)(at, count)
    assert s.get("A1") == 1.0


def test_insert_returns_none_and_values_recalculated():
    s = sheet(A1="1", A2="=A1", A3="=COUNT(A1:A2)")
    assert s.insert_rows(2) is None
    assert s.get("A4") == 2.0
    assert s.delete_rows(2) is None
    s.set("A1", "9")
    assert s.get("A2") == 9.0


def test_refs_after_untokenisable_text_still_rewritten():
    s = sheet(A1="=B1 + ; + C1")
    s.delete_cols(2)
    assert s.get_raw("A1") == "=#REF! + ; + B1"
