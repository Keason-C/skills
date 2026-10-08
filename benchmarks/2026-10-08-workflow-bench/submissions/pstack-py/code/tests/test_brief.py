import time

import pytest

from gridcalc import CellError, Sheet


def E(code):
    return CellError(code)


def is_num(value, expected):
    return type(value) is float and value == expected


def close(value, expected):
    return type(value) is float and abs(value - expected) < 1e-9


def sheet_with(**cells):
    s = Sheet()
    for addr, raw in cells.items():
        s.set(addr, raw)
    return s


def test_address_lowercase_set_and_get_same_cell():
    s = Sheet()
    s.set("b3", "5")
    assert is_num(s.get("B3"), 5.0)
    assert is_num(s.get("b3"), 5.0)


def test_address_returned_in_uppercase():
    s = Sheet()
    assert s.set("b3", "5") == ["B3"]


def test_address_mixed_case_multi_letter_column():
    s = Sheet()
    s.set("aA10", "7")
    assert is_num(s.get("AA10"), 7.0)


def test_address_get_raw_case_insensitive():
    s = Sheet()
    s.set("C2", "hi")
    assert s.get_raw("c2") == "hi"


def test_address_last_cell_of_grid_is_valid():
    s = Sheet()
    assert s.get("XFD1048576") is None
    s.set("XFD1048576", "1")
    assert is_num(s.get("XFD1048576"), 1.0)


@pytest.mark.parametrize(
    "bad",
    ["", "A", "1", "A0", "1A", "A1B", "A-1", "XFE1", "A1048577", "AAAA1", "A 1", "$A$1:B2", "A1:B2"],
)
def test_address_malformed_or_off_grid_get_raises_value_error(bad):
    s = Sheet()
    with pytest.raises(ValueError):
        s.get(bad)


@pytest.mark.parametrize("bad", ["A0", "XFE1", "A1048577", "foo", ""])
def test_address_malformed_set_raises_value_error(bad):
    s = Sheet()
    with pytest.raises(ValueError):
        s.set(bad, "1")


@pytest.mark.parametrize("bad", ["A0", "XFE1", "?"])
def test_address_malformed_get_raw_raises_value_error(bad):
    s = Sheet()
    with pytest.raises(ValueError):
        s.get_raw(bad)


def test_address_bijective_base26_z_then_aa():
    s = sheet_with(Z1="1", AA1="2", AZ1="3", BA1="4")
    s.set("A2", "=Z1+AA1*10+AZ1*100+BA1*1000")
    assert is_num(s.get("A2"), 4321.0)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("42", 42.0),
        ("0", 0.0),
        ("2.5", 2.5),
        (".5", 0.5),
        ("-.5", -0.5),
        ("1e3", 1000.0),
        ("1E3", 1000.0),
        ("-2.5E-2", -0.025),
        ("+3", 3.0),
        ("-7", -7.0),
        ("  7  ", 7.0),
        ("\t3.5\n", 3.5),
    ],
)
def test_literal_number_parses_to_float(raw, expected):
    s = Sheet()
    s.set("A1", raw)
    assert is_num(s.get("A1"), expected)


def test_literal_number_get_raw_keeps_surrounding_whitespace():
    s = Sheet()
    s.set("A1", "  7  ")
    assert s.get_raw("A1") == "  7  "


def test_literal_apostrophe_forces_text():
    s = Sheet()
    s.set("A1", "'123")
    assert s.get("A1") == "123"
    assert type(s.get("A1")) is str


def test_literal_apostrophe_get_raw_keeps_apostrophe():
    s = Sheet()
    s.set("A1", "'123")
    assert s.get_raw("A1") == "'123"


def test_literal_apostrophe_before_true_is_text():
    s = Sheet()
    s.set("A1", "'TRUE")
    assert s.get("A1") == "TRUE"


def test_literal_apostrophe_before_equals_is_text():
    s = Sheet()
    s.set("A1", "'=1+1")
    assert s.get("A1") == "=1+1"


@pytest.mark.parametrize("raw", ["TRUE", "true", "True", "tRuE"])
def test_literal_true_any_case(raw):
    s = Sheet()
    s.set("A1", raw)
    assert s.get("A1") is True


@pytest.mark.parametrize("raw", ["FALSE", "false", "False"])
def test_literal_false_any_case(raw):
    s = Sheet()
    s.set("A1", raw)
    assert s.get("A1") is False


@pytest.mark.parametrize("raw", ["abc", "12abc", "1e", "1,000", "TRUEX", "--1", "e3", "1.2.3", "A1"])
def test_literal_non_number_is_text(raw):
    s = Sheet()
    s.set("A1", raw)
    assert s.get("A1") == raw


def test_literal_text_is_not_stripped():
    s = Sheet()
    s.set("A1", "  hello  ")
    assert s.get("A1") == "  hello  "
    assert s.get_raw("A1") == "  hello  "


def test_literal_empty_string_clears_cell():
    s = sheet_with(A1="5")
    s.set("A1", "")
    assert s.get("A1") is None
    assert s.get_raw("A1") == ""


def test_unset_cell_is_none_and_empty_raw():
    s = Sheet()
    assert s.get("D4") is None
    assert s.get_raw("D4") == ""


def test_get_formula_integer_result_is_float():
    s = sheet_with(A1="=1+1")
    v = s.get("A1")
    assert type(v) is float and v == 2.0


def test_get_formula_text_result():
    s = sheet_with(A1='="hello"')
    assert s.get("A1") == "hello"


def test_get_formula_boolean_result():
    s = sheet_with(A1="=TRUE", A2="=false")
    assert s.get("A1") is True
    assert s.get("A2") is False


def test_get_error_is_cellerror_with_code():
    s = sheet_with(A1="=1/0")
    v = s.get("A1")
    assert isinstance(v, CellError)
    assert v.code == "#DIV/0!"


def test_get_raw_formula_returned_exactly():
    s = sheet_with(A1="=  1 +   2")
    assert s.get_raw("A1") == "=  1 +   2"


def test_formula_whitespace_between_tokens_allowed():
    s = sheet_with(A1="= 1 + 2 * 3")
    assert is_num(s.get("A1"), 7.0)


