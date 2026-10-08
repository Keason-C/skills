import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from gridcalc import CellError, Sheet  # noqa: E402


def E(code):
    return CellError(code)


def val(formula, **cells):
    s = Sheet()
    for k, v in cells.items():
        s.set(k, v)
    s.set("ZZ1", formula)
    return s.get("ZZ1")


def same(a, b):
    return type(a) is type(b) and a == b


# ------------------------------------------------------------------ addresses
@pytest.mark.parametrize("bad", ["", "A", "1", "A0", "1A", "XFE1", "A1048577", "AAAA1",
                                 "A-1", " A1", "A1 ", "$A$1", "A1:B2", "Ä1", None, 5])
def test_bad_addresses(bad):
    s = Sheet()
    with pytest.raises(ValueError):
        s.get(bad)
    with pytest.raises(ValueError):
        s.set(bad, "1")
    with pytest.raises(ValueError):
        s.get_raw(bad)


def test_addresses_case_insensitive_and_edges():
    s = Sheet()
    assert s.set("b3", "1") == ["B3"]
    assert s.get("B3") == 1.0
    assert s.set("XFD1048576", "x") == ["XFD1048576"]
    assert s.get("xfd1048576") == "x"
    assert s.get("A1") is None and s.get_raw("A1") == ""


# ------------------------------------------------------------------ literals
@pytest.mark.parametrize("raw,expected", [
    ("42", 42.0), ("-2.5E-2", -0.025), ("1e3", 1000.0), (".5", 0.5), ("+.5e1", 5.0),
    ("  7  ", 7.0), ("1.", 1.0), ("'123", "123"), ("'", ""), ("TRUE", True), ("false", False),
    ("tRuE", True), (" TRUE", " TRUE"), ("  hi ", "  hi "), ("1e", "1e"), ("1_000", "1_000"),
    ("inf", "inf"), ("nan", "nan"), ("1e400", "1e400"), ("0x10", "0x10"), ("--1", "--1"),
])
def test_literals(raw, expected):
    s = Sheet()
    s.set("A1", raw)
    assert same(s.get("A1"), expected)
    assert s.get_raw("A1") == raw


def test_number_is_float():
    s = Sheet()
    s.set("A1", "3")
    assert type(s.get("A1")) is float
    s.set("A2", "=LEN(\"abc\")+COUNT(A1)")
    assert type(s.get("A2")) is float and s.get("A2") == 4.0


# ------------------------------------------------------------------ operators
@pytest.mark.parametrize("f,expected", [
    ("=1+2*3", 7.0), ("=(1+2)*3", 9.0), ("=2^3^2", 64.0), ("=-2^2", 4.0), ("=2^-1", 0.5),
    ("=10-4-3", 3.0), ("=12/4/3", 1.0), ("=1+2&3", "33"), ("=1&2=12", False),
    ("=\"12\"=1&2", True), ("=1<2=TRUE", True), ("=--3", 3.0), ("=+-+3", -3.0),
    ("= 1 +  2 ", 3.0), ("=\"say \"\"hi\"\"\"", 'say "hi"'), ("=\"\"", ""),
    ("=0.1+0.2&\"\"", "0.3"), ("=1/3&\"\"", "0.333333333333333"), ("=1e20&\"\"", "1e+20"),
    ("=-0&\"\"", "0"), ("=1&\"\"", "1"), ("=TRUE&FALSE", "TRUEFALSE"),
    ("=\"a\">5", True), ("=TRUE>\"z\"", True), ("=\"abc\"=\"ABC\"", True), ("=\"a\"<\"B\"", True),
    ("=\"1\"=1", False), ("=1<>1", False), ("=2>=2", True), ("=2<=1", False),
    ("=\" 3 \"+1", 4.0), ("=\"\"+1", E("#VALUE!")), ("=\"x\"*1", E("#VALUE!")),
    ("=TRUE+TRUE", 2.0), ("=1/0", E("#DIV/0!")), ("=0^-1", E("#DIV/0!")), ("=0^0", 1.0),
    ("=10^400", E("#VALUE!")), ("=(-8)^(1/3)", E("#VALUE!")), ("=(-8)^3", -512.0),
    ("=1e308*10", E("#VALUE!")), ("=1e400", E("#VALUE!")), ("=1/0+\"x\"*1", E("#DIV/0!")),
    ("=\"x\"*1+1/0", E("#VALUE!")), ("=#REF!", E("#REF!")), ("=#n/a", E("#PARSE!")),
    ("=1+", E("#PARSE!")), ("=", E("#PARSE!")), ("=(1", E("#PARSE!")), ("=1)", E("#PARSE!")),
    ("=\"abc", E("#PARSE!")), ("=foo", E("#PARSE!")), ("=1 2", E("#PARSE!")),
    ("=A1:B2", E("#VALUE!")), ("=A1:A3+1", E("#VALUE!")), ("=-A1:A2", E("#VALUE!")),
    ("=XFE1", E("#REF!")), ("=A1048577+1", E("#REF!")), ("=1,2", E("#PARSE!")),
    ("=SUM(1,)", E("#PARSE!")), ("=*1", E("#PARSE!")), ("=1:2", E("#PARSE!")),
])
def test_operators(f, expected):
    assert same(val(f), expected)


