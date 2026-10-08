import pytest

from gridcalc import CellError, Sheet

DIV0 = CellError("#DIV/0!")
VALUE = CellError("#VALUE!")
REF = CellError("#REF!")
NAME = CellError("#NAME?")
PARSE = CellError("#PARSE!")


def ev(formula, **cells):
    """Evaluate ``formula`` in A1 of a sheet pre-filled with ``cells`` (e.g. B1="3")."""
    s = Sheet()
    for addr, raw in cells.items():
        s.set(addr, raw)
    s.set("A1", formula)
    return s.get("A1")


# -- literals and basic arithmetic ------------------------------------------


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("=3", 3.0),
        ("=2.5", 2.5),
        ("=.5", 0.5),
        ("=1e3", 1000.0),
        ("=1+2*3", 7.0),
        ("=(1+2)*3", 9.0),
        ("=10-4-3", 3.0),
        ("=12/2/3", 2.0),
        ("=2^3^2", 64.0),
        ("=-2^2", 4.0),
        ("=2^-1", 0.5),
        ("=--3", 3.0),
        ("=+-+3", -3.0),
        ("=2*-3", -6.0),
        ("= 1 +\t2 ", 3.0),
        ("=0^0", 1.0),
        ("=-0", 0.0),
    ],
)
def test_arithmetic(formula, expected):
    v = ev(formula)
    assert type(v) is float
    assert v == expected


def test_negative_zero_is_normalised():
    v = ev("=-0*1")
    assert v == 0.0 and str(v) == "0.0"


@pytest.mark.parametrize(
    "formula, expected",
    [
        ('="abc"', "abc"),
        ('="say ""hi"""', 'say "hi"'),
        ('=""', ""),
        ("=TRUE", True),
        ("=false", False),
    ],
)
def test_string_and_boolean_literals(formula, expected):
    assert ev(formula) == expected
    assert type(ev(formula)) is type(expected)


def test_number_results_are_always_float():
    assert type(ev("=TRUE+0")) is float


# -- references --------------------------------------------------------------


def test_references_and_dollar_forms():
    assert ev("=B1+$B1+B$1+$B$1", B1="2") == 8.0


def test_references_are_case_insensitive():
    assert ev("=b1*2", B1="4") == 8.0


def test_reference_to_empty_cell_yields_zero():
    v = ev("=B1")
    assert type(v) is float and v == 0.0


def test_reference_to_text_yields_text():
    assert ev("=B1", B1="hi") == "hi"


def test_out_of_grid_reference_is_ref_error():
    assert ev("=XFE1") == REF
    assert ev("=A1048577") == REF


def test_range_where_scalar_expected_is_value_error():
    assert ev("=B1:B3+1", B1="1") == VALUE
    assert ev("=B1:B3") == VALUE
    assert ev("=B1:B1") == VALUE


# -- coercion ------------------------------------------------------------------


@pytest.mark.parametrize(
    "formula, expected",
    [
        ('="12"+1', 13.0),
        ('=" 12 "+1', 13.0),
        ("=TRUE+TRUE", 2.0),
        ("=FALSE*5", 0.0),
        ('=+"12"', 12.0),
        ("=+TRUE", 1.0),
        ("=-B1", 0.0),
    ],
)
def test_arithmetic_coercion(formula, expected):
    assert ev(formula) == expected


@pytest.mark.parametrize(
    "formula", ['=""+1', '="TRUE"+1', '="abc"*2', '=+"a"', '=-"x"']
)
def test_non_numeric_text_in_arithmetic_is_value_error(formula):
    assert ev(formula) == VALUE


def test_text_cell_that_looks_numeric_coerces():
    assert ev("=B1+1", B1="'123") == 124.0


@pytest.mark.parametrize(
    "formula, expected",
    [
        ('="a"&"b"', "ab"),
        ('=1&"x"', "1x"),
        ('=0.1+0.2&""', "0.3"),
        ('=1e20&""', "1e+20"),
        ('=2.5&""', "2.5"),
        ('=-0&""', "0"),
        ("=TRUE&FALSE", "TRUEFALSE"),
        ('=B1&"x"', "x"),
        ('=1/3&""', "0.333333333333333"),
        ("=1&2", "12"),
    ],
)
def test_concatenation_operator(formula, expected):
    assert ev(formula) == expected