def test_formula_reference_to_number_cell_is_float():
    s = sheet_with(A1="3", B1="=A1")
    assert is_num(s.get("B1"), 3.0)


def test_formula_reference_to_text_cell_is_text():
    s = sheet_with(A1="abc", B1="=A1")
    assert s.get("B1") == "abc"


def test_set_returns_own_address_when_value_changes():
    s = Sheet()
    assert s.set("A1", "1") == ["A1"]


def test_set_returns_dependents_that_change():
    s = sheet_with(A1="1", B1="=A1*2")
    assert s.set("A1", "2") == ["A1", "B1"]


def test_set_same_value_returns_empty():
    s = sheet_with(A1="1")
    assert s.set("A1", "1") == []


def test_set_raw_change_same_value_not_reported():
    s = sheet_with(A1="1")
    assert s.set("A1", "=1") == []


def test_set_raw_change_same_value_whitespace_number_not_reported():
    s = sheet_with(A1="5")
    assert s.set("A1", " 5 ") == []


def test_set_float_vs_true_is_a_change():
    s = sheet_with(A1="1")
    assert s.set("A1", "TRUE") == ["A1"]


def test_set_true_vs_float_is_a_change():
    s = sheet_with(A1="TRUE")
    assert s.set("A1", "=1") == ["A1"]


def test_set_number_vs_numeric_text_is_a_change():
    s = sheet_with(A1="1")
    assert s.set("A1", "'1") == ["A1"]


def test_set_same_error_code_is_not_a_change():
    s = sheet_with(A1="=1/0")
    assert s.set("A1", "=2/0") == []


def test_set_different_error_code_is_a_change():
    s = sheet_with(A1="=1/0")
    assert s.set("A1", "=NOSUCHFN()") == ["A1"]


def test_set_dependent_with_unchanged_value_not_reported():
    s = sheet_with(A1="1", B1="=A1>0")
    assert s.set("A1", "2") == ["A1"]


def test_set_sorted_by_row_then_column_not_lexicographic():
    s = Sheet()
    s.set("A2", "1")
    s.set("C1", "=A2")
    s.set("B1", "=A2")
    s.set("AA2", "=A2")
    s.set("B2", "=A2")
    s.set("A10", "=A2")
    s.set("A9", "=A2")
    assert s.set("A2", "5") == ["B1", "C1", "A2", "B2", "AA2", "A9", "A10"]


def test_set_diamond_dependents_no_duplicates():
    s = sheet_with(A1="1", B1="=A1+1", C1="=A1+2", D1="=B1+C1")
    assert s.set("A1", "10") == ["A1", "B1", "C1", "D1"]
    assert is_num(s.get("D1"), 23.0)


def test_set_transitive_dependents_reported():
    s = sheet_with(A1="1", A2="=A1+1", A3="=A2+1")
    assert s.set("A1", "5") == ["A1", "A2", "A3"]
    assert is_num(s.get("A3"), 7.0)


def test_set_clear_cell_reports_change():
    s = sheet_with(A1="5", B1="=A1+1")
    assert s.set("A1", "") == ["A1", "B1"]
    assert is_num(s.get("B1"), 1.0)


def test_set_clear_empty_cell_returns_empty():
    s = Sheet()
    assert s.set("A1", "") == []


def test_set_same_text_returns_empty():
    s = sheet_with(A1="abc")
    assert s.set("A1", "abc") == []


def test_set_returns_list_type():
    s = Sheet()
    assert isinstance(s.set("A1", "1"), list)


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("=1+2*3", 7.0),
        ("=(1+2)*3", 9.0),
        ("=10-3-2", 5.0),
        ("=12/3/2", 2.0),
        ("=2^3^2", 64.0),
        ("=-2^2", 4.0),
        ("=-(2^2)", -4.0),
        ("=2*3^2", 18.0),
        ("=2^-1", 0.5),
        ("=2*-3", -6.0),
        ("=--3", 3.0),
        ("=+5", 5.0),
        ("=3-(-2)", 5.0),
        ("=10/4", 2.5),
        ("=1-2+3", 2.0),
        ("=2+3^2*2", 20.0),
        ("=.5+1e3", 1000.5),
    ],
)
def test_operator_arithmetic_precedence(formula, expected):
    s = sheet_with(A1=formula)
    assert is_num(s.get("A1"), expected)


def test_operator_comparison_lower_than_addition():
    s = sheet_with(A1="=1+1=2")
    assert s.get("A1") is True


def test_operator_concat_higher_than_comparison():
    s = sheet_with(A1='="x"&"y"="xy"')
    assert s.get("A1") is True


def test_operator_concat_lower_than_addition():
    s = sheet_with(A1="=1+2&3+4")
    assert s.get("A1") == "37"


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("=1<2", True),
        ("=2<1", False),
        ("=2>1", True),
        ("=2=2", True),
        ("=1<>1", False),
        ("=1<>2", True),
        ("=3>=3", True),
        ("=2<=1", False),
        ('="a"="a"', True),
        ('="a"<>"b"', True),
    ],
)
def test_operator_comparison_returns_bool(formula, expected):
    s = sheet_with(A1=formula)
    assert s.get("A1") is expected


def test_operator_concat_strings():
    s = sheet_with(A1='="ab"&"cd"&"e"')
    assert s.get("A1") == "abcde"


def test_operator_concat_integer_number():
    s = sheet_with(A1='="n"&5')
    assert s.get("A1") == "n5"


def test_operator_parentheses_nesting_200():
    s = sheet_with(A1="=" + "(" * 200 + "1" + ")" * 200)
    assert is_num(s.get("A1"), 1.0)


def test_operator_parentheses_nesting_200_with_arithmetic():
    s = sheet_with(A1="=" + "(1+" * 200 + "0" + ")" * 200)
    assert is_num(s.get("A1"), 200.0)


def test_divide_by_zero():
    s = sheet_with(A1="=1/0")
    assert s.get("A1") == E("#DIV/0!")


def test_divide_by_empty_cell():
    s = sheet_with(A1="=1/B1")
    assert s.get("A1") == E("#DIV/0!")


