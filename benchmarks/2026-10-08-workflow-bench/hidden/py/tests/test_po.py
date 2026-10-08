"""Behaviour fixed only by the product owner's decisions (clarifications.md), not by the brief.

Section numbers refer to the numbered decisions in clarifications.md.
"""

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


# --- 1. number -> text formatting (".15g", -0 -> "0") ----------------------------------

@pytest.mark.parametrize(
    "formula,expected",
    [
        ('=1&""', "1"),
        ('=2.50&""', "2.5"),
        ('=0.1+0.2&""', "0.3"),
        ('=1/3&""', "0.333333333333333"),
        ('=1E20&""', "1e+20"),
        ('=10^15&""', "1e+15"),
        ('=123456.789&""', "123456.789"),
        ('=0*-1&""', "0"),
        ('="x"&-2.5', "x-2.5"),
    ],
)
def test_number_to_text_format(formula, expected):
    assert value_of(formula) == expected


def test_concat_binds_looser_than_plus():
    # (1+2)&3
    assert value_of("=1+2&3") == "33"


def test_len_of_number_uses_format():
    assert is_num(value_of("=LEN(1/3)"), 17.0)


def test_len_of_large_number():
    assert is_num(value_of("=LEN(1E20)"), 5.0)


def test_concat_function_number_cells():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "2.5")
    s.set("C1", "=CONCAT(A1:B1)")
    assert s.get("C1") == "12.5"


# --- 2. comparisons across types / case-insensitive text -----------------------------------

@pytest.mark.parametrize(
    "formula,expected",
    [
        ('="a">5', True),
        ('=5<"a"', True),
        ('="a"<5', False),
        ('=TRUE>"z"', True),
        ('=FALSE>"zzz"', True),
        ("=TRUE>1", True),
        ("=3>2>1", True),
        ('="abc"="ABC"', True),
        ('="a"<"B"', True),
        ('="Z">"a"', True),
        ('="b"<>"B"', False),
        ('="1"=1', False),
        ('=1="1"', False),
        ('="1"<>1', True),
    ],
)
def test_cross_type_and_text_comparisons(formula, expected):
    assert value_of(formula) is expected


@pytest.mark.parametrize(
    "formula,expected",
    [
        ("=A1=0", True),
        ('=A1=""', True),
        ("=A1=FALSE", True),
        ("=A1=A2", True),
        ("=A1<1", True),
        ('=A1<"a"', True),
        ("=A1<>0", False),
    ],
)
def test_empty_operand_takes_other_type(formula, expected):
    s = Sheet()
    s.set("C1", formula)
    assert s.get("C1") is expected


# --- 3. numeric text coercion in arithmetic --------------------------------------------------

@pytest.mark.parametrize(
    "formula,expected",
    [
        ('="3"+1', 4.0),
        ('=" 3 "*2', 6.0),
        ('="1e3"+0', 1000.0),
        ('="-.5"*2', -1.0),
    ],
)
def test_numeric_text_coerced(formula, expected):
    assert is_num(value_of(formula), expected)


@pytest.mark.parametrize("formula", ['=""+1', '="inf"+0', '="1_0"+0', '="0x1A"+0'])
def test_non_numeric_text_not_coerced(formula):
    assert is_err(value_of(formula), "#VALUE!")


def test_text_cell_holding_digits_coerced():
    s = Sheet()
    s.set("A1", "'7")
    s.set("B1", "=A1*3")
    assert is_num(s.get("B1"), 21.0)


def test_sum_scalar_text_coerced_but_range_text_skipped():
    s = Sheet()
    s.set("A1", "'5")
    s.set("A2", "1")
    s.set("B1", '=SUM("4",A1:A2)')
    assert is_num(s.get("B1"), 5.0)


def test_count_scalar_numeric_text_counted():
    assert is_num(value_of('=COUNT("4")'), 1.0)


# --- 4. ROUND ----------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "formula,expected",
    [
        ("=ROUND(2.5,0)", 3.0),
        ("=ROUND(-2.5,0)", -3.0),
        ("=ROUND(0.5,0)", 1.0),
        ("=ROUND(0.125,2)", 0.13),
        ("=ROUND(1250,-2)", 1300.0),
        ("=ROUND(-1250,-2)", -1300.0),
        ("=ROUND(15,-1)", 20.0),
        ("=ROUND(2.567,1.9)", 2.6),
        ("=ROUND(1234,-1.7)", 1230.0),
    ],
)
def test_round_half_away_from_zero(formula, expected):
    assert is_num(value_of(formula), expected)