def test_empty_semantics():
    s = Sheet()
    s.set("B1", "=A1")
    assert same(s.get("B1"), 0.0)
    s.set("B2", "=A1&\"\"")
    assert same(s.get("B2"), "")
    s.set("B3", "=A1=0")
    assert s.get("B3") is True
    s.set("B4", "=A1=\"\"")
    assert s.get("B4") is True
    s.set("B5", "=A1=FALSE")
    assert s.get("B5") is True
    s.set("B6", "=A1=A2")
    assert s.get("B6") is True
    s.set("B7", "=A1+1")
    assert s.get("B7") == 1.0
    s.set("B8", "=IF(TRUE,A1)")
    assert same(s.get("B8"), 0.0)


def test_deep_parens():
    for depth in (200, 1000, 5000):
        assert val("=" + "(" * depth + "1+2" + ")" * depth) == 3.0
    assert val("=" + "-(" * 3001 + "1" + ")" * 3001) == -1.0
    assert val("=" + "SUM(" * 500 + "1" + ")" * 500) == 1.0
    assert val("=1" + "+1" * 20000) == 20001.0


# ------------------------------------------------------------------ functions
@pytest.mark.parametrize("f,expected", [
    ("=SUM(A1:A5)", 6.0), ("=SUM(A1:A5,10)", 16.0), ("=SUM(1,\"2\",TRUE)", 4.0),
    ("=SUM(\"x\")", E("#VALUE!")), ("=AVERAGE(A1:A5)", 2.0), ("=AVERAGE(A4:A5)", E("#DIV/0!")),
    ("=MIN(A4:A5)", 0.0), ("=MAX(A4:A5)", 0.0), ("=MIN(A1:A5,-1)", -1.0), ("=MAX(A1:A5)", 3.0),
    ("=COUNT(A1:A6)", 3.0), ("=COUNT(1,\"2\",\"x\",TRUE)", 3.0), ("=COUNT(A1:A7)", E("#DIV/0!")),
    ("=SUM(A1:A7)", E("#DIV/0!")), ("=SUM()", E("#VALUE!")), ("=sum(a1:a3)", 6.0),
    ("=SUM(A3:A1)", 6.0), ("=SUM((A1:A3))", 6.0), ("=SUM(IF(TRUE,A1:A3,0))", 6.0),
    ("=IF(TRUE,1)", 1.0), ("=IF(FALSE,1)", False), ("=IF(FALSE,1/0,2)", 2.0),
    ("=IF(TRUE,2,1/0)", 2.0), ("=IF(1/0,1,2)", E("#DIV/0!")), ("=IF(\"true\",1,2)", 1.0),
    ("=IF(\"yes\",1,2)", E("#VALUE!")), ("=IF(A6,1,2)", 2.0), ("=IF(0,1,2)", 2.0),
    ("=IF(TRUE)", E("#VALUE!")), ("=IF(1,2,3,4)", E("#VALUE!")), ("=IF(A1:A2,1,2)", E("#VALUE!")),
    ("=IFERROR(1/0,\"x\")", "x"), ("=IFERROR(5,1/0)", 5.0), ("=IFERROR(1/0)", E("#VALUE!")),
    ("=AND(TRUE,1)", True), ("=AND(TRUE,0)", False), ("=OR(FALSE,0)", False), ("=OR(0,2)", True),
    ("=AND(A4:A4)", E("#VALUE!")), ("=AND(A4:A5)", True), ("=AND(A1:A5)", True), ("=OR(A6:A6)", E("#VALUE!")), ("=OR(A4:A6)", True),
    ("=AND(A4:A5,TRUE)", True), ("=AND(FALSE,1/0)", E("#DIV/0!")), ("=AND(\"x\")", E("#VALUE!")),
    ("=AND(A6)", False), ("=NOT(0)", True), ("=NOT(\"FALSE\")", True), ("=NOT(1,2)", E("#VALUE!")),
    ("=NOT(A1:A2)", E("#VALUE!")),
    ("=ROUND(2.5,0)", 3.0), ("=ROUND(-2.5,0)", -3.0), ("=ROUND(0.125,2)", 0.13),
    ("=ROUND(1250,-2)", 1300.0), ("=ROUND(1.005,2)", 1.01), ("=ROUND(2.567,1.9)", 2.6),
    ("=ROUND(2.567,-0.9)", 3.0), ("=ROUND(1)", E("#VALUE!")), ("=ROUND(\"x\",1/0)", E("#VALUE!")),
    ("=ROUND(1.5,400)", 1.5), ("=ROUND(5,-1000)", 0.0),
    ("=ABS(-3)", 3.0), ("=ABS(\"-2\")", 2.0), ("=LEN(\"hello\")", 5.0), ("=LEN(1/4)", 4.0),
    ("=LEN(A6)", 0.0), ("=LEN(TRUE)", 4.0), ("=LEN(A1:A2)", E("#VALUE!")),
    ("=CONCAT(\"a\",1,TRUE)", "a1TRUE"), ("=CONCAT(B1:C2)", "xy1TRUE"),
    ("=CONCAT(A6,\"z\")", "z"), ("=CONCAT(A7:A7)", E("#DIV/0!")),
    ("=FOO(1)", E("#NAME?")), ("=FOO(1/0)", E("#NAME?")), ("=1/0+FOO(1)", E("#DIV/0!")),
    ("=FOO()", E("#NAME?")), ("=NOT()", E("#VALUE!")), ("=SUM (1,2)", 3.0),
    ("=SUM(1,2)*2", 6.0), ("=MAX(A1:A3)-MIN(A1:A3)", 2.0), ("=Concat(\"a\" , \"b\")", "ab"),
])
def test_functions(f, expected):
    cells = dict(A1="1", A2="2", A3="3", A4="text", A5="TRUE", A7="=1/0",
                 B1="x", C1="y", B2="1", C2="TRUE")
    assert same(val(f, **cells), expected)