def test_string_escaped_quotes():
    s = sheet_with(A1='="say ""hi"""')
    assert s.get("A1") == 'say "hi"'


def test_string_empty_literal():
    s = sheet_with(A1='=""')
    assert s.get("A1") == ""


def test_string_only_escaped_quote():
    s = sheet_with(A1='=""""')
    assert s.get("A1") == '"'


def test_string_containing_reference_like_text():
    s = sheet_with(A1='="A1+B2"')
    assert s.get("A1") == "A1+B2"


def test_coercion_empty_is_zero_in_arithmetic():
    s = sheet_with(A1="=B1+1")
    assert is_num(s.get("A1"), 1.0)


def test_coercion_true_false_in_arithmetic():
    s = sheet_with(A1="=TRUE+1", A2="=FALSE*5+2")
    assert is_num(s.get("A1"), 2.0)
    assert is_num(s.get("A2"), 2.0)


def test_coercion_boolean_cell_in_arithmetic():
    s = sheet_with(B1="TRUE", A1="=B1*10")
    assert is_num(s.get("A1"), 10.0)


def test_coercion_numeric_text_in_arithmetic():
    s = sheet_with(A1='="3"+1', A2='="2"*"4"')
    assert is_num(s.get("A1"), 4.0)
    assert is_num(s.get("A2"), 8.0)


def test_coercion_numeric_text_cell_in_arithmetic():
    s = sheet_with(B1="'3", A1="=B1+1")
    assert is_num(s.get("A1"), 4.0)


def test_coercion_non_numeric_text_is_value_error():
    s = sheet_with(A1='="abc"+1')
    assert s.get("A1") == E("#VALUE!")


def test_coercion_non_numeric_text_cell_is_value_error():
    s = sheet_with(B1="abc", A1="=-B1")
    assert s.get("A1") == E("#VALUE!")


def test_coercion_empty_in_concat_is_empty_string():
    s = sheet_with(A1='=B1&"x"&C1')
    assert s.get("A1") == "x"


def test_coercion_booleans_in_concat():
    s = sheet_with(A1='=TRUE&"/"&FALSE')
    assert s.get("A1") == "TRUE/FALSE"


def test_coercion_boolean_cell_in_concat():
    s = sheet_with(B1="true", A1='=B1&""')
    assert s.get("A1") == "TRUE"


def test_sum_scalars():
    s = sheet_with(A1="=SUM(1,2,3)")
    assert is_num(s.get("A1"), 6.0)


def test_sum_single_argument():
    s = sheet_with(A1="=SUM(4)")
    assert is_num(s.get("A1"), 4.0)


def test_sum_range():
    s = sheet_with(A1="1", A2="2", A3="3", B1="=SUM(A1:A3)")
    assert is_num(s.get("B1"), 6.0)


def test_sum_2d_range():
    s = sheet_with(A1="1", B1="2", A2="3", B2="4", C1="=SUM(A1:B2)")
    assert is_num(s.get("C1"), 10.0)


def test_sum_reversed_range_normalised():
    s = sheet_with(A1="1", B1="2", A2="3", B2="4", C1="=SUM(B2:A1)")
    assert is_num(s.get("C1"), 10.0)


def test_sum_range_with_dollar_endpoints():
    s = sheet_with(A1="1", A2="2", B1="=SUM($A$1:A$2)")
    assert is_num(s.get("B1"), 3.0)


def test_sum_range_skips_text_booleans_and_empty():
    s = sheet_with(A1="5", A2="'10", A3="TRUE", A5="abc", A6="2", B1="=SUM(A1:A6)")
    assert is_num(s.get("B1"), 7.0)


def test_sum_scalar_boolean_is_coerced():
    s = sheet_with(A1="=SUM(TRUE,2)")
    assert is_num(s.get("A1"), 3.0)


def test_sum_scalar_numeric_text_is_coerced():
    s = sheet_with(A1='=SUM("3",1)')
    assert is_num(s.get("A1"), 4.0)


def test_sum_scalar_non_numeric_text_is_value_error():
    s = sheet_with(A1='=SUM("x",1)')
    assert s.get("A1") == E("#VALUE!")


def test_sum_mixed_ranges_and_scalars():
    s = sheet_with(A1="1", A2="2", B1="10", C1="=SUM(A1:A2,5,B1:B1)")
    assert is_num(s.get("C1"), 18.0)


def test_sum_error_in_range_propagates():
    s = sheet_with(A1="1", A2="=1/0", A3="3", B1="=SUM(A1:A3)")
    assert s.get("B1") == E("#DIV/0!")


def test_sum_error_scalar_propagates():
    s = sheet_with(A1="=SUM(1,1/0)")
    assert s.get("A1") == E("#DIV/0!")


def test_average_scalars():
    s = sheet_with(A1="=AVERAGE(2,4)")
    assert is_num(s.get("A1"), 3.0)


def test_average_range_skips_non_numbers():
    s = sheet_with(A1="1", A2="text", A3="5", A4="TRUE", B1="=AVERAGE(A1:A5)")
    assert is_num(s.get("B1"), 3.0)


def test_average_empty_range_is_div0():
    s = sheet_with(B1="=AVERAGE(A1:A3)")
    assert s.get("B1") == E("#DIV/0!")


def test_average_all_text_range_is_div0():
    s = sheet_with(A1="a", A2="b", B1="=AVERAGE(A1:A2)")
    assert s.get("B1") == E("#DIV/0!")


def test_average_error_in_range_propagates():
    s = sheet_with(A1="=1/0", B1="=AVERAGE(A1:A2)")
    assert s.get("B1") == E("#DIV/0!")


def test_min_max_scalars():
    s = sheet_with(A1="=MIN(3,1,2)", A2="=MAX(3,1,2)", A3="=MAX(-5,-2)")
    assert is_num(s.get("A1"), 1.0)
    assert is_num(s.get("A2"), 3.0)
    assert is_num(s.get("A3"), -2.0)


def test_min_max_range_skips_non_numbers():
    s = sheet_with(A1="TRUE", A2="5", A3="'100", A4="7", B1="=MAX(A1:A4)", B2="=MIN(A1:A4)")
    assert is_num(s.get("B1"), 7.0)
    assert is_num(s.get("B2"), 5.0)