# --- 5. wrong argument count / unknown function -------------------------------------------------

@pytest.mark.parametrize(
    "formula",
    [
        "=NOT(1,2)",
        "=NOT()",
        "=IF(TRUE)",
        "=IF(TRUE,1,2,3)",
        "=ROUND(1)",
        "=SUM()",
        "=AVERAGE()",
        "=ABS(1,2)",
        '=LEN("a","b")',
        "=IFERROR(1)",
        "=AND()",
    ],
)
def test_wrong_arg_count_is_value_error(formula):
    assert is_err(value_of(formula), "#VALUE!")


def test_unknown_function_checked_before_arguments():
    assert is_err(value_of("=NOSUCHFUNC(1/0)"), "#NAME?")


def test_unknown_function_no_args():
    assert is_err(value_of("=NOSUCHFUNC()"), "#NAME?")


# --- 6. bare reference to empty cell -------------------------------------------------------------

def test_bare_reference_to_empty_is_zero():
    s = Sheet()
    assert s.set("B1", "=A1") == ["B1"]
    v = s.get("B1")
    assert type(v) is float
    assert v == 0.0


def test_empty_reference_concat_empty_string():
    s = Sheet()
    s.set("B1", '=A1&""')
    assert s.get("B1") == ""


# --- 7. case-insensitive formulas, whitespace, canonical rewritten tokens ----------------------------

def test_lowercase_function_and_range():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    s.set("B1", "=sum(a1:a2)")
    assert is_num(s.get("B1"), 3.0)
    assert s.get_raw("B1") == "=sum(a1:a2)"


def test_mixed_case_function_and_refs():
    s = Sheet()
    s.set("A1", "5")
    s.set("B1", '=If(a1>0,"y","n")')
    assert s.get("B1") == "y"


def test_lowercase_reference_creates_dependency():
    s = Sheet()
    s.set("B1", "=a1*2")
    assert s.set("A1", "4") == ["A1", "B1"]
    assert is_num(s.get("B1"), 8.0)


def test_whitespace_between_tokens():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    s.set("B1", "=SUM( A1 , A2 ) * 2")
    assert is_num(s.get("B1"), 6.0)
    assert s.get_raw("B1") == "=SUM( A1 , A2 ) * 2"


def test_structural_rewrite_uppercases_only_changed_tokens():
    s = Sheet()
    s.set("C1", "=a1+b5")
    s.insert_rows(3)
    assert s.get_raw("C1") == "=a1+B6"


def test_structural_rewrite_range_token_canonical():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    s.set("B1", "=sum(a1:a2)")
    s.insert_rows(1)
    assert s.get_raw("B2") == "=sum(A2:A3)"
    assert is_num(s.get("B2"), 3.0)


def test_structural_rewrite_keeps_whitespace():
    s = Sheet()
    s.set("A1", "1")
    s.set("B5", "=1 +  a1  * 2")
    s.insert_rows(1)
    assert s.get_raw("B6") == "=1 +  A2  * 2"
    assert is_num(s.get("B6"), 3.0)


def test_structural_rewrite_dollar_lowercase():
    s = Sheet()
    s.set("C5", "=$a$1+1")
    s.insert_rows(1)
    assert s.get_raw("C6") == "=$A$2+1"


def test_structural_ref_token_from_lowercase():
    s = Sheet()
    s.set("C5", "=a2*2")
    s.delete_rows(2)
    assert s.get_raw("C4") == "=#REF!*2"


def test_copy_rewrite_canonical_and_untouched_absolute():
    s = Sheet()
    s.set("B1", "=$a$1+a1")
    s.copy("B1", "B2")
    assert s.get_raw("B2") == "=$a$1+A2"


def test_copy_rewrite_lowercase_range():
    s = Sheet()
    s.set("C1", "=sum(a1:b1)")
    s.copy("C1", "D1")
    assert s.get_raw("D1") == "=sum(B1:C1)"


