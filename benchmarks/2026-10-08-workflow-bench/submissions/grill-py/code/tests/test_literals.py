import pytest

from gridcalc import Sheet


def value_of(raw):
    s = Sheet()
    s.set("A1", raw)
    return s.get("A1")


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("42", 42.0),
        (" 42 ", 42.0),
        ("-2.5E-2", -0.025),
        ("1e3", 1000.0),
        (".5", 0.5),
        ("1.", 1.0),
        ("+5", 5.0),
        ("0", 0.0),
        ("\t7\n", 7.0),
    ],
)
def test_numeric_literals_are_floats(raw, expected):
    v = value_of(raw)
    assert type(v) is float
    assert v == expected


@pytest.mark.parametrize(
    "raw",
    [
        "inf",
        "nan",
        "1_000",
        "0x10",
        "1,000",
        "١٢",
        "1e",
        "e3",
        ".",
        "+",
        "1e400",
        "- 1",
    ],
)
def test_non_numbers_stay_text_exactly_as_given(raw):
    assert value_of(raw) == raw


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("TRUE", True),
        ("false", False),
        ("True", True),
        (" true ", True),
        ("FALSE\n", False),
    ],
)
def test_boolean_literals(raw, expected):
    assert value_of(raw) is expected


def test_apostrophe_forces_text():
    assert value_of("'123") == "123"
    assert value_of("'TRUE") == "TRUE"
    assert value_of("'=1+1") == "=1+1"


def test_lone_apostrophe_is_empty_text_not_empty_cell():
    s = Sheet()
    s.set("A1", "'")
    assert s.get("A1") == ""
    assert s.get_raw("A1") == "'"


def test_text_is_not_stripped():
    assert value_of("   ") == "   "
    assert value_of("  hi ") == "  hi "


def test_leading_space_before_equals_is_text():
    assert value_of(" =1") == " =1"


def test_raw_is_returned_exactly():
    s = Sheet()
    s.set("A1", " 42 ")
    assert s.get_raw("A1") == " 42 "


def test_empty_string_clears_cell():
    s = Sheet()
    s.set("A1", "5")
    assert s.set("A1", "") == ["A1"]
    assert s.get("A1") is None
    assert s.get_raw("A1") == ""


def test_setting_same_value_reports_no_change():
    s = Sheet()
    s.set("A1", "5")
    assert s.set("A1", "5.0") == []
    assert s.get_raw("A1") == "5.0"


def test_type_change_counts_as_change():
    s = Sheet()
    s.set("A1", "1")
    assert s.set("A1", "TRUE") == ["A1"]
    assert s.set("A1", "'TRUE") == ["A1"]
