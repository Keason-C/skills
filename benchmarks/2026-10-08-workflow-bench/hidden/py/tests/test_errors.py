"""Error values: production, propagation, leftmost-wins, #NAME?, #PARSE!, range-as-scalar."""

import pytest

from gridcalc import CellError, Sheet


def is_err(v, code):
    return isinstance(v, CellError) and v.code == code


def value_of(raw):
    s = Sheet()
    s.set("A1", raw)
    return s.get("A1")


def two_errors():
    """A1 = #DIV/0!, A2 = #NAME?"""
    s = Sheet()
    s.set("A1", "=1/0")
    s.set("A2", "=NOSUCHFUNC(1)")
    return s


# --- producing errors ---------------------------------------------------------

def test_division_by_zero():
    assert is_err(value_of("=1/0"), "#DIV/0!")


def test_division_by_computed_zero():
    assert is_err(value_of("=1/(2-2)"), "#DIV/0!")


def test_division_by_empty_cell():
    s = Sheet()
    s.set("B1", "=5/A1")
    assert is_err(s.get("B1"), "#DIV/0!")


def test_error_value_is_cellerror_instance():
    v = value_of("=1/0")
    assert isinstance(v, CellError)
    assert v == CellError("#DIV/0!")


def test_text_cell_in_arithmetic():
    s = Sheet()
    s.set("A1", "hello")
    s.set("B1", "=A1*2")
    assert is_err(s.get("B1"), "#VALUE!")


def test_unknown_function_is_name_error():
    assert is_err(value_of("=NOSUCHFUNC(1)"), "#NAME?")


def test_unknown_function_inside_expression():
    assert is_err(value_of("=1+FOO(2)"), "#NAME?")


# --- #PARSE! --------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw",
    [
        "=1+",
        "=(1+2",
        "=1+2)",
        '="abc',
        "=*3",
        "=1+*2",
        "=2^",
        "=SUM(1",
        "=A1:",
        "=)(",
        "=1,2",
        "=",
    ],
)
def test_parse_errors(raw):
    assert is_err(value_of(raw), "#PARSE!")


def test_parse_error_keeps_raw():
    s = Sheet()
    s.set("A1", "=(1+2")
    assert s.get_raw("A1") == "=(1+2"


def test_parse_error_propagates():
    s = Sheet()
    s.set("A1", "=1+")
    s.set("B1", "=A1+1")
    assert is_err(s.get("B1"), "#PARSE!")


# --- propagation ------------------------------------------------------------------

def test_propagation_through_reference_chain():
    s = Sheet()
    s.set("A1", "=1/0")
    s.set("B1", "=A1+1")
    s.set("C1", "=B1*2")
    assert is_err(s.get("C1"), "#DIV/0!")


def test_propagation_through_function_argument():
    s = Sheet()
    s.set("A1", "=1/0")
    s.set("B1", "=ABS(A1)")
    assert is_err(s.get("B1"), "#DIV/0!")


def test_propagation_through_len():
    s = Sheet()
    s.set("A1", "=NOSUCHFUNC(1)")
    s.set("B1", "=LEN(A1)")
    assert is_err(s.get("B1"), "#NAME?")


def test_propagation_through_concat_operator():
    s = Sheet()
    s.set("A1", "=1/0")
    s.set("B1", '=A1&"x"')
    assert is_err(s.get("B1"), "#DIV/0!")


def test_propagation_through_comparison():
    s = Sheet()
    s.set("A1", "=1/0")
    s.set("B1", "=A1>0")
    assert is_err(s.get("B1"), "#DIV/0!")


def test_iferror_fallback_error_returned():
    assert is_err(value_of("=IFERROR(1/0,NOSUCHFUNC(1))"), "#NAME?")


# --- leftmost error wins ---------------------------------------------------------

def test_leftmost_error_plus():
    s = two_errors()
    s.set("B1", "=A1+A2")
    assert is_err(s.get("B1"), "#DIV/0!")


def test_leftmost_error_plus_reversed():
    s = two_errors()
    s.set("B1", "=A2+A1")
    assert is_err(s.get("B1"), "#NAME?")


def test_leftmost_error_concat_operator():
    s = two_errors()
    s.set("B1", "=A2&A1")
    assert is_err(s.get("B1"), "#NAME?")


def test_leftmost_error_comparison():
    s = two_errors()
    s.set("B1", "=A1=A2")
    assert is_err(s.get("B1"), "#DIV/0!")


def test_leftmost_error_sum_args():
    s = two_errors()
    s.set("B1", "=SUM(A2,A1)")
    assert is_err(s.get("B1"), "#NAME?")


def test_leftmost_error_concat_function():
    s = two_errors()
    s.set("B1", "=CONCAT(A1,A2)")
    assert is_err(s.get("B1"), "#DIV/0!")


def test_leftmost_error_in_range():
    s = two_errors()
    s.set("B1", "=SUM(A1:A2)")
    assert is_err(s.get("B1"), "#DIV/0!")


def test_leftmost_error_literal_expressions():
    assert is_err(value_of("=1/0+NOSUCHFUNC(1)"), "#DIV/0!")


def test_leftmost_error_literal_expressions_reversed():
    assert is_err(value_of("=NOSUCHFUNC(1)+1/0"), "#NAME?")


# --- range used as scalar ------------------------------------------------------------

@pytest.mark.parametrize(
    "formula",
    ["=A1:A3+1", "=A1:A2", "=ABS(A1:A2)", '=A1:A2&"x"', "=SUM(A1:A3+1)"],
)
def test_range_as_scalar_is_value_error(formula):
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    s.set("A3", "3")
    s.set("C1", formula)
    assert is_err(s.get("C1"), "#VALUE!")