def test_min_empty_range_is_zero():
    s = sheet_with(B1="=MIN(A1:A3)")
    assert is_num(s.get("B1"), 0.0)


def test_max_all_text_range_is_zero():
    s = sheet_with(A1="x", A2="y", B1="=MAX(A1:A2)")
    assert is_num(s.get("B1"), 0.0)


def test_max_error_in_range_propagates():
    s = sheet_with(A1="1", A2='="a"+1', B1="=MAX(A1:A2)")
    assert s.get("B1") == E("#VALUE!")


def test_count_range_counts_numbers_only():
    s = sheet_with(A1="1", A2="text", A3="TRUE", A5="=2+2", A6="'7", B1="=COUNT(A1:A6)")
    assert is_num(s.get("B1"), 2.0)


def test_count_empty_range_is_zero():
    s = sheet_with(B1="=COUNT(A1:A3)")
    assert is_num(s.get("B1"), 0.0)


def test_count_scalar_numbers():
    s = sheet_with(A1="=COUNT(1,2,3)")
    assert is_num(s.get("A1"), 3.0)


def test_count_scalar_coercible_text_counts():
    s = sheet_with(A1='=COUNT("3")')
    assert is_num(s.get("A1"), 1.0)


def test_count_scalar_non_coercible_text_not_counted():
    s = sheet_with(A1='=COUNT(1,"x")')
    assert is_num(s.get("A1"), 1.0)


def test_count_error_in_range_propagates():
    s = sheet_with(A1="1", A2="=1/0", B1="=COUNT(A1:A2)")
    assert s.get("B1") == E("#DIV/0!")


def test_if_true_branch():
    s = sheet_with(A1='=IF(TRUE,1,2)')
    assert is_num(s.get("A1"), 1.0)


def test_if_false_branch():
    s = sheet_with(A1='=IF(1>2,"y","n")')
    assert s.get("A1") == "n"


def test_if_missing_else_is_false():
    s = sheet_with(A1='=IF(FALSE,1)', A2='=IF(1>2,"y")')
    assert s.get("A1") is False
    assert s.get("A2") is False


def test_if_only_chosen_branch_evaluated_then():
    s = sheet_with(A1="=IF(TRUE,1,1/0)")
    assert is_num(s.get("A1"), 1.0)


def test_if_only_chosen_branch_evaluated_else():
    s = sheet_with(A1='=IF(FALSE,"a"+1,2)')
    assert is_num(s.get("A1"), 2.0)


def test_if_unchosen_range_branch_not_evaluated():
    s = sheet_with(A1="=IF(TRUE,5,B1:B3)")
    assert is_num(s.get("A1"), 5.0)


def test_if_error_condition_propagates():
    s = sheet_with(A1="=IF(1/0,1,2)")
    assert s.get("A1") == E("#DIV/0!")


def test_if_condition_from_cell():
    s = sheet_with(B1="5", A1='=IF(B1>3,"big","small")')
    assert s.get("A1") == "big"
    s.set("B1", "1")
    assert s.get("A1") == "small"


def test_iferror_returns_fallback_on_error():
    s = sheet_with(A1='=IFERROR(1/0,"x")')
    assert s.get("A1") == "x"


def test_iferror_returns_value_when_not_error():
    s = sheet_with(A1='=IFERROR(5,"x")')
    assert is_num(s.get("A1"), 5.0)


def test_iferror_fallback_not_evaluated_when_value_ok():
    s = sheet_with(A1="=IFERROR(5,1/0)")
    assert is_num(s.get("A1"), 5.0)


def test_iferror_catches_error_from_cell():
    s = sheet_with(B1="=NOPE(1)", A1="=IFERROR(B1,0)")
    assert is_num(s.get("A1"), 0.0)


def test_and_or_scalars():
    s = sheet_with(
        A1="=AND(TRUE,FALSE)",
        A2="=AND(TRUE,TRUE)",
        A3="=OR(FALSE,TRUE)",
        A4="=OR(FALSE,FALSE)",
        A5="=AND(TRUE)",
        A6="=OR(1>2)",
    )
    assert s.get("A1") is False
    assert s.get("A2") is True
    assert s.get("A3") is True
    assert s.get("A4") is False
    assert s.get("A5") is True
    assert s.get("A6") is False


def test_and_or_boolean_ranges():
    s = sheet_with(B1="TRUE", B2="TRUE", B3="FALSE", A1="=AND(B1:B2)", A2="=AND(B1:B3)", A3="=OR(B3:B3)", A4="=OR(B2:B3)")
    assert s.get("A1") is True
    assert s.get("A2") is False
    assert s.get("A3") is False
    assert s.get("A4") is True


def test_and_error_propagates():
    s = sheet_with(A1="=AND(TRUE,1/0)")
    assert s.get("A1") == E("#DIV/0!")


def test_not():
    s = sheet_with(A1="=NOT(TRUE)", A2="=NOT(1>2)")
    assert s.get("A1") is False
    assert s.get("A2") is True


def test_not_error_propagates():
    s = sheet_with(A1="=NOT(1/0)")
    assert s.get("A1") == E("#DIV/0!")


def test_round_two_digits():
    s = sheet_with(A1="=ROUND(3.14159,2)", A2="=ROUND(-2.567,1)", A3="=ROUND(2.4,0)")
    assert close(s.get("A1"), 3.14)
    assert close(s.get("A2"), -2.6)
    assert is_num(s.get("A3"), 2.0)


def test_round_error_propagates():
    s = sheet_with(A1="=ROUND(1/0,1)")
    assert s.get("A1") == E("#DIV/0!")


def test_abs():
    s = sheet_with(A1="=ABS(-3)", A2="=ABS(2.5)")
    assert is_num(s.get("A1"), 3.0)
    assert is_num(s.get("A2"), 2.5)


def test_abs_error_propagates():
    s = sheet_with(A1="=ABS(1/0)")
    assert s.get("A1") == E("#DIV/0!")


def test_len():
    s = sheet_with(A1='=LEN("hello")', A2='=LEN("")', A3='=LEN("a""b")')
    assert is_num(s.get("A1"), 5.0)
    assert is_num(s.get("A2"), 0.0)
    assert is_num(s.get("A3"), 3.0)


