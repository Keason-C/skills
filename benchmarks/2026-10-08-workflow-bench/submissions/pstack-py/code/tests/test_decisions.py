import pytest

from gridcalc import CellError, Sheet


def value_of(raw, **cells):
    s = Sheet()
    for addr, cell_raw in cells.items():
        s.set(addr, cell_raw)
    s.set("Z100", raw)
    return s.get("Z100")


def err(code):
    return CellError(code)


def test_reference_to_empty_cell_is_zero():
    v = value_of("=A1")
    assert type(v) is float and v == 0.0


def test_reference_to_empty_cell_concatenates_as_empty_text():
    assert value_of('=A1&""') == ""


@pytest.mark.parametrize("fn, expected", [("SUM", 5.0), ("COUNT", 1.0), ("MAX", 5.0), ("AVERAGE", 5.0)])
def test_single_reference_argument_skips_text_like_a_range(fn, expected):
    assert value_of(f"={fn}(A1,A2)", A1="abc", A2="5") == expected


def test_single_reference_argument_to_and_skips_text():
    assert value_of("=AND(A1,A2)", A1="abc", A2="TRUE") is True
    assert value_of("=AND(A1)", A1="abc") == err("#VALUE!")


def test_scalar_text_argument_is_coerced():
    assert value_of('=SUM("abc")') == err("#VALUE!")
    assert value_of('=SUM("4",1)') == 5.0


@pytest.mark.parametrize(
    "formula, expected",
    [
        ('="1"=1', False),
        ('="abc"="ABC"', True),
        ('=2<"a"', True),
        ('="z"<TRUE', True),
        ("=A1=0", True),
        ('=A1=""', True),
        ("=A1=FALSE", True),
        ('="b">"A"', True),
    ],
)
def test_excel_style_comparisons(formula, expected):
    assert value_of(formula) is expected


@pytest.mark.parametrize(
    "formula, expected",
    [
        ('=1&""', "1"),
        ('=0.1+0.2&""', "0.3"),
        ('=1E20&""', "1e+20"),
        ('=-0&""', "0"),
        ('=1/3&""', "0.333333333333333"),
        ("=LEN(1.5)", 3.0),
        ('=CONCAT(1,TRUE,"x")', "1TRUEx"),
    ],
)
def test_number_to_text_uses_15_significant_digits(formula, expected):
    assert value_of(formula) == expected


@pytest.mark.parametrize(
    "formula, expected",
    [
        ("=0^-1", err("#DIV/0!")),
        ("=0^0", 1.0),
        ("=(-8)^(1/3)", err("#VALUE!")),
        ("=10^400", err("#VALUE!")),
        ("=1E300*1E300", err("#VALUE!")),
        ("=1e400", err("#VALUE!")),
    ],
)
def test_math_without_a_real_result(formula, expected):
    assert value_of(formula) == expected


def test_overflowing_number_literal_is_text():
    assert value_of("=A1", A1="1e400") == "1e400"


@pytest.mark.parametrize("formula", ["=ABS(1,2)", "=SUM()", "=IF(1)", "=NOT()", "=ROUND(1)"])
def test_wrong_argument_count_is_value_error(formula):
    assert value_of(formula) == err("#VALUE!")


def test_unknown_function_wins_over_argument_count():
    assert value_of("=NOPE()") == err("#NAME?")


@pytest.mark.parametrize("formula", ["=foo+1", "=XFE1", "=A0", "=ABCD1", "=A01"])
def test_unknown_bare_names_are_name_errors(formula):
    assert value_of(formula) == err("#NAME?")


def test_name_error_does_not_create_a_dependency():
    s = Sheet()
    s.set("B1", "=XFE1")
    assert s.set("A1", "5") == ["A1"]


@pytest.mark.parametrize("raw, expected", [(" TRUE ", True), ("\tfalse\n", False), ("1.", 1.0), ("+5", 5.0)])
def test_literal_whitespace_and_signs(raw, expected):
    assert value_of("=A1", A1=raw) == expected


@pytest.mark.parametrize("formula, expected", [("=ROUND(2.675,2)", 2.68), ("=ROUND(-2.5,0)", -3.0), ("=ROUND(1234,-2)", 1200.0), ("=ROUND(1.5,0.9)", 2.0)])
def test_round_half_away_from_zero(formula, expected):
    assert value_of(formula) == expected


@pytest.mark.parametrize(
    "method, args",
    [
        ("insert_rows", (0,)),
        ("insert_rows", (1048577,)),
        ("insert_rows", (1, 0)),
        ("delete_rows", (1048576, 2)),
        ("insert_cols", (16385,)),
        ("delete_cols", (1, -1)),
    ],
)
def test_invalid_structural_arguments_raise(method, args):
    s = Sheet()
    s.set("A1", "1")
    with pytest.raises(ValueError):
        getattr(s, method)(*args)
    assert s.get("A1") == 1.0