# ------------------------------------------------------------------ set / changed
def test_changed_list():
    s = Sheet()
    assert s.set("A1", "1") == ["A1"]
    assert s.set("A1", "1") == []
    assert s.set("A1", "1.0") == []          # value equal
    assert s.set("B2", "=A1*2") == ["B2"]
    assert s.set("C1", "=A1+B2") == ["C1"]
    assert s.set("A1", "2") == ["A1", "C1", "B2"]
    assert s.get("C1") == 6.0
    assert s.set("B2", "=A1+A1") == []      # raw changed, value equal


def test_changed_sorted_row_then_col():
    s = Sheet()
    s.set("A1", "1")
    for a in ("B1", "A2", "C3", "AA1", "B10"):
        s.set(a, "=A1")
    assert s.set("A1", "2") == ["A1", "B1", "AA1", "A2", "C3", "B10"]
    assert s.set("A1", "") == ["A1", "B1", "AA1", "A2", "C3", "B10"]
    assert s.set("A1", "") == []
    assert s.set("Z9", "") == []


def test_type_sensitive_change():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "=A1")
    assert s.set("A1", "TRUE") == ["A1", "B1"]  # 1.0 -> True
    s.set("C1", "=1/0")
    assert s.set("C1", "=2/0") == []
    assert s.set("C1", "=#DIV/0!") == []
    assert s.set("C1", "=\"x\"*1") == ["C1"]


