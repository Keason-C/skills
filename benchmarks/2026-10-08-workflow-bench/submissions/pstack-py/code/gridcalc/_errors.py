from __future__ import annotations


class CellError:
    """An error value stored in a cell. Compare by code."""

    __slots__ = ("code",)

    CODES = ("#DIV/0!", "#VALUE!", "#REF!", "#NAME?", "#CYCLE!", "#PARSE!")

    def __init__(self, code: str) -> None:
        if code not in self.CODES:
            raise ValueError(f"unknown error code: {code!r}")
        self.code = code

    def __eq__(self, other: object) -> bool:
        return isinstance(other, CellError) and other.code == self.code

    def __hash__(self) -> int:
        return hash(("CellError", self.code))

    def __repr__(self) -> str:
        return f"CellError({self.code!r})"


DIV0 = CellError("#DIV/0!")
VALUE = CellError("#VALUE!")
REF = CellError("#REF!")
NAME = CellError("#NAME?")
CYCLE = CellError("#CYCLE!")
PARSE = CellError("#PARSE!")