# -- arithmetic errors -------------------------------------------------------


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("=1/0", DIV0),
        ("=1/B1", DIV0),
        ("=0^-1", DIV0),
        ("=(-8)^(1/3)", VALUE),
        ("=10^400", VALUE),
        ("=1e308*10", VALUE),
        ("=1e308+1e308", VALUE),
    ],
)
def test_arithmetic_errors(formula, expected):
    assert ev(formula) == expected


def test_leftmost_error_wins():
    assert ev("=1/0+XFE1") == DIV0
    assert ev("=XFE1+1/0") == REF
    assert ev('="x"+1/0') == VALUE
    assert ev('=1/0&"x"*1') == DIV0


def test_errors_propagate_through_operators():
    assert ev("=-(1/0)") == DIV0
    assert ev("=(1/0)=1") == DIV0
    assert ev('=(1/0)&"a"') == DIV0


def test_error_literals_in_formulas():
    for code in CellError.CODES:
        assert ev(f"={code}") == CellError(code)
    assert ev("=#ref!") == REF


def test_error_values_in_referenced_cells_propagate():
    assert ev("=B1+1", B1="=1/0") == DIV0


# -- comparisons ---------------------------------------------------------------


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("=1=1", True),
        ("=1<>1", False),
        ("=1<2", True),
        ("=2<=2", True),
        ("=3>=4", False),
        ("=3>2", True),
        ('="a"="A"', True),
        ('="apple"<"Banana"', True),
        ('=1="1"', False),
        ('=1<"0"', True),
        ('="z"<TRUE', True),
        ("=1<FALSE", True),
        ("=B1=0", True),
        ('=B1=""', True),
        ("=B1=FALSE", True),
        ("=B1=C1", True),
        ("=1+1=2", True),
        ('="a"&"b"="AB"', True),
        ("=1=1=TRUE", True),
        ("=TRUE>FALSE", True),
    ],
)
def test_comparisons(formula, expected):
    assert ev(formula) is expected


# -- names and parse errors ----------------------------------------------------


@pytest.mark.parametrize(
    "formula", ["=foo", "=FOO(1)", "=foo(1/0)", "=A1B", "=Bar.Baz(1)"]
)
def test_unknown_names_are_name_errors(formula):
    assert ev(formula) == NAME


@pytest.mark.parametrize(
    "formula",
    [
        "=",
        "= ",
        "=1+",
        "=(1",
        "=1)",
        "=()",
        "=1 2",
        "=A0",
        "=A01",
        "=5%",
        "=A:A",
        "=1:1",
        "=Sheet1!A1",
        "={1,2}",
        '="abc',
        "=1,2",
        "=SUM(1,,2)",
        "=SUM(1,)",
        "=SUM(,1)",
        "=*2",
        "=$A",
        "=A1:",
        "=A1:B",
        "=@A1",
        "=#NOPE!",
    ],
)
def test_unparseable_formulas_are_parse_errors(formula):
    assert ev(formula) == PARSE


def test_raw_formula_text_is_kept_verbatim():
    s = Sheet()
    s.set("A1", "=sum( b1 , 2 )")
    assert s.get_raw("A1") == "=sum( b1 , 2 )"


def test_deep_parentheses():
    depth = 500
    assert ev("=" + "(" * depth + "1" + ")" * depth) == 1.0


def test_long_operator_chain():
    assert ev("=" + "+".join(["1"] * 5000)) == 5000.0


def test_long_unary_chain():
    assert ev("=" + "-" * 5001 + "1") == -1.0


def test_whitespace_around_function_paren_and_range_colon():
    assert ev("=SUM (B1 : B2)", B1="1", B2="2") == 3.0


def test_overflowing_number_literal_in_formula_is_value_error():
    assert ev("=1e400") == VALUE
    assert ev("=1e400*0") == VALUE


def test_deeply_nested_function_calls():
    depth = 1000
    assert ev("=" + "SUM(" * depth + "1" + ")" * depth) == 1.0
    assert ev("=" + "IF(TRUE," * depth + "7" + ",0)" * depth) == 7.0