def test_formula_raw_preserved():
    s = Sheet()
    s.set("A1", "=sum( a1:b2 ) + 1")
    assert s.get_raw("A1") == "=sum( a1:b2 ) + 1"


# ------------------------------------------------------------------ cycles
def test_cycles():
    s = Sheet()
    s.set("A1", "=A1")
    assert s.get("A1") == E("#CYCLE!")
    s.set("B1", "=C1+1")
    s.set("C1", "=B1+1")
    s.set("D1", "=B1*2")
    s.set("E1", "=IFERROR(D1, 7)")
    assert s.get("B1") == E("#CYCLE!") and s.get("C1") == E("#CYCLE!")
    assert s.get("D1") == E("#CYCLE!") and s.get("E1") == 7.0
    assert s.set("C1", "5") == ["B1", "C1", "D1", "E1"]
    assert s.get("B1") == 6.0 and s.get("D1") == 12.0 and s.get("E1") == 12.0
    # IF branch not taken still counts as dependency
    s.set("F1", "=IF(TRUE,1,F2)")
    s.set("F2", "=F1")
    assert s.get("F1") == E("#CYCLE!")
    # range self-reference
    s.set("G3", "=SUM(G1:G5)")
    assert s.get("G3") == E("#CYCLE!")
    s.set("G3", "=SUM(G1:G2)")
    assert s.get("G3") == 0.0
    # unknown function still has deps
    s.set("H1", "=FOO(H1)")
    assert s.get("H1") == E("#CYCLE!")


def test_cycle_break_restores_everything():
    s = Sheet()
    s.set("A1", "=A3+1")
    s.set("A2", "=A1+1")
    s.set("A3", "=A2+1")
    s.set("B1", "=SUM(A1:A3)")
    assert all(s.get(a) == E("#CYCLE!") for a in ("A1", "A2", "A3", "B1"))
    s.set("A2", "10")
    assert (s.get("A1"), s.get("A2"), s.get("A3"), s.get("B1")) == (12.0, 10.0, 11.0, 33.0)
    s.set("A2", "=A1+1")
    assert s.get("B1") == E("#CYCLE!")


def test_large_cycle_and_chain_no_recursion():
    s = Sheet()
    n = 50000
    s.set("A1", "1")
    for i in range(2, n + 1):
        s.set(f"A{i}", f"=A{i-1}+1")
    assert s.get(f"A{n}") == float(n)
    ch = s.set("A1", "2")
    assert len(ch) == n and s.get(f"A{n}") == float(n + 1)
    s.set("A1", f"=A{n}")
    assert s.get("A1") == E("#CYCLE!") and s.get(f"A{n}") == E("#CYCLE!")
    s.set("A1", "0")
    assert s.get(f"A{n}") == float(n - 1)


# ------------------------------------------------------------------ structural edits
def test_insert_delete_rows_basic():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    s.set("A3", "3")
    s.set("B1", "=SUM(A1:A3)+$A$2+a3")
    s.insert_rows(2)
    assert s.get_raw("A3") == "2" and s.get_raw("A2") == ""
    assert s.get_raw("B1") == "=SUM(A1:A4)+$A$3+A4"
    s.set("A2", "10")
    assert s.get("B1") == 1 + 10 + 2 + 3 + 2 + 3.0
    s.delete_rows(3)
    assert s.get_raw("B1") == "=SUM(A1:A3)+#REF!+A3"
    assert s.get("B1") == E("#REF!")


def test_insert_range_rules():
    s = Sheet()
    s.set("Z1", "=SUM(A2:A4)")
    s.insert_rows(5)          # directly below last row -> unchanged
    assert s.get_raw("Z1") == "=SUM(A2:A4)"
    s.insert_rows(4)          # at last row -> grows
    assert s.get_raw("Z1") == "=SUM(A2:A5)"
    s.insert_rows(3, 2)       # strictly inside -> grows
    assert s.get_raw("Z1") == "=SUM(A2:A7)"
    s.insert_rows(2)          # at first row -> shift
    assert s.get_raw("Z1") == "=SUM(A3:A8)"


