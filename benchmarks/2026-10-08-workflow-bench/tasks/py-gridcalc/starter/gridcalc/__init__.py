"""gridcalc: an in-memory spreadsheet engine. See BRIEF.md.

The public API below is fixed: keep these names and signatures.
"""

from __future__ import annotations

__all__ = ["Sheet", "CellError"]


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


class Sheet:
    def __init__(self) -> None:
        raise NotImplementedError

    def set(self, addr: str, raw: str) -> list[str]:
        raise NotImplementedError

    def get(self, addr: str) -> float | str | bool | CellError | None:
        raise NotImplementedError

    def get_raw(self, addr: str) -> str:
        raise NotImplementedError

    def insert_rows(self, at: int, count: int = 1) -> None:
        raise NotImplementedError

    def delete_rows(self, at: int, count: int = 1) -> None:
        raise NotImplementedError

    def insert_cols(self, at: int, count: int = 1) -> None:
        raise NotImplementedError

    def delete_cols(self, at: int, count: int = 1) -> None:
        raise NotImplementedError

    def copy(self, src: str, dst: str) -> list[str]:
        raise NotImplementedError
