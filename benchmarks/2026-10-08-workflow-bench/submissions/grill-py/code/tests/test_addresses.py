import pytest

from gridcalc import Sheet


@pytest.mark.parametrize("addr", ["A1", "Z99", "AA10", "XFD1048576", "b3", "xfd1"])
def test_valid_addresses_round_trip(addr):
    s = Sheet()
    s.set(addr, "x")
    assert s.get(addr) == "x"
    assert s.get(addr.upper()) == "x"


def test_addresses_are_case_insensitive():
    s = Sheet()
    s.set("b3", "hello")
    assert s.get("B3") == "hello"
    assert s.get_raw("b3") == "hello"


def test_returned_addresses_are_canonical_upper_case():
    s = Sheet()
    assert s.set("aa10", "1") == ["AA10"]


@pytest.mark.parametrize(
    "addr",
    [
        "",
        "A",
        "1",
        "A0",
        "A01",
        "$A$1",
        "A$1",
        " A1",
        "A1 ",
        "A1:B2",
        "1A",
        "XFE1",
        "A1048577",
        "AAAA1",
        "A-1",
        "A1.5",
        "Ä1",
    ],
)
def test_malformed_or_out_of_grid_addresses_raise_value_error(addr):
    s = Sheet()
    with pytest.raises(ValueError):
        s.get(addr)
    with pytest.raises(ValueError):
        s.get_raw(addr)
    with pytest.raises(ValueError):
        s.set(addr, "1")


def test_non_string_raw_raises_type_error():
    s = Sheet()
    with pytest.raises(TypeError):
        s.set("A1", 42)  # type: ignore[arg-type]


def test_empty_cell_reads_none_and_empty_raw():
    s = Sheet()
    assert s.get("C7") is None
    assert s.get_raw("C7") == ""


@pytest.mark.parametrize("bad", [5, None, 1.5, b"A1", ("A", 1)])
def test_non_string_address_raises_both_type_and_value_error(bad):
    s = Sheet()
    calls = [
        lambda: s.get(bad),
        lambda: s.get_raw(bad),
        lambda: s.set(bad, "1"),
        lambda: s.copy(bad, "A1"),
        lambda: s.copy("A1", bad),
    ]
    for call in calls:
        with pytest.raises(TypeError):
            call()
        with pytest.raises(ValueError):
            call()


@pytest.mark.parametrize(
    "op", ["insert_rows", "delete_rows", "insert_cols", "delete_cols"]
)
@pytest.mark.parametrize("args", [("1",), (True,), (1.0,), (1, None), (1, False)])
def test_non_int_structural_arguments_raise_both_type_and_value_error(op, args):
    with pytest.raises(TypeError):
        getattr(Sheet(), op)(*args)
    with pytest.raises(ValueError):
        getattr(Sheet(), op)(*args)