def test_delete_range_rules():
    s = Sheet()
    s.set("Z1", "=SUM(A3:A8)+SUM(B3:B8)+SUM(C3:C8)+SUM(D3:D8)+SUM(E10:E12)")
    s.delete_rows(5, 2)       # inside -> shrink
    assert s.get_raw("Z1") == "=SUM(A3:A6)+SUM(B3:B6)+SUM(C3:C6)+SUM(D3:D6)+SUM(E8:E10)"
    s.delete_rows(2, 2)       # includes first endpoint
    assert s.get_raw("Z1") == "=SUM(A2:A4)+SUM(B2:B4)+SUM(C2:C4)+SUM(D2:D4)+SUM(E6:E8)"
    s.delete_rows(4, 3)       # includes last endpoint
    assert s.get_raw("Z1") == "=SUM(A2:A3)+SUM(B2:B3)+SUM(C2:C3)+SUM(D2:D3)+SUM(E4:E5)"
    s.delete_rows(2, 2)       # entire range
    assert s.get_raw("Z1") == "=SUM(#REF!)+SUM(#REF!)+SUM(#REF!)+SUM(#REF!)+SUM(E2:E3)"
    assert s.get("Z1") == E("#REF!")


def test_reversed_range_rewrite():
    s = Sheet()
    s.set("Z1", "=SUM(A8:A3)")
    s.delete_rows(5, 2)
    assert s.get_raw("Z1") == "=SUM(A6:A3)"
    s.insert_rows(4)
    assert s.get_raw("Z1") == "=SUM(A7:A3)"


def test_columns_and_dollars():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "2")
    s.set("C1", "3")
    s.set("A2", "=$A$1+B$1+$C1+SUM($A1:C$1)")
    s.insert_cols(2)
    assert s.get_raw("A2") == "=$A$1+C$1+$D1+SUM($A1:D$1)"
    assert s.get("A2") == 1 + 2 + 3 + 6.0
    s.delete_cols(1)
    assert s.get_raw("A1") == "" and s.get("A1") is None
    assert s.get_raw("XFD2") == ""
    s2 = Sheet()
    s2.set("D5", "=$A$1+b$1")
    s2.delete_cols(1)
    assert s2.get_raw("C5") == "=#REF!+A$1"


def test_structural_preserves_other_text_and_case():
    s = Sheet()
    s.set("C3", '=sum( a1 : a2 )&"A1 B2"&  a5 &Sum(b1)')
    s.insert_rows(1)
    assert s.get_raw("C4") == '=sum( A2 : A3 )&"A1 B2"&  A6 &Sum(B2)'
    s.insert_cols(1)
    assert s.get_raw("D4") == '=sum( B2 : B3 )&"A1 B2"&  B6 &Sum(C2)'


def test_structural_grid_edges():
    s = Sheet()
    s.set("A1048576", "x")
    s.set("A1048575", "y")
    s.set("B1", "=A1048576")
    s.set("B2", "=A1048575")
    s.set("B3", "=COUNT(A1048570:A1048576)")
    s.insert_rows(10)
    assert s.get("A1048576") == "y"
    assert s.get_raw("B1") == "=#REF!" and s.get("B1") == E("#REF!")
    assert s.get_raw("B2") == "=A1048576" and s.get("B2") == "y"
    assert s.get_raw("B3") == "=COUNT(#REF!)"
    s.set("XFD1", "z")
    s.insert_cols(1)
    assert s.get("XFD1") is None


def test_structural_recalc_values():
    s = Sheet()
    for i in range(1, 6):
        s.set(f"A{i}", str(i))
    s.set("B1", "=SUM(A1:A5)")
    s.set("B2", "=B1*2")
    s.delete_rows(2, 2)
    assert s.get("A1") == 1.0 and s.get("A2") == 4.0
    assert s.get_raw("B1") == "=SUM(A1:A3)" and s.get("B1") == 10.0
    assert s.get("B2") is None
    s.set("C1", "=B1*2")
    s.insert_rows(1)
    assert s.get("C2") == 20.0 and s.get_raw("C2") == "=B2*2"


