import pytest

from gridcalc import CellError, Sheet


def ev(formula, **cells):
    s = Sheet()
    for addr, raw in cells.items():
        s.set(addr, raw)
    s.set("Z1", formula)
    return s.get("Z1")


def err(code):
    return CellError(code)


@pytest.mark.parametrize(
    "formula,expected",
    [
        ("=1+2*3", 7.0),
        ("=(1+2)*3", 9.0),
        ("=2^3^2", 64.0),
        ("=-2^2", 4.0),
        ("=2^-1", 0.5),
        ("=10-4-3", 3.0),
        ("=8/4/2", 1.0),
        ("=.5+1e3", 1000.5),
        ("=1+2&3", "33"),
        ("=1&2=12", False),  # & binds tighter than =, "12" (text) vs 12
        ("=\"say \"\"hi\"\"\"", 'say "hi"'),
        ("=TRUE", True),
        ("= 1 +  2 ", 3.0),
        ("=+3", 3.0),
        ("=--3", 3.0),
        ("=1/3&\"\"", "0.333333333333333"),
        ("=1e20&\"\"", "1e+20"),
        ("=2.5&\"\"", "2.5"),
        ("=TRUE&FALSE", "TRUEFALSE"),
    ],
)
def test_operators(formula, expected):
    v = ev(formula)
    assert type(v) is type(expected)
    assert v == expected


def test_deep_parentheses():
    depth = 1000
    assert ev("=" + "(" * depth + "1" + ")" * depth) == 1.0
    assert ev("=" + "-" * 1001 + "1") == -1.0


@pytest.mark.parametrize(
    "formula,expected",
    [
        ("=\"a\"=\"A\"", True),
        ("=\"a\"<\"B\"", True),
        ("=\"a\">5", True),
        ("=TRUE>\"z\"", True),
        ("=1=TRUE", False),
        ("=\"1\"=1", False),
        ("=A1=0", True),
        ("=A1=\"\"", True),
        ("=A1=FALSE", True),
        ("=A1=A2", True),
        ("=1<>2", True),
        ("=2<=2", True),
        ("=3>=4", False),
    ],
)
def test_comparisons(formula, expected):
    assert ev(formula) is expected


@pytest.mark.parametrize(
    "formula,code",
    [
        ("=1/0", "#DIV/0!"),
        ("=0^-1", "#DIV/0!"),
        ("=\"x\"+1", "#VALUE!"),
        ("=\"TRUE\"+1", "#VALUE!"),
        ("=\"\"+1", "#VALUE!"),
        ("=1e308*10", "#VALUE!"),
        ("=(-8)^0.5", "#VALUE!"),
        ("=1e400", "#VALUE!"),
        ("=+\"abc\"", "#VALUE!"),
        ("=A1:A3+1", "#VALUE!"),
        ("=A1:A1", "#VALUE!"),
        ("=FOO(1)", "#NAME?"),
        ("=foo", "#NAME?"),
        ("=FOO(1/0)", "#NAME?"),
        ("=ROUND(1)", "#VALUE!"),
        ("=SUM()", "#VALUE!"),
        ("=NOT(1,2)", "#VALUE!"),
        ("=IF(1)", "#VALUE!"),
        ("=#DIV/0!", "#DIV/0!"),
        ("=#REF!+1", "#REF!"),
        ("=XFE1", "#REF!"),
        ("=A1048577", "#REF!"),
        ("=A0", "#REF!"),
        ("=SUM(A1:A1048577)", "#REF!"),
        ("=1/0+\"x\"+1", "#DIV/0!"),
        ("=\"x\"+(1/0)", "#VALUE!"),
        ("=(1/0)+\"x\"", "#DIV/0!"),
        ("=-\"x\"&(1/0)", "#VALUE!"),
        ("=SUM(\"x\", 1/0)", "#VALUE!"),
        ("=SUM(1/0, \"x\")", "#DIV/0!"),
        ("=A1:A2&(1/0)", "#VALUE!"),
        ("=(1/0)=#REF!", "#DIV/0!"),
        ("=(1/0)&#REF!", "#DIV/0!"),
        ("=", "#PARSE!"),
        ("=1+", "#PARSE!"),
        ("=(1", "#PARSE!"),
        ("=1)", "#PARSE!"),
        ("=\"abc", "#PARSE!"),
        ("=1 2", "#PARSE!"),
        ("=#FOO!", "#PARSE!"),
        ("=SUM(1,)", "#PARSE!"),
        ("=(1,2)", "#PARSE!"),
        ("=1%", "#PARSE!"),
        ("=*1", "#PARSE!"),
    ],
)
def test_errors(formula, code):
    assert ev(formula) == err(code)


def test_coercion_of_cells():
    assert ev("=A1+1", A1="'3") == 4.0
    assert ev("=A1+1", A1="' 3 ") == 4.0
    assert ev("=A1+A2", A1="TRUE") == 1.0
    assert ev("=A1&\"x\"", A1="") == "x"
    assert ev("=A1") == 0.0
    assert ev("=IF(TRUE,A1)") == 0.0
    assert ev("=-A1") == 0.0 and str(ev("=-A1")) == "0.0"
    assert ev("=A1", A1="hi") == "hi"