def test_len_of_text_cell_keeps_whitespace():
    s = sheet_with(B1="  ab ", A1="=LEN(B1)")
    assert is_num(s.get("A1"), 5.0)


def test_concat_scalars():
    s = sheet_with(A1='=CONCAT("a","b","c")')
    assert s.get("A1") == "abc"


def test_concat_range_row_major():
    s = sheet_with(A1="a", B1="b", A2="c", B2="d", C1="=CONCAT(A1:B2)")
    assert s.get("C1") == "abcd"


def test_concat_range_and_scalar():
    s = sheet_with(A1="x", A2="y", C1='=CONCAT("<",A1:A2,">")')
    assert s.get("C1") == "<xy>"


@pytest.mark.parametrize(
    "formula",
    ["=A1:A3+1", '=A1:A2&"x"', "=ABS(A1:A2)", "=LEN(A1:A2)", "=IF(A1:A2,1,2)", "=ROUND(A1:A2,1)"],
)
def test_range_used_as_scalar_is_value_error(formula):
    s = sheet_with(A1="1", A2="2", A3="3", C1=formula)
    assert s.get("C1") == E("#VALUE!")


def test_error_unknown_function_is_name():
    s = sheet_with(A1="=FOO(1)")
    assert s.get("A1") == E("#NAME?")


def test_error_propagates_through_reference():
    s = sheet_with(A1="=1/0", B1="=A1+1", C1='=B1&"x"')
    assert s.get("B1") == E("#DIV/0!")
    assert s.get("C1") == E("#DIV/0!")


def test_error_leftmost_wins_div_first():
    s = sheet_with(A1="=1/0+FOO()")
    assert s.get("A1") == E("#DIV/0!")


def test_error_leftmost_wins_name_first():
    s = sheet_with(A1="=FOO()+1/0")
    assert s.get("A1") == E("#NAME?")


def test_error_leftmost_wins_in_concat():
    s = sheet_with(A1='=("a"+1)&(1/0)')
    assert s.get("A1") == E("#VALUE!")


def test_error_leftmost_wins_in_function_args():
    s = sheet_with(A1='=SUM("x",1/0)', A2='=SUM(1/0,"x")')
    assert s.get("A1") == E("#VALUE!")
    assert s.get("A2") == E("#DIV/0!")


def test_error_leftmost_wins_across_cells():
    s = sheet_with(B1="=1/0", C1="=ZZZ()", A1="=C1+B1", A2="=B1+C1")
    assert s.get("A1") == E("#NAME?")
    assert s.get("A2") == E("#DIV/0!")


def test_error_in_comparison_propagates():
    s = sheet_with(A1="=(1/0)=1")
    assert s.get("A1") == E("#DIV/0!")


@pytest.mark.parametrize("formula", ["=1+", "=(1", "=1)", "=", '="abc', "=1 2", "=SUM(1,", "=*3", "=A1:", "=1++"])
def test_error_unparseable_formula_is_parse(formula):
    s = Sheet()
    s.set("A1", formula)
    assert s.get("A1") == E("#PARSE!")


def test_error_parse_keeps_raw_text():
    s = Sheet()
    s.set("A1", "=1+")
    assert s.get_raw("A1") == "=1+"


def test_error_parse_propagates_to_dependents():
    s = sheet_with(A1="=(", B1="=A1+1")
    assert s.get("B1") == E("#PARSE!")


def test_cycle_self_reference():
    s = sheet_with(A1="=A1+1")
    assert s.get("A1") == E("#CYCLE!")


def test_cycle_two_cells():
    s = sheet_with(A1="=B1", B1="=A1")
    assert s.get("A1") == E("#CYCLE!")
    assert s.get("B1") == E("#CYCLE!")


def test_cycle_three_cells():
    s = sheet_with(A1="=B1+1", B1="=C1+1", C1="=A1+1")
    for a in ("A1", "B1", "C1"):
        assert s.get(a) == E("#CYCLE!")


def test_cycle_through_range():
    s = sheet_with(A1="1", A2="=SUM(A1:A3)")
    assert s.get("A2") == E("#CYCLE!")


def test_cycle_static_dependency_in_unchosen_if_branch():
    s = sheet_with(A1="=IF(TRUE,1,A1)")
    assert s.get("A1") == E("#CYCLE!")


def test_cycle_iferror_member_still_cycle():
    s = sheet_with(A1="=IFERROR(B1,0)", B1="=A1")
    assert s.get("A1") == E("#CYCLE!")
    assert s.get("B1") == E("#CYCLE!")


def test_cycle_downstream_gets_propagated_error():
    s = sheet_with(A1="=B1", B1="=A1", C1="=A1+1")
    assert s.get("C1") == E("#CYCLE!")


def test_cycle_downstream_iferror_catches_propagated_error():
    s = sheet_with(A1="=B1", B1="=A1", C1="=IFERROR(A1,7)")
    assert is_num(s.get("C1"), 7.0)


def test_cycle_formation_returns_changed_cells():
    s = sheet_with(A1="=B1+1", C1="=A1*2")
    assert s.set("B1", "=A1") == ["A1", "B1", "C1"]


def test_cycle_break_restores_values():
    s = sheet_with(A1="=B1+1", B1="=A1", C1="=A1*2")
    s.set("B1", "5")
    assert is_num(s.get("A1"), 6.0)
    assert is_num(s.get("B1"), 5.0)
    assert is_num(s.get("C1"), 12.0)


def test_cycle_break_by_editing_other_member():
    s = sheet_with(A1="=B1+1", B1="=C1+1", C1="=A1+1", D1="=C1")
    s.set("A1", "10")
    assert is_num(s.get("C1"), 11.0)
    assert is_num(s.get("B1"), 12.0)
    assert is_num(s.get("D1"), 11.0)


def test_cycle_break_by_clearing_member():
    s = sheet_with(A1="=B1+1", B1="=A1")
    s.set("B1", "")
    assert is_num(s.get("A1"), 1.0)