def test_structural_cycle_break():
    s = Sheet()
    s.set("A1", "=A2")
    s.set("A2", "=A1")
    s.set("A3", "=A1+1")
    s.delete_rows(2)
    assert s.get_raw("A1") == "=#REF!" and s.get("A1") == E("#REF!")
    assert s.get("A2") == E("#REF!")


def test_structural_arg_validation():
    s = Sheet()
    for bad in (0, -1, 1048577):
        with pytest.raises(ValueError):
            s.insert_rows(bad)
        with pytest.raises(ValueError):
            s.delete_rows(bad)
    with pytest.raises(ValueError):
        s.insert_cols(16385)
    assert s.insert_rows(1) is None and s.delete_cols(1, 3) is None


# ------------------------------------------------------------------ copy
def test_copy_basic():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    s.set("B1", "=A1+$A$1+A$1+$A1")
    s.set("B2", "=sum(A1:a2)")
    ch = s.copy("A1:B2", "D5")
    assert s.get_raw("E5") == "=D5+$A$1+D$1+$A5"
    assert s.get_raw("E6") == "=sum(D5:D6)"
    assert s.get("E6") == 3.0
    assert ch == ["D5", "E5", "D6", "E6"]


def test_copy_untouched_tokens_and_ref():
    s = Sheet()
    s.set("B2", "=a1+$a$1+A3")
    s.copy("B2", "B3")
    assert s.get_raw("B3") == "=A2+$a$1+A4"
    s.copy("B2", "A1")
    assert s.get_raw("A1") == "=#REF!+$a$1+#REF!" and s.get("A1") == E("#CYCLE!")
    s.set("B2", "=a1+$b$1+A3")
    s.copy("B2", "A1")
    assert s.get_raw("A1") == "=#REF!+$b$1+#REF!" and s.get("A1") == E("#REF!")
    s.set("C5", "=SUM(A1:B2)+1")
    s.copy("C5", "B4")
    assert s.get_raw("B4") == "=SUM(#REF!)+1"


def test_copy_overlap_and_clear():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "=A1+1")
    s.set("A3", "=A2+1")
    s.copy("A1:A3", "A2")
    assert [s.get_raw(f"A{i}") for i in range(1, 5)] == ["1", "1", "=A2+1", "=A3+1"]
    assert s.get("A4") == 3.0
    s.set("C1", "x")
    s.copy("D1", "C1")   # empty source clears
    assert s.get_raw("C1") == "" and s.get("C1") is None


def test_copy_out_of_grid_dest():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    with pytest.raises(ValueError):
        s.copy("A1:A2", "B1048576")
    with pytest.raises(ValueError):
        s.copy("A1:B1", "XFD1")
    with pytest.raises(ValueError):
        s.copy("A1", "XFE1")
    assert s.get_raw("B1048576") == ""
    assert s.copy("B1:A2", "A1") == []
    assert s.copy("a1", "xfd1048576") == ["XFD1048576"]


def test_copy_returns_dependents():
    s = Sheet()
    s.set("A1", "5")
    s.set("C1", "=B1*2")
    assert s.copy("A1", "B1") == ["B1", "C1"]


# ------------------------------------------------------------------ performance
def test_perf_unrelated_edits():
    s = Sheet()
    t0 = time.perf_counter()
    for i in range(1, 25001):
        s.set(f"A{i}", str(i))
        s.set(f"B{i}", f"=A{i}*2")
    s.set("C1", "=SUM(A1:A25000)")
    s.set("C2", "=SUM(B1:B1000)")
    build = time.perf_counter() - t0
    t0 = time.perf_counter()
    for i in range(1, 5001):
        assert s.set(f"D{i}", str(i)) == [f"D{i}"]
        s.set(f"E{i % 50 + 1}", f"=D{i}+1")
    edits = time.perf_counter() - t0
    assert s.get("C1") == 25000 * 25001 / 2
    assert build < 6 and edits < 3, (build, edits)


def test_perf_wide_range_dependency_lookup():
    s = Sheet()
    for i in range(1, 2001):
        s.set(f"B{i}", f"=SUM(A1:A{i})")
    t0 = time.perf_counter()
    for i in range(1, 2001):
        s.set(f"C{i}", str(i))
    assert time.perf_counter() - t0 < 1.0
    s.set("A1", "1")
    assert s.get("B2000") == 1.0


