import pytest

from gridcalc import CellError, Sheet

REF = CellError("#REF!")
PARSE = CellError("#PARSE!")
CYCLE = CellError("#CYCLE!")


def copied(formula, src, dst):
    """Raw text of ``formula`` (stored at ``src``) after copying it to ``dst``."""
    s = Sheet()
    s.set(src, formula)
    s.copy(src, dst)
    return s.get_raw(dst)


@pytest.mark.parametrize(
    "formula, src, dst, expected",
    [
        ("=B1+$C$1+$D2+E$3", "A1", "A3", "=B3+$C$1+$D4+E$3"),
        ("=B1+$C$1+$D2+E$3", "A1", "C1", "=D1+$C$1+$D2+G$3"),
        ("=B1+$C$1+$D2+E$3", "A1", "C3", "=D3+$C$1+$D4+G$3"),
        ("=B5", "C5", "C2", "=B2"),
        ("=sum( b1 , 2 )", "A1", "A2", "=sum( B2 , 2 )"),
        ("=$b$1+b1", "A1", "A2", "=$b$1+B2"),
        ("=SUM(A1:B2)", "C3", "C4", "=SUM(A2:B3)"),
        ("=SUM(B2:A1)", "C3", "C4", "=SUM(A2:B3)"),
        ("=SUM(B2:A1)", "C3", "C3", "=SUM(B2:A1)"),
        ("=SUM($A$1:$B$2)", "C3", "D9", "=SUM($A$1:$B$2)"),
        ("=SUM(A$5:A10)", "B10", "B1", "=SUM(A1:A$5)"),
        ("=SUM($A$5:A10)", "B10", "B1", "=SUM($A1:A$5)"),
        ('=A1 & "A1"', "B1", "B2", '=A2 & "A1"'),
        ("=SUM(A1 : B2)", "C3", "C4", "=SUM(A2:B3)"),
    ],
)
def test_copy_shifts_relative_parts(formula, src, dst, expected):
    assert copied(formula, src, dst) == expected


@pytest.mark.parametrize(
    "formula, src, dst, expected",
    [
        ("=A1", "A2", "A1", "=#REF!"),
        ("=A1+1", "B1", "A1", "=#REF!+1"),
        ("=SUM(A1:A3)", "B2", "B1", "=SUM(#REF!)"),
        ("=SUM(A1:A$3)", "B2", "B1", "=SUM(#REF!)"),
        ("=SUM(A2:A$3)", "B2", "B1", "=SUM(A1:A$3)"),
        ("=XFD1", "A1", "B1", "=#REF!"),
        ("=$XFD1", "A1", "B1", "=$XFD1"),
    ],
)
def test_copy_off_grid_reference_becomes_ref(formula, src, dst, expected):
    s = Sheet()
    s.set(src, formula)
    s.copy(src, dst)
    assert s.get_raw(dst) == expected
    if "#REF!" in expected:
        assert s.get(dst) == REF


@pytest.mark.parametrize(
    "formula",
    ["=A1+", "=XFE1+1", "=#REF!+1", "=1/0"],
)
def test_copy_leaves_unshiftable_formulas_verbatim(formula):
    assert copied(formula, "A1", "C7") == formula


def test_copy_parse_error_formula_keeps_text_with_references():
    assert copied("=A1+(B2", "A1", "C3") == "=A1+(B2"


def test_copy_out_of_grid_token_kept_while_others_shift():
    assert copied("=XFE1+A1", "B1", "B2") == "=XFE1+A2"


@pytest.mark.parametrize("raw", [" 42 ", "'x", "text", "TRUE", "'=A1"])
def test_copy_literals_exactly(raw):
    assert copied(raw, "A1", "B2") == raw


def test_copy_block_and_values():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "=A1*10")
    s.set("A2", "2")
    s.set("B2", "=A2*10")
    changed = s.copy("A1:B2", "D5")
    assert changed == ["D5", "E5", "D6", "E6"]
    assert s.get_raw("E5") == "=D5*10"
    assert s.get("E6") == 20.0


def test_copy_reversed_source_range():
    s = Sheet()
    s.set("A1", "1")
    s.set("B2", "2")
    s.copy("B2:A1", "D1")
    assert s.get("D1") == 1.0
    assert s.get("E2") == 2.0


def test_copy_reports_dependents_and_skips_unchanged():
    s = Sheet()
    s.set("A1", "5")
    s.set("B1", "5")
    s.set("C1", "=B1*2")
    s.set("D1", "=A1")
    assert s.copy("A1", "B1") == []
    s.set("A1", "6")
    assert s.copy("A1", "B1") == ["B1", "C1"]
    assert s.get("C1") == 12.0


def test_empty_source_cells_clear_destination():
    s = Sheet()
    s.set("A1", "1")
    s.set("D1", "x")
    s.set("E1", "y")
    s.set("F1", "=E1")
    changed = s.copy("A1:B1", "D1")
    assert s.get("D1") == 1.0
    assert s.get("E1") is None
    assert s.get_raw("E1") == ""
    assert changed == ["D1", "E1", "F1"]


def test_overlapping_copy_reads_source_first():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "=A1+1")
    s.set("A3", "=A2+1")
    s.copy("A1:A2", "A2")
    assert s.get_raw("A2") == "1"
    assert s.get_raw("A3") == "=A2+1"
    assert s.get("A3") == 2.0


def test_overlapping_copy_downwards_chain():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "=A1*2")
    s.copy("A1:A2", "A2")
    assert s.get_raw("A2") == "1"
    assert s.get_raw("A3") == "=A2*2"
    assert s.get("A3") == 2.0


def test_copy_can_create_cycle():
    s = Sheet()
    s.set("A1", "=B1")
    s.copy("A1", "B1")
    assert s.get_raw("B1") == "=C1"
    s.copy("A1", "C1")
    assert s.get("A1") == 0.0
    s.set("D1", "=A1")
    assert s.get("A1") == CYCLE
    assert s.get("C1") == CYCLE


@pytest.mark.parametrize(
    "src, dst",
    [("A1:B2", "XFD1"), ("A1:A2", "A1048576"), ("A1", "XFE1"), ("A1:B2", "D5:E6")],
)
def test_destination_off_grid_raises_and_writes_nothing(src, dst):
    s = Sheet()
    s.set("A1", "1")
    s.set("XFD1", "keep")
    s.set("A1048576", "keep")
    with pytest.raises(ValueError):
        s.copy(src, dst)
    assert s.get("XFD1") == "keep"
    assert s.get("A1048576") == "keep"


@pytest.mark.parametrize("src", ["", "A0", "A1:", "$A$1", "A1:B2:C3", "a1 "])
def test_malformed_source_raises(src):
    with pytest.raises(ValueError):
        Sheet().copy(src, "B1")


def test_copy_whole_column_sparse():
    s = Sheet()
    s.set("A1", "1")
    s.set("A1000000", "=A999999+1")
    s.copy("A1:A1048576", "B1")
    assert s.get("B1") == 1.0
    assert s.get_raw("B1000000") == "=B999999+1"
