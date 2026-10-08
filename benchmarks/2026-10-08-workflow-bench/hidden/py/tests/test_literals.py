"""Literal input parsing (set() with non-formula raw) and formula literals."""

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


# --- numbers -----------------------------------------------------------------

def test_integer_literal_is_float():
    v = value_of("42")
    assert type(v) is float
    assert v == 42.0


def test_decimal_literal():
    assert is_num(value_of("3.25"), 3.25)


def test_leading_dot_decimal():
    assert is_num(value_of(".5"), 0.5)


def test_signed_leading_dot_decimal():
    assert is_num(value_of("-.5"), -0.5)


def test_explicit_plus_sign():
    assert is_num(value_of("+7"), 7.0)


def test_negative_integer():
    assert is_num(value_of("-12"), -12.0)


def test_exponent_lowercase():
    assert is_num(value_of("1e3"), 1000.0)


def test_exponent_uppercase_negative():
    assert is_num(value_of("-2.5E-2"), -0.025)


def test_leading_zeros_number():
    assert is_num(value_of("007"), 7.0)


def test_surrounding_whitespace_number_value():
    assert is_num(value_of(" 42 "), 42.0)


def test_surrounding_whitespace_number_raw_kept():
    s = Sheet()
    s.set("A1", " 42 ")
    assert s.get_raw("A1") == " 42 "


# --- apostrophe --------------------------------------------------------------

def test_apostrophe_forces_text():
    v = value_of("'123")
    assert type(v) is str
    assert v == "123"


def test_apostrophe_raw_keeps_apostrophe():
    s = Sheet()
    s.set("A1", "'123")
    assert s.get_raw("A1") == "'123"


def test_apostrophe_true_is_text():
    assert value_of("'TRUE") == "TRUE"
    assert type(value_of("'TRUE")) is str


def test_apostrophe_equals_is_text_not_formula():
    v = value_of("'=1+1")
    assert type(v) is str
    assert v == "=1+1"


# --- booleans ----------------------------------------------------------------

def test_true_uppercase():
    assert value_of("TRUE") is True


def test_true_lowercase():
    assert value_of("true") is True


def test_false_mixed_case():
    assert value_of("FaLsE") is False


def test_truex_is_text():
    assert value_of("TRUEX") == "TRUEX"


# --- text --------------------------------------------------------------------

def test_plain_text():
    v = value_of("hello world")
    assert type(v) is str
    assert v == "hello world"


def test_text_stored_without_stripping():
    assert value_of("  hello  ") == "  hello  "


def test_text_raw_without_stripping():
    s = Sheet()
    s.set("A1", "  hello  ")
    assert s.get_raw("A1") == "  hello  "


def test_leading_space_then_equals_is_text():
    v = value_of(" =1+1")
    assert type(v) is str
    assert v == " =1+1"


def test_error_code_spelling_literal_is_text():
    v = value_of("#DIV/0!")
    assert type(v) is str
    assert v == "#DIV/0!"


@pytest.mark.parametrize(
    "raw",
    ["1e", "1.2.3", "e3", "12abc", ".", "-", "1,000", "$5", "1e3.5", "--5"],
)
def test_malformed_numbers_are_text(raw):
    v = value_of(raw)
    assert type(v) is str
    assert v == raw


@pytest.mark.parametrize("raw", ["inf", "nan", "Infinity", "1_000", "0x10"])
def test_python_float_spellings_are_text(raw):
    v = value_of(raw)
    assert type(v) is str
    assert v == raw


# --- empty -------------------------------------------------------------------

def test_never_set_cell_is_none():
    s = Sheet()
    assert s.get("C7") is None
    assert s.get_raw("C7") == ""


def test_empty_string_clears_cell():
    s = Sheet()
    s.set("A1", "5")
    s.set("A1", "")
    assert s.get("A1") is None
    assert s.get_raw("A1") == ""


# --- formula literals --------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [("=2.5", 2.5), ("=.5", 0.5), ("=1e3", 1000.0), ("=2.5e1", 25.0), ("=7", 7.0)],
)
def test_formula_number_literals(raw, expected):
    assert is_num(value_of(raw), expected)


def test_formula_true_literal():
    assert value_of("=TRUE") is True


def test_formula_false_literal():
    assert value_of("=FALSE") is False


def test_formula_string_literal():
    v = value_of('="hello"')
    assert type(v) is str
    assert v == "hello"


def test_string_escaped_quotes():
    assert value_of('="say ""hi"""') == 'say "hi"'


def test_string_consisting_of_one_quote():
    assert value_of('=""""') == '"'


def test_formula_raw_returned_as_entered():
    s = Sheet()
    s.set("A1", '=1+2*"x"')
    assert s.get_raw("A1") == '=1+2*"x"'