def test_perf_long_chain_structural():
    s = Sheet()
    n = 30000
    s.set("A1", "1")
    for i in range(2, n + 1):
        s.set(f"A{i}", f"=A{i-1}+1")
    t0 = time.perf_counter()
    s.insert_rows(1)
    s.delete_rows(1)
    s.insert_cols(1)
    assert time.perf_counter() - t0 < 5
    assert s.get(f"B{n}") == float(n)
    assert s.get_raw(f"B{n}") == f"=B{n-1}+1"


# ------------------------------------------------------------------ huge ranges
def test_huge_ranges_tracked():
    s = Sheet()
    s.set("XFD1", "=SUM(A1:A1048576)")
    s.set("XFD2", "=COUNT(A1:XFC1048576)")
    s.set("XFD3", "=CONCAT(C1:D1048576)")
    s.set("XFD4", "=SUM(A1:Z1048576)")
    s.set("XFD5", "=SUM(XFD1:XFD4)")
    assert s.set("A1048576", "5") == ["XFD1", "XFD2", "XFD4", "XFD5", "A1048576"]
    assert s.get("XFD1") == 5.0 and s.get("XFD2") == 1.0 and s.get("XFD5") == 11.0
    s.set("D2", "x")
    s.set("C2", "w")
    s.set("C9", "z")
    s.set("D1", "y")
    assert s.get("XFD3") == "ywxz"
    assert s.set("XFC9", "1") == ["XFD2", "XFD5", "XFC9"]
    s.set("B1", "=SUM(A1:Z1048576)")
    assert s.get("B1") == CellError("#CYCLE!")


# ------------------------------------------------------------------ fuzz vs. full rebuild
import random  # noqa: E402

_COLS = "ABCDE"


def _rand_ref(rng):
    return rng.choice(["", "$"]) + rng.choice(_COLS) + rng.choice(["", "$"]) + str(rng.randint(1, 6))


def _rand_raw(rng):
    k = rng.random()
    if k < 0.25:
        return str(rng.randint(-3, 9))
    if k < 0.3:
        return rng.choice(["", "abc", "TRUE", "'7", " 4 "])
    a, b = _rand_ref(rng), _rand_ref(rng)
    templates = [
        f"={a}+{b}", f"={a}*2-{b}", f"=SUM({a}:{b})", f"=IF({a}>2,{b},{a}&\"x\")",
        f"=IFERROR({a}/{b},-1)", f"=COUNT({a}:{b},{a})", f"=MAX({a}:{b})+MIN({b}:{a})",
        f"=CONCAT({a}:{b})", f"=AND({a}:{b})", f"=ROUND({a}/3,1)", f"={a}", f"=LEN({a})",
        f"=AVERAGE({a}:{b})", f"=-{a}^2", f"={a}={b}", f"=sum( {a} : {b} ) +  {a}",
    ]
    return rng.choice(templates).lower() if rng.random() < 0.2 else rng.choice(templates)


def _snapshot(s, rows=30, cols=14):
    out = {}
    for r in range(1, rows + 1):
        for c in range(1, cols + 1):
            a = "ABCDEFGHIJKLMN"[c - 1] + str(r)
            out[a] = (s.get_raw(a), s.get(a))
    return out


def _rebuild(sheet, rng):
    from gridcalc import _addr
    t = Sheet()
    items = [(_addr(k), c.raw) for k, c in sheet._cells.items()]
    rng.shuffle(items)
    for a, raw in items:
        t.set(a, raw)
    return t


def _key(a):
    col = a.rstrip("0123456789")
    return (int(a[len(col):]), col)


def _norm_code(code):
    from gridcalc import Rng
    return [tuple((x.r1, x.c1, x.r2, x.c2) if type(x) is Rng else x for x in ins) for ins in code]


