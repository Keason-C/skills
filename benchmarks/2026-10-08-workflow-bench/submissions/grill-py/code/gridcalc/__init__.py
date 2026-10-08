"""gridcalc: an in-memory spreadsheet engine. See BRIEF.md.

The public API below is fixed: keep these names and signatures.
"""

from __future__ import annotations

__all__ = ["CellError", "Sheet"]


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


# Imported after CellError is defined: the engine modules import it from here.
from ._engine import Engine


class Sheet:
    def __init__(self) -> None:
        self._engine = Engine()

    def set(self, addr: str, raw: str) -> list[str]:
        return self._engine.set(addr, raw)

    def get(self, addr: str) -> float | str | bool | CellError | None:
        return self._engine.get(addr)

    def get_raw(self, addr: str) -> str:
        return self._engine.get_raw(addr)

    def insert_rows(self, at: int, count: int = 1) -> None:
        self._engine.insert(True, at, count)

    def delete_rows(self, at: int, count: int = 1) -> None:
        self._engine.delete(True, at, count)

    def insert_cols(self, at: int, count: int = 1) -> None:
        self._engine.insert(False, at, count)

    def delete_cols(self, at: int, count: int = 1) -> None:
        self._engine.delete(False, at, count)

    def copy(self, src: str, dst: str) -> list[str]:
        return self._engine.copy(src, dst)
