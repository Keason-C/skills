"""Operator precedence, associativity, unary minus vs ^, concatenation, comparisons."""

import pytest

from gridcalc import CellError, Sheet


def is_err(v, code):
    return isinstance(v, CellError) and v.code == code


def is_num(v, x):
    return type(v) is float and v == pytest.approx(x)


def value_of(raw):
    s = Sheet()
    s.set("A1", raw)
    return s.get("A1")


# --- arithmetic precedence / associativity ----------------------------------

def test_mul_before_add():
    assert is_num(value_of("=2+3*4"), 14.0)


def test_parentheses_override():
    assert is_num(value_of("=(2+3)*4"), 20.0)


def test_subtraction_left_assoc():
    assert is_num(value_of("=1-2-3"), -4.0)


def test_add_sub_left_assoc():
    assert is_num(value_of("=2-3+4"), 3.0)


def test_division_left_assoc():
    assert is_num(value_of("=100/10/5"), 2.0)


def test_power_before_mul():
    assert is_num(value_of("=2*3^2"), 18.0)


def test_power_before_add_and_mul():
    assert is_num(value_of("=2+3*4^2"), 50.0)


def test_power_left_assoc():
    assert is_num(value_of("=2^3^2"), 64.0)


def test_fractional_power():
    assert is_num(value_of("=2^0.5"), 1.4142135623730951)


def test_division_result():
    assert is_num(value_of("=1/4"), 0.25)


# --- unary minus vs ^ ---------------------------------------------------------

def test_unary_minus_binds_tighter_than_power():
    assert is_num(value_of("=-2^2"), 4.0)


def test_binary_minus_lower_than_power():
    assert is_num(value_of("=0-2^2"), -4.0)


def test_parenthesised_negation_of_power():
    assert is_num(value_of("=-(2^2)"), -4.0)


def test_negative_base_odd_power():
    assert is_num(value_of("=-2^3"), -8.0)


def test_unary_minus_in_exponent():
    assert is_num(value_of("=2^-1"), 0.5)


def test_unary_minus_both_sides_of_power():
    assert is_num(value_of("=-2^-2"), 0.25)


def test_power_left_assoc_with_unary_exponent():
    # (2^(-2))^2
    assert is_num(value_of("=2^-2^2"), 0.0625)


def test_unary_minus_of_reference_then_power():
    s = Sheet()
    s.set("A1", "3")
    s.set("B1", "=-A1^2")
    assert is_num(s.get("B1"), 9.0)


def test_double_unary_minus():
    assert is_num(value_of("=--2"), 2.0)


def test_mixed_unary_signs():
    assert is_num(value_of("=+-+2"), -2.0)


def test_mul_by_negative():
    assert is_num(value_of("=2*-3"), -6.0)


def test_mul_by_negative_power():
    # 2 * ((-2)^2)
    assert is_num(value_of("=2*-2^2"), 8.0)


# --- coercion in arithmetic ----------------------------------------------------

def test_booleans_in_arithmetic():
    assert is_num(value_of("=TRUE+TRUE"), 2.0)


def test_false_in_arithmetic():
    assert is_num(value_of("=FALSE*5+1"), 1.0)


def test_empty_reference_in_arithmetic_is_zero():
    s = Sheet()
    s.set("B1", "=A1+1")
    assert is_num(s.get("B1"), 1.0)


def test_non_numeric_text_in_arithmetic_is_value_error():
    assert is_err(value_of('="abc"+1'), "#VALUE!")


def test_unary_minus_on_non_numeric_text_is_value_error():
    assert is_err(value_of('=-"abc"'), "#VALUE!")


# --- concatenation ---------------------------------------------------------------

def test_concat_strings():
    assert value_of('="a"&"b"&"c"') == "abc"


def test_concat_empty_reference_is_empty_string():
    s = Sheet()
    s.set("B1", '=A1&"x"')
    assert s.get("B1") == "x"


def test_concat_true():
    assert value_of('=TRUE&"x"') == "TRUEx"


def test_concat_false():
    assert value_of('="x"&FALSE') == "xFALSE"


def test_concat_binds_tighter_than_comparison():
    # ("a"&"b")="ab", not "a"&("b"="ab")
    assert value_of('="a"&"b"="ab"') is True


def test_comparison_rhs_concat():
    assert value_of('="ab"="a"&"b"') is True


def test_concat_text_cells():
    s = Sheet()
    s.set("A1", "foo")
    s.set("A2", "bar")
    s.set("B1", "=A1&A2")
    assert s.get("B1") == "foobar"


# --- comparisons --------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("=1<2", True),
        ("=2>1", True),
        ("=2<=2", True),
        ("=3>=4", False),
        ("=1<>2", True),
        ("=3<>3", False),
        ("=1=1", True),
        ("=2=3", False),
        ("=-1<0", True),
    ],
)
def test_numeric_comparisons(raw, expected):
    assert value_of(raw) is expected


def test_arithmetic_binds_tighter_than_comparison():
    assert value_of("=1+1=2") is True


def test_comparison_left_assoc():
    # (1<2)=TRUE
    assert value_of("=1<2=TRUE") is True


def test_boolean_equality():
    assert value_of("=TRUE=FALSE") is False


def test_comparison_of_cells():
    s = Sheet()
    s.set("A1", "10")
    s.set("A2", "9.5")
    s.set("B1", "=A1>A2")
    assert s.get("B1") is True