def test_cycle_break_self_reference_returns_changed():
    s = sheet_with(A1="=A1", B1="=A1&\"\"")
    assert s.set("A1", "x") == ["A1", "B1"]
    assert s.get("B1") == "x"


def test_cycle_non_member_depending_on_cycle_does_not_join():
    s = sheet_with(A1="=B1", B1="=A1", C1="=A1")
    s.set("A1", "3")
    assert is_num(s.get("C1"), 3.0)


def test_insert_rows_returns_none():
    s = sheet_with(A1="1")
    assert s.insert_rows(1) is None
    assert s.delete_rows(1) is None
    assert s.insert_cols(1) is None
    assert s.delete_cols(1) is None


def test_insert_rows_moves_cells():
    s = sheet_with(A1="5", A3="x")
    s.insert_rows(2)
    assert is_num(s.get("A1"), 5.0)
    assert s.get("A3") is None
    assert s.get("A4") == "x"


def test_insert_rows_shifts_reference():
    s = sheet_with(A1="5", B2="=A1*2")
    s.insert_rows(1)
    assert s.get("B2") is None
    assert s.get_raw("B3") == "=A2*2"
    assert is_num(s.get("B3"), 10.0)


def test_insert_rows_count():
    s = sheet_with(A5="1", B1="=A5+A4")
    s.insert_rows(5, 3)
    assert s.get_raw("B1") == "=A8+A4"
    assert is_num(s.get("A8"), 1.0)


def test_insert_rows_preserves_dollars():
    s = sheet_with(A1="1", B2="=$A$1+A$1+$A1")
    s.insert_rows(1)
    assert s.get_raw("B3") == "=$A$2+A$2+$A2"
    assert is_num(s.get("B3"), 3.0)


def test_insert_rows_preserves_bytes_outside_refs():
    s = sheet_with(B2='=  A1  &  "A1"  ')
    s.insert_rows(1)
    assert s.get_raw("B3") == '=  A2  &  "A1"  '


def test_insert_rows_does_not_rewrite_literal_text():
    s = sheet_with(A5="A1")
    s.insert_rows(1)
    assert s.get_raw("A6") == "A1"


def test_insert_rows_dependency_tracking_follows_moved_cells():
    s = sheet_with(A1="5", B2="=A1*2")
    s.insert_rows(1)
    assert s.set("A2", "6") == ["A2", "B3"]
    assert is_num(s.get("B3"), 12.0)


def test_insert_rows_range_strictly_inside_grows():
    s = sheet_with(A2="1", A3="2", A4="3", A5="4", C1="=SUM(A2:A5)")
    s.insert_rows(3)
    assert s.get_raw("C1") == "=SUM(A2:A6)"
    assert is_num(s.get("C1"), 10.0)
    s.set("A3", "100")
    assert is_num(s.get("C1"), 110.0)


def test_insert_rows_at_last_row_of_range_grows():
    s = sheet_with(A2="1", A5="4", C1="=SUM(A2:A5)")
    s.insert_rows(5)
    assert s.get_raw("C1") == "=SUM(A2:A6)"
    assert is_num(s.get("C1"), 5.0)


def test_insert_rows_at_first_row_of_range_shifts():
    s = sheet_with(A2="1", A5="4", C1="=SUM(A2:A5)")
    s.insert_rows(2)
    assert s.get_raw("C1") == "=SUM(A3:A6)"
    assert is_num(s.get("C1"), 5.0)


def test_insert_rows_directly_below_range_unchanged():
    s = sheet_with(A2="1", A5="4", C1="=SUM(A2:A5)")
    s.insert_rows(6)
    assert s.get_raw("C1") == "=SUM(A2:A5)"
    s.set("A6", "100")
    assert is_num(s.get("C1"), 5.0)


def test_insert_rows_range_preserves_dollars():
    s = sheet_with(C1="=SUM($A$2:$A$5)")
    s.insert_rows(1)
    assert s.get_raw("C2") == "=SUM($A$3:$A$6)"


def test_delete_rows_moves_cells_up():
    s = sheet_with(A1="a", A2="b", A3="c")
    s.delete_rows(1)
    assert s.get("A1") == "b"
    assert s.get("A2") == "c"
    assert s.get("A3") is None


def test_delete_rows_shifts_reference():
    s = sheet_with(A3="7", B5="=A3+1")
    s.delete_rows(1)
    assert s.get_raw("B4") == "=A2+1"
    assert is_num(s.get("B4"), 8.0)


def test_delete_rows_count():
    s = sheet_with(A10="1", B1="=A10")
    s.delete_rows(2, 3)
    assert s.get_raw("B1") == "=A7"
    assert is_num(s.get("B1"), 1.0)


def test_delete_rows_preserves_dollars():
    s = sheet_with(A3="2", B1="=$A$3*A$3")
    s.delete_rows(2)
    assert s.get_raw("B1") == "=$A$2*A$2"
    assert is_num(s.get("B1"), 4.0)


def test_delete_rows_single_deleted_ref_becomes_ref_token():
    s = sheet_with(A1="5", B2="=A1+1")
    s.delete_rows(1)
    assert s.get_raw("B1") == "=#REF!+1"
    assert s.get("B1") == E("#REF!")


def test_delete_rows_only_deleted_ref_replaced():
    s = sheet_with(A1="1", A3="3", B5="=A1+A3")
    s.delete_rows(1)
    assert s.get_raw("B4") == "=#REF!+A2"
    assert s.get("B4") == E("#REF!")


def test_delete_rows_dollar_ref_deleted_becomes_ref_token():
    s = sheet_with(A2="1", B5="=$A$2")
    s.delete_rows(2)
    assert s.get_raw("B4") == "=#REF!"


def test_delete_rows_ref_error_propagates_to_dependents():
    s = sheet_with(A1="5", B2="=A1+1", C3="=B2*2")
    s.delete_rows(1)
    assert s.get("C2") == E("#REF!")


def test_delete_rows_inside_range_shrinks():
    s = sheet_with(A1="1", A2="2", A3="3", A4="4", A5="5", C10="=SUM(A1:A5)")
    s.delete_rows(2, 2)
    assert s.get_raw("C8") == "=SUM(A1:A3)"
    assert is_num(s.get("C8"), 10.0)


