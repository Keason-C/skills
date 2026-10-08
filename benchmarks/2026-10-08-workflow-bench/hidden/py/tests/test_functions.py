"""Built-in functions (brief-determined behaviour only)."""

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


def mixed_column():
    """A1=1, A2='x', A3=TRUE, A4 empty, A5=2.5"""
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "x")
    s.set("A3", "TRUE")
    s.set("A5", "2.5")
    return s


# --- SUM --------------------------------------------------------------------------

def test_sum_range():
    s = Sheet()
    for i, v in enumerate(["1", "2", "3"], start=1):
        s.set(f"A{i}", v)
    s.set("B1", "=SUM(A1:A3)")
    assert is_num(s.get("B1"), 6.0)


def test_sum_range_and_scalars():
    s = Sheet()
    for i, v in enumerate(["1", "2", "3"], start=1):
        s.set(f"A{i}", v)
    s.set("B1", "=SUM(A1:A3,10,0.5)")
    assert is_num(s.get("B1"), 16.5)


def test_sum_skips_text_bool_empty_in_range():
    s = mixed_column()
    s.set("B1", "=SUM(A1:A5)")
    assert is_num(s.get("B1"), 3.5)


def test_sum_coerces_scalar_booleans():
    assert is_num(value_of("=SUM(TRUE,2)"), 3.0)


def test_sum_scalar_non_numeric_text_is_value_error():
    assert is_err(value_of('=SUM("abc",1)'), "#VALUE!")


def test_sum_propagates_error_in_range():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "=1/0")
    s.set("A3", "3")
    s.set("B1", "=SUM(A1:A3)")
    assert is_err(s.get("B1"), "#DIV/0!")


def test_sum_propagates_error_in_scalar_arg():
    assert is_err(value_of("=SUM(1,1/0)"), "#DIV/0!")


def test_sum_of_empty_range_is_zero():
    s = Sheet()
    s.set("B1", "=SUM(A1:A3)")
    assert is_num(s.get("B1"), 0.0)


def test_sum_2d_range():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "2")
    s.set("A2", "3")
    s.set("B2", "4")
    s.set("D1", "=SUM(A1:B2)")
    assert is_num(s.get("D1"), 10.0)


def test_sum_reversed_range_is_normalised():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "2")
    s.set("A2", "3")
    s.set("B2", "4")
    s.set("D1", "=SUM(B2:A1)")
    assert is_num(s.get("D1"), 10.0)


def test_sum_anti_diagonal_corners_normalised():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", "2")
    s.set("A3", "5")
    s.set("B3", "7")
    s.set("D1", "=SUM(B1:A3)")
    assert is_num(s.get("D1"), 15.0)


# --- AVERAGE -------------------------------------------------------------------------

def test_average_skips_text_and_empty():
    s = Sheet()
    s.set("A1", "2")
    s.set("A2", "4")
    s.set("A3", "x")
    s.set("B1", "=AVERAGE(A1:A4)")
    assert is_num(s.get("B1"), 3.0)


def test_average_with_scalar():
    s = Sheet()
    s.set("A1", "2")
    s.set("A2", "4")
    s.set("B1", "=AVERAGE(A1:A2,9)")
    assert is_num(s.get("B1"), 5.0)


def test_average_of_empty_range_is_div0():
    s = Sheet()
    s.set("B1", "=AVERAGE(A1:A3)")
    assert is_err(s.get("B1"), "#DIV/0!")


def test_average_of_text_only_range_is_div0():
    s = Sheet()
    s.set("A1", "x")
    s.set("A2", "TRUE")
    s.set("B1", "=AVERAGE(A1:A2)")
    assert is_err(s.get("B1"), "#DIV/0!")


def test_average_scalar_booleans_coerced():
    assert is_num(value_of("=AVERAGE(TRUE,3)"), 2.0)


# --- MIN / MAX ---------------------------------------------------------------------------

def test_min_scalars():
    assert is_num(value_of("=MIN(3,1,2)"), 1.0)


def test_max_scalars():
    assert is_num(value_of("=MAX(3,1,2)"), 3.0)


def test_max_all_negative_range_ignores_empty():
    s = Sheet()
    s.set("A1", "-5")
    s.set("A2", "-2")
    s.set("B1", "=MAX(A1:A3)")
    assert is_num(s.get("B1"), -2.0)


def test_min_of_empty_range_is_zero():
    s = Sheet()
    s.set("B1", "=MIN(A1:A3)")
    assert is_num(s.get("B1"), 0.0)


def test_max_of_text_only_range_is_zero():
    s = Sheet()
    s.set("A1", "abc")
    s.set("B1", "=MAX(A1:A2)")
    assert is_num(s.get("B1"), 0.0)


def test_max_skips_booleans_in_range():
    s = Sheet()
    s.set("A1", "TRUE")
    s.set("A2", "-3")
    s.set("B1", "=MAX(A1:A2)")
    assert is_num(s.get("B1"), -3.0)


def test_min_coerces_scalar_boolean():
    assert is_num(value_of("=MIN(TRUE,5)"), 1.0)


def test_min_propagates_error_in_range():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "=1/0")
    s.set("B1", "=MIN(A1:A2)")
    assert is_err(s.get("B1"), "#DIV/0!")


# --- COUNT -----------------------------------------------------------------------------

def test_count_numbers_only_in_range():
    s = mixed_column()
    s.set("B1", "=COUNT(A1:A5)")
    assert is_num(s.get("B1"), 2.0)


def test_count_scalar_args_numbers_and_booleans():
    s = Sheet()
    s.set("A1", "7")
    s.set("A2", "y")
    s.set("B1", "=COUNT(1,TRUE,A1:A2)")
    assert is_num(s.get("B1"), 3.0)


