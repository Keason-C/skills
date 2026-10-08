import pytest

from gridcalc import CellError, Sheet


def sheet(**cells):
    s = Sheet()
    for addr, raw in cells.items():
        s.set(addr, raw)
    return s


def test_copy_shifts_relative_parts_only():
    s = sheet(A1="1", A2="2", B1="=A1+$A$1+A$2+$A2")
    changed = s.copy("B1", "C3")
    assert s.get_raw("C3") == "=B3+$A$1+B$2+$A4"
    assert changed == ["C3"]
    assert s.get("C3") == 1.0


def test_copy_block_with_literals_and_empty_cells():
    s = sheet(A1="x", B2="=A1&\"!\"", D5="old", E6="old")
    changed = s.copy("A1:B2", "D5")
    assert s.get("D5") == "x"
    assert s.get_raw("E5") == ""
    assert s.get_raw("D6") == ""
    assert s.get_raw("E6") == '=D5&"!"'
    assert s.get("E6") == "x!"
    assert changed == ["D5", "E6"]


def test_copy_reports_dependents_and_sorted():
    s = sheet(A1="1", C1="5", Z9="=SUM(C1:C2)")
    changed = s.copy("A1", "C2")
    assert changed == ["C2", "Z9"]
    assert s.get("Z9") == 6.0


def test_copy_reference_leaving_grid_becomes_ref():
    s = sheet(B2="=A1+SUM(A1:B2)+$C$9")
    s.copy("B2", "A1")
    assert s.get_raw("A1") == "=#REF!+SUM(#REF!)+$C$9"
    assert s.get("A1") == CellError("#REF!")


def test_copy_overlapping_reads_source_first():
    s = sheet(A1="1", A2="=A1+1", A3="=A2+1")
    s.copy("A1:A3", "A2")
    assert s.get_raw("A2") == "1"
    assert s.get_raw("A3") == "=A2+1"
    assert s.get_raw("A4") == "=A3+1"
    assert s.get("A4") == 3.0


def test_copy_preserves_text_outside_tokens_and_normalises_ranges():
    s = sheet(A1="= sum( a1:b2 ) & \"A1\"", B1="=SUM($B1:A$3)")
    s.copy("A1:B1", "C3")
    assert s.get_raw("C3") == "= sum( C3:D4 ) & \"A1\""
    # $B1:A$3 normalised to A1:$B$3; shifted 2 rows/2 cols -> C$3:$B3 -> normalised
    assert s.get_raw("D3") == "=SUM($B3:C$3)"


def test_copy_argument_forms():
    s = sheet(A1="7")
    s.copy("$a$1", "$c$1")
    assert s.get("C1") == 7.0
    s.copy("b2:a1", "d4")
    assert s.get("D4") == 7.0
    for src, dst in [("A1", "C1:D2"), ("A0", "B1"), ("A1", "XFE1"), ("A1:B2", "XFD1"), ("A1", "A1048577")]:
        with pytest.raises(ValueError):
            s.copy(src, dst)
    with pytest.raises(ValueError):
        s.copy("A1:A2", "B1048576")
    assert s.get_raw("B1048576") == ""


def test_copy_to_itself_is_noop():
    s = sheet(A1="1", B1="=A1*2")
    assert s.copy("A1:B1", "A1") == []
    assert s.get_raw("B1") == "=A1*2"


def test_copy_rewrites_refs_after_untokenisable_text():
    s = sheet(A1="=B1 + @ + C1")
    s.copy("A1", "A2")
    assert s.get_raw("A2") == "=B2 + @ + C2"
    assert s.get("A2") == CellError("#PARSE!")