def test_delete_rows_first_endpoint_moves():
    s = sheet_with(A1="1", A2="2", A3="3", A4="4", A5="5", C10="=SUM(A1:A5)")
    s.delete_rows(1)
    assert s.get_raw("C9") == "=SUM(A1:A4)"
    assert is_num(s.get("C9"), 14.0)


def test_delete_rows_first_endpoint_and_above_moves():
    s = sheet_with(A2="2", A3="3", A4="4", A5="5", C10="=SUM(A2:A5)")
    s.delete_rows(1, 2)
    assert s.get_raw("C8") == "=SUM(A1:A3)"
    assert is_num(s.get("C8"), 12.0)


def test_delete_rows_last_endpoint_moves():
    s = sheet_with(A1="1", A2="2", A3="3", A4="4", A5="5", C10="=SUM(A1:A5)")
    s.delete_rows(4, 3)
    assert s.get_raw("C7") == "=SUM(A1:A3)"
    assert is_num(s.get("C7"), 6.0)


def test_delete_rows_entire_range_is_ref():
    s = sheet_with(A2="1", A3="2", C10="=SUM(A2:A3)")
    s.delete_rows(2, 2)
    assert s.get("C8") == E("#REF!")
    assert "#REF!" in s.get_raw("C8")


def test_delete_rows_range_preserves_dollars():
    s = sheet_with(C10="=SUM($A$1:$A$5)")
    s.delete_rows(2)
    assert s.get_raw("C9") == "=SUM($A$1:$A$4)"


def test_delete_rows_value_recalculated_for_shrunk_range():
    s = sheet_with(A1="1", A2="2", A3="=SUM(A1:A2)")
    s.delete_rows(1)
    assert is_num(s.get("A2"), 2.0)


def test_delete_rows_dependency_tracking_after_delete():
    s = sheet_with(A3="1", B5="=A3*10")
    s.delete_rows(1)
    assert s.set("A2", "2") == ["A2", "B4"]


def test_insert_cols_shifts_reference():
    s = sheet_with(A1="4", B2="=A1+1")
    s.insert_cols(1)
    assert s.get_raw("C2") == "=B1+1"
    assert is_num(s.get("C2"), 5.0)
    assert s.get("A1") is None


def test_insert_cols_preserves_dollars():
    s = sheet_with(A1="1", A3="=$B$1+B$1+$B1")
    s.insert_cols(2)
    assert s.get_raw("A3") == "=$C$1+C$1+$C1"


def test_insert_cols_count():
    s = sheet_with(B1="2", A2="=B1")
    s.insert_cols(2, 26)
    assert s.get_raw("A2") == "=AB1"
    assert is_num(s.get("A2"), 2.0)


def test_insert_cols_range_strictly_inside_grows():
    s = sheet_with(B1="1", C1="2", D1="3", A5="=SUM(B1:D1)")
    s.insert_cols(3)
    assert s.get_raw("A5") == "=SUM(B1:E1)"
    assert is_num(s.get("A5"), 6.0)


def test_insert_cols_directly_right_of_range_unchanged():
    s = sheet_with(B1="1", D1="3", A5="=SUM(B1:D1)")
    s.insert_cols(5)
    assert s.get_raw("A5") == "=SUM(B1:D1)"


def test_delete_cols_shifts_reference():
    s = sheet_with(C1="9", A2="=C1")
    s.delete_cols(2)
    assert s.get_raw("A2") == "=B1"
    assert is_num(s.get("A2"), 9.0)


def test_delete_cols_deleted_ref_becomes_ref_token():
    s = sheet_with(B1="9", A2="=B1*2")
    s.delete_cols(2)
    assert s.get_raw("A2") == "=#REF!*2"
    assert s.get("A2") == E("#REF!")


def test_delete_cols_first_endpoint_moves():
    s = sheet_with(B1="1", C1="2", D1="3", A5="=SUM(B1:D1)")
    s.delete_cols(2)
    assert s.get_raw("A5") == "=SUM(B1:C1)"
    assert is_num(s.get("A5"), 5.0)


def test_delete_cols_entire_range_is_ref():
    s = sheet_with(B1="1", C1="2", A5="=SUM(B1:C1)")
    s.delete_cols(2, 2)
    assert s.get("A5") == E("#REF!")


def test_delete_cols_moves_cells_left():
    s = sheet_with(A1="a", B1="b", C1="c")
    s.delete_cols(1)
    assert s.get("A1") == "b"
    assert s.get("B1") == "c"
    assert s.get("C1") is None


def test_insert_rows_drops_cell_pushed_past_grid():
    s = sheet_with(A1048576="5", A1048575="4")
    s.insert_rows(1)
    assert is_num(s.get("A1048576"), 4.0)


def test_insert_rows_reference_pushed_past_grid_is_ref():
    s = sheet_with(B1="=A1048576")
    s.insert_rows(2)
    assert s.get_raw("B1") == "=#REF!"
    assert s.get("B1") == E("#REF!")


def test_insert_cols_drops_cell_pushed_past_grid():
    s = sheet_with(XFD1="x")
    s.insert_cols(1)
    assert s.get("XFD1") is None


def test_insert_cols_reference_pushed_past_grid_is_ref():
    s = sheet_with(A2="=XFD1+1")
    s.insert_cols(2)
    assert s.get_raw("A2") == "=#REF!+1"
    assert s.get("A2") == E("#REF!")


def test_copy_shifts_relative_reference():
    s = sheet_with(A1="1", A2="3", B1="=A1*2")
    s.copy("B1", "B2")
    assert s.get_raw("B2") == "=A2*2"
    assert is_num(s.get("B2"), 6.0)


def test_copy_dollar_parts_not_shifted():
    s = sheet_with(B1="=$A$1+$A1+A$1")
    s.copy("B1", "C3")
    assert s.get_raw("C3") == "=$A$1+$A3+B$1"


def test_copy_range_reference_shifted():
    s = sheet_with(B1="=SUM(A1:A3)")
    s.copy("B1", "C2")
    assert s.get_raw("C2") == "=SUM(B2:B4)"


