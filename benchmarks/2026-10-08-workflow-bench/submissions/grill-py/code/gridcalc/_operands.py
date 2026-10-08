"""What formula evaluation passes around: values and not-yet-read references."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol

from ._values import VALUE, Value

Pos = tuple[int, int]
Box = tuple[int, int, int, int]  # (top, left, bottom, right)


class Reader(Protocol):
    """Read access to cell values during evaluation."""

    def value_at(self, pos: Pos) -> Value: ...

    def range_values(self, box: Box) -> Iterator[Value]:
        """Values of the populated cells in ``box``, row-major."""
        ...


# A reference written directly in a formula travels unread through evaluation
# as its coordinates: a ``Pos`` for a cell, a ``Box`` for a range. Plain tuples
# of ints keep compiled formulas cheap for the garbage collector, and no cell
# value is ever a tuple.
Operand = Value | Pos | Box


def scalar(x: Operand, reader: Reader) -> Value:
    """Resolve an operand where a single value is required."""
    if type(x) is tuple:
        return reader.value_at(x) if len(x) == 2 else VALUE  # type: ignore[arg-type]
    return x  # type: ignore[return-value]


def cells(x: Operand, reader: Reader) -> Iterator[Value] | None:
    """Populated values of a reference operand (row-major), or None for a plain value."""
    if type(x) is not tuple:
        return None
    if len(x) == 4:
        return reader.range_values(x)  # type: ignore[arg-type]
    v = reader.value_at(x)  # type: ignore[arg-type]
    return iter(()) if v is None else iter((v,))
