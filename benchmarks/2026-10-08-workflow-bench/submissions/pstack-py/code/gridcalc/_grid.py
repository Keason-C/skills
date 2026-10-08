from __future__ import annotations

import re
from functools import lru_cache

MAX_ROW = 1048576
MAX_COL = 16384

Addr = tuple[int, int]
Rect = tuple[int, int, int, int]

_ADDR_RE = re.compile(r"([A-Za-z]{1,3})([1-9][0-9]*)")


@lru_cache(maxsize=None)
def col_letters(col: int) -> str:
    letters = ""
    while col:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def letters_col(letters: str) -> int:
    col = 0
    for ch in letters.upper():
        col = col * 26 + ord(ch) - 64
    return col


def in_grid(row: int, col: int) -> bool:
    return 1 <= row <= MAX_ROW and 1 <= col <= MAX_COL


def parse_addr(text: str) -> Addr:
    m = _ADDR_RE.fullmatch(text) if isinstance(text, str) else None
    if m is None:
        raise ValueError(f"malformed address: {text!r}")
    row, col = int(m[2]), letters_col(m[1])
    if not in_grid(row, col):
        raise ValueError(f"address outside the grid: {text!r}")
    return row, col


def parse_block(text: str) -> Rect:
    if not isinstance(text, str):
        raise ValueError(f"malformed range: {text!r}")
    first, sep, last = text.partition(":")
    r1, c1 = parse_addr(first)
    r2, c2 = parse_addr(last) if sep else (r1, c1)
    return min(r1, r2), min(c1, c2), max(r1, r2), max(c1, c2)


def format_addr(addr: Addr) -> str:
    return f"{col_letters(addr[1])}{addr[0]}"