def test_copy_range_reference_mixed_dollars():
    s = sheet_with(B1="=SUM($A1:A$3)")
    s.copy("B1", "C2")
    assert s.get_raw("C2") == "=SUM($A2:B$3)"


def test_copy_preserves_bytes_outside_refs():
    s = sheet_with(B1='=  A1 & "B1"')
    s.copy("B1", "B2")
    assert s.get_raw("B2") == '=  A2 & "B1"'


def test_copy_literal_raw_unchanged():
    s = sheet_with(A1="'A1", A2="  hi ")
    s.copy("A1:A2", "C1")
    assert s.get_raw("C1") == "'A1"
    assert s.get_raw("C2") == "  hi "


def test_copy_off_grid_reference_is_ref():
    s = sheet_with(B2="=A1+1")
    s.copy("B2", "A1")
    assert s.get_raw("A1") == "=#REF!+1"
    assert s.get("A1") == E("#REF!")


def test_copy_off_grid_dollar_part_kept():
    s = sheet_with(B2="=$A1")
    s.copy("B2", "A1")
    assert s.get("A1") == E("#REF!")


def test_copy_block():
    s = sheet_with(A1="1", B1="2", A2="=A1+B1", B2="=B1*10")
    s.copy("A1:B2", "D5")
    assert is_num(s.get("D5"), 1.0)
    assert is_num(s.get("E5"), 2.0)
    assert s.get_raw("D6") == "=D5+E5"
    assert s.get_raw("E6") == "=E5*10"
    assert is_num(s.get("D6"), 3.0)
    assert is_num(s.get("E6"), 20.0)


def test_copy_returns_changed_sorted():
    s = sheet_with(A1="1", B1="2", A2="=A1+B1", B2="=B1*10")
    assert s.copy("A1:B2", "D5") == ["D5", "E5", "D6", "E6"]


def test_copy_returns_dependents_of_destination():
    s = sheet_with(A1="5", C1="=D5+1")
    assert s.copy("A1", "D5") == ["C1", "D5"]
    assert is_num(s.get("C1"), 6.0)


def test_copy_unchanged_value_returns_empty():
    s = sheet_with(A1="5", B1="5")
    assert s.copy("A1", "B1") == []


def test_copy_empty_source_clears_destination():
    s = sheet_with(D1="x")
    assert s.copy("A1", "D1") == ["D1"]
    assert s.get("D1") is None
    assert s.get_raw("D1") == ""


def test_copy_empty_cells_in_block_clear_destination():
    s = sheet_with(A1="1", D1="old", D2="old2")
    s.copy("A1:A2", "D1")
    assert is_num(s.get("D1"), 1.0)
    assert s.get("D2") is None


def test_copy_overlap_downward_reads_before_write():
    s = sheet_with(A1="a", A2="b", A3="c")
    s.copy("A1:A2", "A2")
    assert s.get("A1") == "a"
    assert s.get("A2") == "a"
    assert s.get("A3") == "b"


def test_copy_overlap_upward_reads_before_write():
    s = sheet_with(A1="a", A2="b", A3="c")
    s.copy("A2:A3", "A1")
    assert s.get("A1") == "b"
    assert s.get("A2") == "c"
    assert s.get("A3") == "c"


def test_copy_overlap_formulas():
    s = sheet_with(A1="1", A2="=A1+1", A3="=A2+1")
    assert s.copy("A1:A2", "A2") == ["A2", "A3"]
    assert s.get_raw("A2") == "1"
    assert s.get_raw("A3") == "=A2+1"
    assert is_num(s.get("A3"), 2.0)


def test_copy_overlap_horizontal():
    s = sheet_with(A1="x", B1="y", C1="z")
    s.copy("A1:B1", "B1")
    assert s.get("B1") == "x"
    assert s.get("C1") == "y"


def test_copy_lowercase_addresses():
    s = sheet_with(A1="7")
    assert s.copy("a1", "c3") == ["C3"]
    assert is_num(s.get("C3"), 7.0)


def test_perf_many_unrelated_edits_on_50k_cell_sheet():
    s = Sheet()
    rows = 5000
    for r in range(1, rows + 1):
        s.set(f"A{r}", str(r))
        s.set(f"B{r}", f"=A{r}+1")
        s.set(f"C{r}", f"=B{r}*2")
        s.set(f"D{r}", "'txt")
        s.set(f"E{r}", f"=IF(A{r}>2,C{r},0)")
        s.set(f"F{r}", f"=SUM(A{r}:C{r})")
        s.set(f"G{r}", "1")
        s.set(f"H{r}", "2.5")
        s.set(f"I{r}", "TRUE")
        s.set(f"J{r}", f"=H{r}*{r}")
    s.set("L1", f"=SUM(B1:B{rows})")
    assert is_num(s.get("L1"), float(sum(range(2, rows + 2))))

    start = time.perf_counter()
    for i in range(2000):
        r = (i * 7) % rows + 1
        assert s.set(f"G{r}", str(i + 100)) == [f"G{r}"]
    elapsed = time.perf_counter() - start
    assert elapsed < 3.0, f"2000 unrelated edits took {elapsed:.2f}s"
    assert is_num(s.get("F10"), 10.0 + 11.0 + 22.0)


def test_perf_long_chain_no_recursion_error():
    s = Sheet()
    n = 30000
    s.set("A1", "1")
    for r in range(2, n + 1):
        s.set(f"A{r}", f"=A{r - 1}+1")
    assert is_num(s.get(f"A{n}"), float(n))
    changed = s.set("A1", "10")
    assert is_num(s.get(f"A{n}"), float(n + 9))
    assert len(changed) == n
    assert changed[0] == "A1" and changed[-1] == f"A{n}"


def test_perf_long_chain_closed_into_cycle_and_broken():
    s = Sheet()
    n = 20000
    s.set("A1", "1")
    for r in range(2, n + 1):
        s.set(f"A{r}", f"=A{r - 1}+1")
    s.set("A1", f"=A{n}")
    assert s.get("A1") == E("#CYCLE!")
    assert s.get(f"A{n}") == E("#CYCLE!")
    s.set("A1", "1")
    assert is_num(s.get(f"A{n}"), float(n))
