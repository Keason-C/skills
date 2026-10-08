import pytest

from gridcalc import CellError, Sheet

DIV0 = CellError("#DIV/0!")
VALUE = CellError("#VALUE!")
REF = CellError("#REF!")
NAME = CellError("#NAME?")


@pytest.fixture
def sheet():
    """B1:B5 = 1, 2, "text", TRUE, (empty); C1 = #DIV/0!; D1 = '7 (numeric-looking text)."""
    s = Sheet()
    s.set("B1", "1")
    s.set("B2", "2")
    s.set("B3", "text")
    s.set("B4", "TRUE")
    s.set("C1", "=1/0")
    s.set("D1", "'7")
    return s


def ev(sheet, formula):
    sheet.set("A1", formula)
    return sheet.get("A1")


# -- aggregates ----------------------------------------------------------------


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("=SUM(B1:B5)", 3.0),
        ("=SUM(B5:B1)", 3.0),
        ("=SUM(B1:B2, 10)", 13.0),
        ("=SUM(B1)", 1.0),
        ("=SUM(B3)", 0.0),
        ("=SUM(B4)", 0.0),
        ("=SUM((B4))", 0.0),
        ("=SUM(D1)", 0.0),
        ('=SUM("3")', 3.0),
        ("=SUM(TRUE)", 1.0),
        ("=SUM(1, 2, 3)", 6.0),
        ("=SUM(B5)", 0.0),
        ("=AVERAGE(B1:B5)", 1.5),
        ("=AVERAGE(B1:B2, 6)", 3.0),
        ("=MIN(B1:B5)", 1.0),
        ("=MAX(B1:B5)", 2.0),
        ("=MIN(B3:B5)", 0.0),
        ("=MAX(B3:B5)", 0.0),
        ("=MAX(B1:B2, -5, 9)", 9.0),
        ("=MIN(B1:B2, -5)", -5.0),
        ("=COUNT(B1:B5)", 2.0),
        ('=COUNT("3")', 1.0),
        ("=COUNT(TRUE)", 1.0),
        ('=COUNT("x")', 0.0),
        ("=COUNT(B3)", 0.0),
        ('=COUNT(B1:B5, 1, "x")', 3.0),
        ("=sum(b1:b2)", 3.0),
    ],
)
def test_aggregates(sheet, formula, expected):
    v = ev(sheet, formula)
    assert type(v) is float
    assert v == expected


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("=SUM(B1:C1)", DIV0),
        ("=SUM(C1)", DIV0),
        ('=SUM("x")', VALUE),
        ("=SUM(1/0, XFE1)", DIV0),
        ("=COUNT(1/0)", DIV0),
        ("=COUNT(C1)", DIV0),
        ("=AVERAGE(B3:B5)", DIV0),
        ('=MAX(B1:B2, "x")', VALUE),
        ("=SUM(IF(TRUE, B1:B2, 0))", VALUE),
        ("=SUM(IF(TRUE, B3, 0))", VALUE),
    ],
)
def test_aggregate_errors(sheet, formula, expected):
    assert ev(sheet, formula) == expected


def test_aggregate_over_huge_sparse_range(sheet):
    assert ev(sheet, "=SUM(A2:XFD1048576)") == 2.0  # row 1 excluded
    assert ev(sheet, "=SUM(B1:B1048576)") == 3.0
    assert ev(sheet, "=COUNT(B1:B1048576)") == 2.0
    assert ev(sheet, "=COUNT(B1:XFD1048576)") == DIV0  # C1


def test_range_error_order_is_row_major():
    s = Sheet()
    s.set("C1", "=XFE1")
    s.set("B2", "=1/0")
    s.set("A1", "=SUM(B1:C2)")
    assert s.get("A1") == REF


# -- IF / IFERROR ----------------------------------------------------------------


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("=IF(TRUE, 1, 2)", 1.0),
        ("=IF(FALSE, 1, 2)", 2.0),
        ("=IF(0, 1, 2)", 2.0),
        ("=IF(-3, 1, 2)", 1.0),
        ('=IF("true", 1, 2)', 1.0),
        ('=IF("FALSE", 1, 2)', 2.0),
        ("=IF(B5, 1, 2)", 2.0),
        ("=IF(FALSE, 1)", False),
        ("=IF(TRUE, 1/0, 2)", DIV0),
        ("=IF(FALSE, 1/0, 2)", 2.0),
        ("=IF(TRUE, 1, 1/0)", 1.0),
        ("=IF(1/0, 1, 2)", DIV0),
        ('=IF("x", 1, 2)', VALUE),
        ("=IF(B1:B2, 1, 2)", VALUE),
        ("=IF(TRUE, B5)", 0.0),
        ("=IF(TRUE, B1:B2)", VALUE),
        ("=IF(TRUE, B3)", "text"),
        ("=IF(1, 2, 3, 4)", VALUE),
        ("=IF(1)", VALUE),
        ("=IF(TRUE, 1, ROUND(1))", 1.0),
        ('=IF(B1=1, "one", "other")', "one"),
        ("=IFERROR(1/0, 5)", 5.0),
        ("=IFERROR(3, 5)", 3.0),
        ('=IFERROR(C1, "bad")', "bad"),
        ("=IFERROR(B1:B2, 9)", 9.0),
        ("=IFERROR(ROUND(1), 5)", 5.0),
        ("=IFERROR(FOO(1), 5)", 5.0),
        ("=IFERROR(1/0, 1/0)", DIV0),
        ("=IFERROR(1)", VALUE),
        ("=IFERROR(B5, 1)", 0.0),
    ],
)
def test_conditionals(sheet, formula, expected):
    v = ev(sheet, formula)
    assert v == expected
    assert type(v) is type(expected)


