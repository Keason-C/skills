"""Randomised check: after any sequence of edits, every value equals what a
freshly built sheet with the same raw contents computes, and change lists
report exactly the cells whose values changed."""

import random

import pytest

from gridcalc import Sheet

ROWS, COLS = 10, 6
LETTERS = "ABCDEF"


def addr(r, c):
    return f"{LETTERS[c - 1]}{r}"


def all_addrs():
    return [addr(r, c) for r in range(1, ROWS + 1) for c in range(1, COLS + 1)]


def rand_ref(rng):
    d1, d2 = rng.choice(["", "$"]), rng.choice(["", "$"])
    return f"{d1}{rng.choice(LETTERS)}{d2}{rng.randint(1, ROWS)}"


def rand_operand(rng):
    roll = rng.random()
    if roll < 0.5:
        return rand_ref(rng)
    if roll < 0.7:
        return str(rng.randint(0, 9))
    if roll < 0.8:
        return rng.choice(['"x"', '"3"', "TRUE", "#REF!"])
    return f"SUM({rand_ref(rng)}:{rand_ref(rng)})"


def rand_formula(rng):
    a, b = rand_operand(rng), rand_operand(rng)
    templates = [
        f"={a}+{b}",
        f"={a}*{b}-1",
        f"={a}&{b}",
        f"=IF({a}>{b}, {a}, {b})",
        f"=IFERROR({a}/{b}, -1)",
        f"=COUNT({rand_ref(rng)}:{rand_ref(rng)}, {a})",
        f"=CONCAT({rand_ref(rng)}:{rand_ref(rng)})",
        f"=MAX({a}, {b})",
        f"={a}",
        f"=AND({a}, {b})",
    ]
    return rng.choice(templates)


def rand_raw(rng):
    roll = rng.random()
    if roll < 0.45:
        return rand_formula(rng)
    if roll < 0.75:
        return str(rng.randint(-5, 20))
    if roll < 0.85:
        return rng.choice(["hello", "TRUE", "'7", " 2.5 "])
    return ""


def snapshot(sheet):
    return {a: sheet.get(a) for a in all_addrs()}


def same(x, y):
    return type(x) is type(y) and x == y


def check_against_fresh(sheet):
    fresh = Sheet()
    for a in all_addrs():
        raw = sheet.get_raw(a)
        if raw:
            fresh.set(a, raw)
    for a in all_addrs():
        assert same(sheet.get(a), fresh.get(a)), (
            a,
            sheet.get_raw(a),
            sheet.get(a),
            fresh.get(a),
        )


def expected_changes(before, after):
    return [a for a in all_addrs() if not same(before[a], after[a])]


def row_major(addrs):
    return sorted(addrs, key=lambda a: (int(a[1:]), a[0]))


@pytest.mark.parametrize("seed", range(40))
def test_random_edit_sequences_match_fresh_sheet(seed):
    rng = random.Random(seed)
    s = Sheet()
    for a in all_addrs():
        if rng.random() < 0.6:
            s.set(a, rand_raw(rng))
    check_against_fresh(s)
    for _ in range(25):
        before = snapshot(s)
        op = rng.random()
        if op < 0.5:
            target = rng.choice(all_addrs())
            changed = s.set(target, rand_raw(rng))
            assert changed == row_major(expected_changes(before, snapshot(s)))
        elif op < 0.65:
            r1, r2 = sorted(rng.sample(range(1, ROWS + 1), 2))
            c1, c2 = sorted(rng.sample(range(1, COLS + 1), 2))
            dr, dc = rng.randint(1, ROWS - (r2 - r1)), rng.randint(1, COLS - (c2 - c1))
            changed = s.copy(f"{addr(r1, c1)}:{addr(r2, c2)}", addr(dr, dc))
            assert changed == row_major(expected_changes(before, snapshot(s)))
        else:
            rows = rng.random() < 0.5
            limit = ROWS if rows else COLS
            at = rng.randint(1, limit)
            count = rng.randint(1, 2)
            if rng.random() < 0.5:
                (s.insert_rows if rows else s.insert_cols)(at, count)
                # Drop what was pushed past the window so it stays fully populated
                # inside it (a legitimate edit sequence in its own right).
                (s.delete_rows if rows else s.delete_cols)(limit + 1, count)
            elif at + count - 1 <= limit:
                (s.delete_rows if rows else s.delete_cols)(at, count)
        check_against_fresh(s)
        for a in all_addrs():
            raw = s.get_raw(a)
            if raw.startswith("="):
                assert s.set(a, raw) == [], (a, raw)
