import pytest

from gridcalc import Sheet


def test_number_literal_is_float():
    s = Sheet()
    s.set("A1", "42")
    assert s.get("A1") == 42.0
    assert type(s.get("A1")) is float


def test_empty_cell_is_none_and_raw_empty():
    s = Sheet()
    assert s.get("B7") is None
    assert s.get_raw("B7") == ""


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("-2.5E-2", -0.025),
        ("1e3", 1000.0),
        (".5", 0.5),
        ("+7", 7.0),
        ("  12  ", 12.0),
    ],
)
def test_number_forms(raw, expected):
    s = Sheet()
    s.set("A1", raw)
    assert s.get("A1") == expected
    assert s.get_raw("A1") == raw


def test_apostrophe_forces_text():
    s = Sheet()
    s.set("A1", "'123")
    assert s.get("A1") == "123"
    assert s.get_raw("A1") == "'123"


@pytest.mark.parametrize("raw,expected", [("TRUE", True), ("false", False), ("True", True)])
def test_booleans(raw, expected):
    s = Sheet()
    s.set("A1", raw)
    assert s.get("A1") is expected


def test_other_text_stored_exactly():
    s = Sheet()
    s.set("A1", "  hello ")
    assert s.get("A1") == "  hello "
    s.set("A2", "1,000")
    assert s.get("A2") == "1,000"


def test_empty_string_clears():
    s = Sheet()
    s.set("A1", "5")
    assert s.set("A1", "") == ["A1"]
    assert s.get("A1") is None
    assert s.get_raw("A1") == ""


def test_addresses_case_insensitive_and_validated():
    s = Sheet()
    s.set("b3", "1")
    assert s.get("B3") == 1.0
    assert s.set("xfd1048576", "2") == ["XFD1048576"]
    for bad in ["A0", "XFE1", "A1048577", "1A", "A", "", "A1:B2", "$A$1"]:
        with pytest.raises(ValueError):
            s.get(bad)
        with pytest.raises(ValueError):
            s.set(bad, "1")


def test_set_returns_changed_only_when_value_changes():
    s = Sheet()
    assert s.set("A1", "1") == ["A1"]
    assert s.set("A1", "1.0") == []
    assert s.get_raw("A1") == "1.0"
    assert s.set("A1", "TRUE") == ["A1"]  # 1.0 vs True differ by type
    assert s.set("A1", "'TRUE") == ["A1"]


def test_booleans_strip_surrounding_whitespace():
    s = Sheet()
    s.set("A1", " TRUE ")
    assert s.get("A1") is True
    assert s.get_raw("A1") == " TRUE "
    s.set("A2", "' true ")
    s.set("A3", "=IF(A2, 1, 2)")
    assert s.get("A3") == 1.0