def _check_compiled_state(s):
    """Remapped cells after structural edits must equal freshly parsed ones."""
    from gridcalc import _make_cell
    for k, cell in s._cells.items():
        f = _make_cell(cell.raw)
        assert cell.items == f.items, cell.raw
        assert set(cell.singles) == set(f.singles), cell.raw
        assert set(cell.ranges) == set(f.ranges), cell.raw
        assert cell.lit == f.lit or (cell.lit != cell.lit), cell.raw
        if cell.code is None:
            assert f.code is None
        else:
            assert _norm_code(cell.code) == _norm_code(f.code), cell.raw


@pytest.mark.parametrize("seed", range(25))
def test_fuzz_incremental_matches_rebuild(seed):
    rng = random.Random(seed)
    s = Sheet()
    for _ in range(120):
        before = _snapshot(s)
        op = rng.random()
        ret = None
        if op < 0.7:
            a = rng.choice(_COLS) + str(rng.randint(1, 6))
            ret = s.set(a, _rand_raw(rng))
        elif op < 0.8:
            c1, c2 = sorted(rng.sample(range(5), 2))
            r1, r2 = sorted(rng.sample(range(1, 7), 2))
            src = f"{_COLS[c1]}{r1}:{_COLS[c2]}{r2}"
            dst = rng.choice(_COLS) + str(rng.randint(1, 6))
            ret = s.copy(src, dst)
        else:
            fn = rng.choice([s.insert_rows, s.delete_rows, s.insert_cols, s.delete_cols])
            fn(rng.randint(1, 5), rng.randint(1, 2))
        after = _snapshot(s)
        if ret is not None:
            exp = sorted((a for a in after
                          if not (type(after[a][1]) is type(before[a][1])
                                  and after[a][1] == before[a][1])), key=_key)
            assert [a for a in ret if a in after] == exp
        _check_compiled_state(s)
        fresh = _snapshot(_rebuild(s, rng))
        for a in after:
            v1, v2 = after[a][1], fresh[a][1]
            assert type(v1) is type(v2) and v1 == v2, (a, after[a], fresh[a])


# ------------------------------------------------------------------ more structural / copy
def test_column_range_rules():
    s = Sheet()
    s.set("A10", "=SUM(B1:E1)+SUM(c2:$D2)")
    s.insert_cols(3)                  # strictly inside -> grows
    assert s.get_raw("A10") == "=SUM(B1:F1)+SUM(D2:$E2)"
    s.insert_cols(7)                  # directly right of last col -> unchanged
    assert s.get_raw("A10") == "=SUM(B1:F1)+SUM(D2:$E2)"
    s.delete_cols(2, 2)               # includes first endpoint of first range
    assert s.get_raw("A10") == "=SUM(B1:D1)+SUM(B2:$C2)"
    s.delete_cols(2, 2)
    assert s.get_raw("A10") == "=SUM(B1:B1)+SUM(#REF!)"
    s.delete_cols(1)
    assert s.get_raw("A10") == ""


def test_copy_ranges_and_absolute_mix():
    s = Sheet()
    s.set("C3", "=SUM($A1:B$2)&a$1&$a2")
    s.copy("C3", "E7")
    assert s.get_raw("E7") == "=SUM($A5:D$2)&C$1&$A6"
    s.copy("C3", "D3")
    assert s.get_raw("D3") == "=SUM($A1:C$2)&B$1&$a2"


def test_copy_returns_sorted_changed_and_handles_values():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "=A1*10")
    s.set("Z1", "=SUM(A2:B3)")
    ch = s.copy("A1:B1", "A3")
    assert ch == ["Z1", "A3", "B3"]
    assert s.get("B3") == 10.0 and s.get("Z1") == 11.0


def test_perf_structural_50k():
    s = Sheet()
    for i in range(1, 25001):
        s.set(f"A{i}", str(i))
        s.set(f"B{i}", f"=A{i}+SUM(A{i}:A{i + 3})")
    s.set("C1", "=SUM(B1:B25000)")
    total = s.get("C1")
    t0 = time.perf_counter()
    s.insert_rows(10000, 5)
    s.delete_rows(10000, 5)
    s.insert_cols(1)
    s.delete_cols(1)
    assert time.perf_counter() - t0 < 8
    assert s.get("C1") == total
    s.delete_rows(1)
    assert s.get_raw("B1") == "=A1+SUM(A1:A4)"
