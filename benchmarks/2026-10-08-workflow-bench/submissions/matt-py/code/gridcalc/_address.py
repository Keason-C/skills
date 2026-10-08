"""Cell addresses: column letters <-> numbers, parsing and formatting."""

from __future__ import annotations

import re

MAX_ROW = 1048576
MAX_COL = 16384

_ADDR_RE = re.compile(r"([A-Za-z]{1,3})([0-9]+)")


def col_to_num(letters: str) -> int:
    n = 0
    for ch in letters.upper():
        n = n * 26 + (ord(ch) - 64)
    return n


def num_to_col(n: int) -> str:
    out = []
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out.append(chr(65 + rem))
    return "".join(reversed(out))


def in_grid(row: int, col: int) -> bool:
    return 1 <= row <= MAX_ROW and 1 <= col <= MAX_COL


def parse_addr(addr: str) -> tuple[int, int]:
    """Parse an API address like "b3" into (row, col); ValueError if invalid."""
    if not isinstance(addr, str):
        raise ValueError(f"invalid address: {addr!r}")
    m = _ADDR_RE.fullmatch(addr)
    if m is None:
        raise ValueError(f"invalid address: {addr!r}")
    row, col = int(m.group(2)), col_to_num(m.group(1))
    if not in_grid(row, col):
        raise ValueError(f"address outside the grid: {addr!r}")
    return row, col


def format_addr(row: int, col: int) -> str:
    return f"{num_to_col(col)}{row}"