def test_count_of_empty_range_is_zero():
    s = Sheet()
    s.set("B1", "=COUNT(A1:A3)")
    assert is_num(s.get("B1"), 0.0)


def test_count_propagates_error_in_range():
    s = Sheet()
    s.set("A1", "1")
    s.set("A2", "=1/0")
    s.set("B1", "=COUNT(A1:A2)")
    assert is_err(s.get("B1"), "#DIV/0!")


# --- IF -------------------------------------------------------------------------------------

def test_if_true_branch():
    assert is_num(value_of("=IF(TRUE,1,2)"), 1.0)


def test_if_false_branch():
    assert is_num(value_of("=IF(FALSE,1,2)"), 2.0)


def test_if_missing_else_is_false():
    assert value_of("=IF(FALSE,1)") is False


def test_if_missing_else_true_branch():
    assert value_of('=IF(TRUE,"yes")') == "yes"


def test_if_lazy_else_not_evaluated():
    assert is_num(value_of("=IF(TRUE,1,1/0)"), 1.0)


def test_if_lazy_then_not_evaluated():
    assert is_num(value_of("=IF(FALSE,1/0,2)"), 2.0)


def test_if_comparison_condition():
    s = Sheet()
    s.set("A1", "1")
    s.set("B1", '=IF(A1>2,"big","small")')
    assert s.get("B1") == "small"


def test_if_error_condition_propagates():
    assert is_err(value_of("=IF(1/0,1,2)"), "#DIV/0!")


def test_if_chosen_branch_error_propagates():
    assert is_err(value_of("=IF(TRUE,1/0,1)"), "#DIV/0!")


# --- AND / OR / NOT ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [
        ("=AND(TRUE,TRUE)", True),
        ("=AND(TRUE,FALSE)", False),
        ("=OR(FALSE,FALSE)", False),
        ("=OR(FALSE,TRUE)", True),
        ("=NOT(TRUE)", False),
        ("=NOT(1>2)", True),
        ("=AND(1<2,2<3,3<4)", True),
    ],
)
def test_logical_functions(raw, expected):
    assert value_of(raw) is expected


def test_and_over_boolean_range():
    s = Sheet()
    s.set("A1", "TRUE")
    s.set("A2", "TRUE")
    s.set("A3", "FALSE")
    s.set("B1", "=AND(A1:A3)")
    assert s.get("B1") is False


def test_or_over_boolean_range():
    s = Sheet()
    s.set("A1", "FALSE")
    s.set("A2", "TRUE")
    s.set("A3", "FALSE")
    s.set("B1", "=OR(A1:A3)")
    assert s.get("B1") is True


def test_and_propagates_error():
    assert is_err(value_of("=AND(TRUE,1/0)"), "#DIV/0!")


def test_not_propagates_error():
    assert is_err(value_of("=NOT(1/0)"), "#DIV/0!")


# --- IFERROR -----------------------------------------------------------------------------------

def test_iferror_returns_fallback_on_error():
    assert value_of('=IFERROR(1/0,"x")') == "x"


def test_iferror_returns_value_when_not_error():
    assert is_num(value_of('=IFERROR(5,"x")'), 5.0)


def test_iferror_fallback_lazy():
    assert is_num(value_of("=IFERROR(1,1/0)"), 1.0)


def test_iferror_catches_name_error():
    assert is_num(value_of("=IFERROR(NOSUCHFUNC(1),2)"), 2.0)


def test_iferror_catches_error_from_reference():
    s = Sheet()
    s.set("A1", "=1/0")
    s.set("B1", "=IFERROR(A1,0)")
    assert is_num(s.get("B1"), 0.0)


# --- ROUND / ABS / LEN / CONCAT ----------------------------------------------------------------

def test_round_two_digits():
    assert is_num(value_of("=ROUND(3.14159,2)"), 3.14)


def test_round_negative_number():
    assert is_num(value_of("=ROUND(-3.7,0)"), -4.0)


def test_round_one_digit():
    assert is_num(value_of("=ROUND(1234.5678,1)"), 1234.6)


def test_abs_negative():
    assert is_num(value_of("=ABS(-3)"), 3.0)


def test_abs_positive_fraction():
    assert is_num(value_of("=ABS(2.5)"), 2.5)


def test_len_text():
    v = value_of('=LEN("hello")')
    assert type(v) is float
    assert v == 5.0


def test_len_with_escaped_quotes():
    assert is_num(value_of('=LEN("say ""hi""")'), 8.0)


def test_len_of_empty_string_literal():
    assert is_num(value_of('=LEN("")'), 0.0)


def test_concat_scalars():
    assert value_of('=CONCAT("a","b","c")') == "abc"


def test_concat_range_row_major():
    s = Sheet()
    s.set("A1", "a")
    s.set("B1", "b")
    s.set("A2", "c")
    s.set("B2", "d")
    s.set("D1", "=CONCAT(A1:B2)")
    assert s.get("D1") == "abcd"


def test_concat_ranges_and_scalars():
    s = Sheet()
    s.set("A1", "a")
    s.set("B1", "b")
    s.set("A2", "c")
    s.set("B2", "d")
    s.set("D1", '=CONCAT(A1:B1,"-",A2:B2)')
    assert s.get("D1") == "ab-cd"


def test_concat_range_with_empty_cell():
    s = Sheet()
    s.set("A1", "a")
    s.set("A2", "c")
    s.set("B2", "d")
    s.set("D1", "=CONCAT(A1:B2)")
    assert s.get("D1") == "acd"


# --- composition -------------------------------------------------------------------------------

def test_nested_functions():
    assert is_num(value_of("=SUM(1,MAX(2,3),ABS(-4))"), 8.0)


def test_count_result_is_float():
    v = value_of("=COUNT(1,2)")
    assert type(v) is float
    assert v == 2.0