def test_references_are_case_insensitive_and_allow_leading_zeros():
    assert ev("=sum(a1, $b$01)", A1="2", B1="3") == 5.0


@pytest.mark.parametrize(
    "formula,expected",
    [
        ("=SUM(A1:A5)", 6.0),  # text, bool, empty skipped
        ("=SUM(A1:A4, 1, TRUE, \"2\")", 10.0),
        ("=SUM(A2)", 0.0),  # single ref acts like a range: text skipped
        ("=AVERAGE(A1:A4)", 3.0),
        ("=MIN(A1:A4)", 1.0),
        ("=MAX(A1:A4)", 5.0),
        ("=MIN(A2:A3)", 0.0),
        ("=MAX(B1:B9)", 0.0),
        ("=COUNT(A1:A4)", 2.0),
        ("=COUNT(\"3\", TRUE, \"abc\")", 2.0),
        ("=COUNT(A2)", 0.0),
        ("=SUM(A1 : A4)", 6.0),
        ("=SUM(A4:A1)", 6.0),
    ],
)
def test_aggregates(formula, expected):
    v = ev(formula, A1="1", A2="x", A3="TRUE", A4="5")
    assert v == expected
    assert type(v) is float


def test_aggregate_errors():
    assert ev("=AVERAGE(B1:B3)") == err("#DIV/0!")
    assert ev("=SUM(A1:A2)", A1="1", A2="=1/0") == err("#DIV/0!")
    assert ev("=COUNT(A1:A2)", A1="1", A2="=1/0") == err("#DIV/0!")
    assert ev("=COUNT(1/0)") == err("#DIV/0!")
    assert ev("=SUM(\"x\")") == err("#VALUE!")
    assert ev("=SUM(A1:A2, 1/0)", A1="=#REF!") == err("#REF!")


def test_if_and_iferror():
    assert ev("=IF(1>0, \"y\", \"n\")") == "y"
    assert ev("=IF(0, \"y\", \"n\")") == "n"
    assert ev("=IF(FALSE, 1)") is False
    assert ev("=IF(TRUE, 1, 1/0)") == 1.0  # only chosen branch evaluated
    assert ev("=IF(\"true\", 1, 2)") == 1.0
    assert ev("=IF(\"x\", 1, 2)") == err("#VALUE!")
    assert ev("=IF(A1, 1, 2)") == 2.0
    assert ev("=IF(A1:A2, 1, 2)") == err("#VALUE!")
    assert ev("=IF(1/0, 1, 2)") == err("#DIV/0!")
    assert ev("=IFERROR(1/0, \"f\")") == "f"
    assert ev("=IFERROR(5, 1/0)") == 5.0
    assert ev("=IFERROR(A1:A3, 0)") == 0.0
    assert ev("=IFERROR(A1, 7)") == 0.0


def test_logical_functions():
    assert ev("=AND(TRUE, 1)") is True
    assert ev("=AND(TRUE, 0)") is False
    assert ev("=OR(FALSE, 0)") is False
    assert ev("=OR(A1:A3)", A1="x", A2="0", A3="TRUE") is True
    assert ev("=AND(A1:A3)", A1="x", A2="0", A3="TRUE") is False
    assert ev("=AND(A1:A3)", A1="x") == err("#VALUE!")
    assert ev("=AND(\"x\")") == err("#VALUE!")
    assert ev("=AND(\"true\")") is True
    assert ev("=AND(TRUE, A9)") is False  # scalar empty ref is FALSE
    assert ev("=OR(1/0, TRUE)") == err("#DIV/0!")
    assert ev("=NOT(0)") is True
    assert ev("=NOT(A1:A2)") == err("#VALUE!")


@pytest.mark.parametrize(
    "formula,expected",
    [
        ("=ROUND(2.5, 0)", 3.0),
        ("=ROUND(-2.5, 0)", -3.0),
        ("=ROUND(0.125, 2)", 0.13),
        ("=ROUND(2.675, 2)", 2.68),
        ("=ROUND(1250, -2)", 1300.0),
        ("=ROUND(1.26, 1.9)", 1.3),
        ("=ROUND(-0.4, 0)", 0.0),
        ("=ABS(-3)", 3.0),
        ("=ABS(\"-2\")", 2.0),
        ("=LEN(\"hello\")", 5.0),
        ("=LEN(123)", 3.0),
        ("=LEN(TRUE)", 4.0),
        ("=LEN(A9)", 0.0),
        ("=CONCAT(\"a\", 1, TRUE)", "a1TRUE"),
        ("=CONCAT(A1:B2)", "abcd"),
    ],
)
def test_scalar_functions(formula, expected):
    v = ev(formula, A1="a", B1="b", A2="c", B2="d")
    assert type(v) is type(expected)
    assert v == expected


def test_scalar_functions_reject_ranges():
    for f in ["=ABS(A1:A2)", "=LEN(A1:A2)", "=ROUND(A1:A2, 0)", "=ROUND(1, A1:A2)"]:
        assert ev(f) == err("#VALUE!")


def test_get_raw_keeps_formula_text():
    s = Sheet()
    s.set("A1", "= sum( a1:b2 ) ")
    assert s.get_raw("A1") == "= sum( a1:b2 ) "