# --- 8. truthiness ------------------------------------------------------------------------------------

@pytest.mark.parametrize(
    "formula,expected",
    [
        ('=IF(1,"y","n")', "y"),
        ('=IF(0,"y","n")', "n"),
        ('=IF(-0.5,"y","n")', "y"),
        ('=IF("true","y","n")', "y"),
        ('=IF("FALSE","y","n")', "n"),
    ],
)
def test_if_condition_truthiness(formula, expected):
    assert value_of(formula) == expected


def test_if_empty_condition_is_false():
    s = Sheet()
    s.set("B1", '=IF(A1,"y","n")')
    assert s.get("B1") == "n"


def test_if_text_cell_true_condition():
    s = Sheet()
    s.set("A1", "'TRUE")
    s.set("B1", '=IF(A1,"y","n")')
    assert s.get("B1") == "y"


def test_if_other_text_condition_is_value_error():
    assert is_err(value_of('=IF("abc",1,2)'), "#VALUE!")


@pytest.mark.parametrize(
    "formula,expected",
    [
        ("=AND(1,2)", True),
        ("=AND(1,0)", False),
        ("=OR(0,0)", False),
        ("=OR(0,3)", True),
        ("=NOT(0)", True),
        ("=NOT(2)", False),
        ('=NOT("TRUE")', False),
    ],
)
def test_logical_truthiness(formula, expected):
    assert value_of(formula) is expected


def test_not_other_text_is_value_error():
    assert is_err(value_of('=NOT("x")'), "#VALUE!")


def test_and_range_skips_text_and_empty():
    s = Sheet()
    s.set("A1", "TRUE")
    s.set("A2", "x")
    s.set("B1", "=AND(A1:A3)")
    assert s.get("B1") is True


def test_and_range_numbers():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "0")
    s.set("B1", "=AND(A1:A2)")
    assert s.get("B1") is False


def test_or_range_with_only_text_and_empty_is_value_error():
    s = Sheet()
    s.set("A1", "x")
    s.set("B1", "=OR(A1:A3)")
    assert is_err(s.get("B1"), "#VALUE!")


# --- 9. non-finite / non-real results, 0^0 --------------------------------------------------------------

@pytest.mark.parametrize(
    "formula",
    [
        "=10^400",
        "=(-8)^(1/3)",
        "=-1^0.5",
        "=1E308*10",
        "=1E308+1E308",
        "=SUM(1E308,1E308)",
    ],
)
def test_non_finite_or_complex_is_value_error(formula):
    assert is_err(value_of(formula), "#VALUE!")


def test_zero_to_negative_power_is_div0():
    assert is_err(value_of("=0^-1"), "#DIV/0!")


def test_zero_to_zero_is_one():
    assert is_num(value_of("=0^0"), 1.0)


# --- 10. ="" is empty text --------------------------------------------------------------------------------

def test_empty_string_formula_is_str():
    v = value_of('=""')
    assert type(v) is str
    assert v == ""


def test_empty_text_cell_in_arithmetic_is_value_error():
    s = Sheet()
    s.set("A1", '=""')
    s.set("B1", "=A1+1")
    assert is_err(s.get("B1"), "#VALUE!")


# --- 11. same raw / clearing empty --------------------------------------------------------------------------

def test_same_raw_literal_returns_empty():
    s = Sheet()
    s.set("A1", "5")
    assert s.set("A1", "5") == []


def test_same_raw_formula_with_dependents_returns_empty():
    s = Sheet()
    s.set("A1", "=1/0")
    s.set("B1", "=A1+1")
    assert s.set("A1", "=1/0") == []


def test_clearing_empty_cell_returns_empty():
    s = Sheet()
    assert s.set("A1", "") == []


# --- 12. copy destination outside the grid -----------------------------------------------------------------

def test_copy_block_past_last_column_raises():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "2")
    with pytest.raises(ValueError):
        s.copy("A1:B1", "XFD5")
    assert s.get("XFD5") is None
    assert s.get_raw("XFD5") == ""


def test_copy_block_past_last_row_raises():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "2")
    s.set("A1048576", "x")
    with pytest.raises(ValueError):
        s.copy("A1:A2", "A1048576")
    assert s.get("A1048576") == "x"