# -- logical functions -------------------------------------------------------------


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("=AND(TRUE, 1)", True),
        ("=AND(TRUE, 0)", False),
        ("=OR(FALSE, 0)", False),
        ("=OR(FALSE, 2)", True),
        ('=AND("true", TRUE)', True),
        ("=AND(B1:B5)", True),
        ("=OR(B3:B5)", True),
        ("=AND(B1:B2, FALSE)", False),
        ("=AND(B5, TRUE)", True),
        ("=NOT(TRUE)", False),
        ("=NOT(0)", True),
        ('=NOT("false")', True),
        ("=NOT(B5)", True),
        ("=AND(B3)", VALUE),
        ("=OR(B5:B5)", VALUE),
        ('=AND("x")', VALUE),
        ("=AND(C1, TRUE)", DIV0),
        ("=OR(TRUE, 1/0)", DIV0),
        ("=NOT(B1:B2)", VALUE),
        ("=NOT(1, 2)", VALUE),
        ("=NOT()", VALUE),
        ("=AND()", VALUE),
    ],
)
def test_logical_functions(sheet, formula, expected):
    v = ev(sheet, formula)
    assert v == expected
    assert type(v) is type(expected)


# -- ROUND / ABS / LEN / CONCAT ------------------------------------------------------


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("=ROUND(2.675, 2)", 2.68),
        ("=ROUND(2.5, 0)", 3.0),
        ("=ROUND(-2.5, 0)", -3.0),
        ("=ROUND(0.5, 0)", 1.0),
        ("=ROUND(1.005, 2)", 1.01),
        ("=ROUND(1234, -2)", 1200.0),
        ("=ROUND(1250, -2)", 1300.0),
        ("=ROUND(3.14159, 2.9)", 3.14),
        ("=ROUND(3.14159, -0.5)", 3.0),
        ('=ROUND("2.5", TRUE)', 2.5),
        ("=ROUND(B5, 0)", 0.0),
        ("=ROUND(1.5, 400)", 1.5),
        ("=ROUND(1.5, -400)", 0.0),
        ("=ROUND(-0.4, 0)", 0.0),
        ("=ABS(-3)", 3.0),
        ('=ABS("-2")', 2.0),
        ("=ABS(TRUE)", 1.0),
        ('=LEN("hello")', 5.0),
        ("=LEN(12.5)", 4.0),
        ("=LEN(TRUE)", 4.0),
        ("=LEN(B5)", 0.0),
        ("=LEN(B1)", 1.0),
        ("=LEN(1/3)", 17.0),
        ('=CONCAT("a", 1, TRUE)', "a1TRUE"),
        ("=CONCAT(B1:B5)", "12textTRUE"),
        ("=CONCAT(B1:C2)", "12"),
        ("=CONCAT(B5)", ""),
    ],
)
def test_scalar_functions(sheet, formula, expected):
    sheet.set("C1", "")
    v = ev(sheet, formula)
    assert v == expected
    assert type(v) is type(expected)


def test_round_result_is_not_negative_zero(sheet):
    v = ev(sheet, "=ROUND(-0.4, 0)")
    assert str(v) == "0.0"


def test_concat_range_is_row_major():
    s = Sheet()
    s.set("B1", "a")
    s.set("C1", "b")
    s.set("B2", "c")
    s.set("C2", "d")
    s.set("A1", "=CONCAT(B1:C2)")
    assert s.get("A1") == "abcd"


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("=ROUND(1)", VALUE),
        ("=ROUND(1/0)", VALUE),
        ("=ROUND(1/0, 1)", DIV0),
        ('=ROUND("x", 1)', VALUE),
        ("=ROUND(B1:B2, 1)", VALUE),
        ("=ABS(B1:B2)", VALUE),
        ('=ABS("x")', VALUE),
        ("=ABS()", VALUE),
        ("=LEN(B1:B2)", VALUE),
        ("=LEN(C1)", DIV0),
        ("=LEN(1, 2)", VALUE),
        ("=CONCAT(B1, C1)", DIV0),
        ("=CONCAT()", VALUE),
        ("=SUM()", VALUE),
        ("=AVERAGE()", VALUE),
        ("=MIN()", VALUE),
        ("=MAX()", VALUE),
        ("=COUNT()", VALUE),
    ],
)
def test_function_errors(sheet, formula, expected):
    assert ev(sheet, formula) == expected


def test_unknown_function_beats_arity_and_skips_arguments(sheet):
    assert ev(sheet, "=NOPE()") == NAME
    assert ev(sheet, "=NOPE(1/0)") == NAME


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("=ROUND(1e28, 0)", 1e28),
        ("=ROUND(1e30, -2)", 1e30),
        ("=ROUND(1e300*10, 0)", 1e301),
        ("=ROUND(123456789012345678901234567890, 5)", 1.2345678901234568e29),
        ("=ROUND(1e-300, 400)", 1e-300),
        ("=ROUND(1.5e300, -300)", 2e300),
        ("=ROUND(1, -1e20)", 0.0),
        ("=ROUND(1.5, 1e20)", 1.5),
    ],
)
def test_round_extreme_magnitudes(sheet, formula, expected):
    assert ev(sheet, formula) == expected