def test_delete_last_row_and_column_are_allowed():
    s = Sheet()
    s.set("A1048576", "1")
    s.set("XFD1", "2")
    s.delete_rows(1048576)
    s.delete_cols(16384)
    assert s.get("A1048576") is None and s.get("XFD1") is None


@pytest.mark.parametrize("dst", ["XFD1", "A1048576", "B1:C2", "$B$1"])
def test_invalid_copy_destination_raises_and_changes_nothing(dst):
    s = Sheet()
    s.set("A1", "1")
    s.set("B2", "2")
    with pytest.raises(ValueError):
        s.copy("A1:B2", dst)
    assert s.get_raw("XFD1") == "" and s.get_raw("B1") == ""


@pytest.mark.parametrize("addr", ["A01", " A1", "A1 ", "$A$1", "A1:B2", "", "1A", "A"])
def test_malformed_api_addresses_raise(addr):
    with pytest.raises(ValueError):
        Sheet().get(addr)


def test_insert_inside_range_clamps_end_at_grid_edge():
    s = Sheet()
    s.set("A1", "=SUM(A1048570:A1048575)")
    s.insert_rows(1048572, 10)
    assert s.get_raw("A1") == "=SUM(A1048570:A1048576)"


def test_insert_pushing_range_start_off_grid_is_ref():
    s = Sheet()
    s.set("A1", "=SUM(A1048570:A1048575)")
    s.insert_rows(1000, 10)
    assert s.get_raw("A1") == "=SUM(#REF!)"
    assert s.get("A1") == err("#REF!")


def test_rewrite_preserves_untouched_text_byte_for_byte():
    s = Sheet()
    s.set("A1", '= sum( a3:a5 ) + $b$3 + "A3" & a1048576')
    s.insert_rows(2)
    assert s.get_raw("A1") == '= sum( A4:A6 ) + $B$4 + "A3" & #REF!'


def test_unchanged_reference_keeps_its_spelling():
    s = Sheet()
    s.set("C1", "=a1+B3:b2")
    s.insert_rows(5)
    assert s.get_raw("C1") == "=a1+B3:b2"


def test_rewritten_reversed_range_is_normalised_with_markers():
    s = Sheet()
    s.set("C1", "=SUM(B$3:$A1)")
    s.insert_rows(1)
    assert s.get_raw("C2") == "=SUM($A2:B$4)"


def test_unparseable_formula_still_has_references_rewritten():
    s = Sheet()
    s.set("A1", "=B5+")
    s.insert_rows(1)
    assert s.get_raw("A2") == "=B6+"
    assert s.get("A2") == err("#PARSE!")


def test_copy_reversing_endpoints_normalises_range():
    s = Sheet()
    s.set("C1", "=SUM(A1:$B1)")
    s.copy("C1", "F1")
    assert s.get_raw("F1") == "=SUM($B1:D1)"


def test_error_literals_parse_case_insensitively():
    assert value_of("=#ref!") == err("#REF!")
    assert value_of("=IFERROR(#DIV/0!,7)") == 7.0


def test_huge_ranges_iterate_only_populated_cells():
    s = Sheet()
    s.set("C3", "=SUM(A1:XFD1048575)")
    s.set("B1048575", "4")
    s.set("A1", "'x")
    assert s.get("C3") == err("#CYCLE!")
    s.set("D1048576", "=CONCAT(A1:B1048575)")
    assert s.get("D1048576") == "x4"
    assert s.set("B1048575", "5") == ["B1048575", "D1048576"]


def test_long_flat_formula_does_not_recurse_per_operator():
    assert value_of("=" + "+".join(["1"] * 5000)) == 5000.0


def test_cycle_member_unreachable_from_edit_keeps_cycle():
    s = Sheet()
    s.set("A1", "=B1")
    s.set("B1", "=A1")
    s.set("C1", "=A1")
    assert s.set("D1", "1") == ["D1"]
    assert s.get("C1") == err("#CYCLE!")


@pytest.mark.parametrize("formula", ["=１+1", "=²", "=.１", "=1+①"])
def test_non_ascii_digits_are_parse_errors(formula):
    assert value_of(formula) == err("#PARSE!")


@pytest.mark.parametrize("depth", [200, 1000])
def test_deep_nesting_through_functions(depth):
    assert value_of("=" + "(1+SUM(" * depth + "1" + "))" * depth) == depth + 1.0
    assert value_of("=" + "IF(FALSE,0," * depth + "1" + ")" * depth) == 1.0


def test_recursion_limit_is_restored():
    import sys

    before = sys.getrecursionlimit()
    value_of("=" + "(" * 500 + "1" + ")" * 500)
    assert sys.getrecursionlimit() == before
