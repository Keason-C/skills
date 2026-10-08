"""Cell coordinates: parsing and formatting of A1-style addresses.

Coordinates are 1-based ``(row, col)`` tuples throughout the package.
"""

from __future__ import annotations

import re

MAX_ROW = 1048576
MAX_COL = 16384


class ArgumentTypeError(TypeError, ValueError):
    """An argument of the wrong type, such as an address that is not a string.

    It is both a ``TypeError`` and a ``ValueError``, so callers catching either
    one (``ValueError`` being what the API raises for malformed addresses) work.
    """


_ADDR_RE = re.compile(r"([A-Za-z]{1,3})([1-9][0-9]{0,6})")


def letters_to_col(letters: str) -> int:
    """Bijective base-26: ``A`` -> 1, ``Z`` -> 26, ``AA`` -> 27."""
    n = 0
    for ch in letters.upper():
        n = n * 26 + (ord(ch) - 64)
    return n


def col_to_letters(col: int) -> str:
    out = []
    while col:
        col, rem = divmod(col - 1, 26)
        out.append(chr(65 + rem))
    return "".join(reversed(out))


def format_addr(row: int, col: int) -> str:
    return f"{col_to_letters(col)}{row}"


def in_grid(row: int, col: int) -> bool:
    return 1 <= row <= MAX_ROW and 1 <= col <= MAX_COL


_addr_cache: dict[str, tuple[int, int]] = {}


def parse_addr(addr: str) -> tuple[int, int]:
    """Parse a plain API address (no ``$``, no whitespace) or raise ``ValueError``."""
    pos = _addr_cache.get(addr) if type(addr) is str else None
    if pos is not None:
        return pos
    pos = _parse_addr(addr)
    if len(_addr_cache) >= 100_000:
        _addr_cache.clear()
    _addr_cache[addr] = pos
    return pos


def _parse_addr(addr: str) -> tuple[int, int]:
    if not isinstance(addr, str):
        raise ArgumentTypeError(f"address must be a str, not {type(addr).__name__}")
    m = _ADDR_RE.fullmatch(addr)
    if m is None:
        raise ValueError(f"malformed address: {addr!r}")
    row, col = int(m.group(2)), letters_to_col(m.group(1))
    if not in_grid(row, col):
        raise ValueError(f"address outside the grid: {addr!r}")
    return row, col


def parse_block(block: str) -> tuple[int, int, int, int]:
    """Parse ``"A1"`` or ``"A1:B2"`` into a normalised ``(r1, c1, r2, c2)``."""
    if not isinstance(block, str):
        raise ArgumentTypeError(f"range must be a str, not {type(block).__name__}")
    first, sep, second = block.partition(":")
    r1, c1 = parse_addr(first)
    r2, c2 = parse_addr(second) if sep else (r1, c1)
    return min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2)
