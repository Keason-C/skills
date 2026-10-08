"""Differential fuzz for gridcalc.  python3 -I fuzz_py.py <impl_dir> <out.json> [seeds]

Generates random op scripts (set / copy / insert / delete) restricted to behaviour the brief + PO
decisions pin down (no lowercase, no reversed or 1-cell ranges, no bare refs as SUM-family args,
no ranges in AND/OR, small exponents, copies only shift down/right). Records every changed-list and
a final snapshot of values and raws; the grader compares against the reference implementation.
"""
import json, math, random, signal, sys

impl, out_path = sys.argv[1], sys.argv[2]
SEEDS = int(sys.argv[3]) if len(sys.argv) > 3 else 300
sys.path.insert(0, impl)
import gridcalc  # noqa: E402

COLS = "ABCDEFGH"
NROW = 14


def col(i):
    return COLS[i]


class Gen:
    def __init__(self, r):
        self.r = r

    def ref(self):
        r = self.r
        c, row = r.randrange(6), r.randrange(1, 11)
        return ("$" if r.random() < 0.2 else "") + col(c) + ("$" if r.random() < 0.2 else "") + str(row)

    def rng(self):
        r = self.r
        c1, r1 = r.randrange(5), r.randrange(1, 9)
        c2, r2 = r.randrange(c1, 6), r.randrange(r1, 11)
        if c1 == c2 and r1 == r2:
            r2 += 1
        d = lambda: "$" if r.random() < 0.15 else ""
        return f"{d()}{col(c1)}{d()}{r1}:{d()}{col(c2)}{d()}{r2}"

    def num(self):
        r = self.r
        return r.choice(["0", "1", "2", "3", "10", "0.5", "2.5", "7", "100", "1.25", "4"])

    def text(self):
        return '"' + self.r.choice(["a", "B", "abc", "x y", "3", " 4 ", "", 'q""q', "TRUE", "1e2"]) + '"'

    def scalar(self, d):
        r = self.r
        k = r.random()
        if d <= 0 or k < 0.3:
            return r.choice([self.num, self.num, self.ref, self.ref, self.text, lambda: r.choice(["TRUE", "FALSE"])])()
        if k < 0.55:
            op = r.choice(["+", "-", "*", "/", "&", "=", "<>", "<", ">", "<=", ">=", "^"])
            right = r.choice(["0", "1", "2", "3"]) if op == "^" else self.scalar(d - 1)
            left = self.scalar(d - 1) if op != "^" else r.choice([self.num(), self.ref()])
            return f"{left}{op}{right}"
        if k < 0.6:
            return f"-{self.scalar(d - 1)}"
        if k < 0.68:
            return f"({self.scalar(d - 1)})"
        return self.func(d - 1)

    def agg_arg(self, d):
        return self.rng() if self.r.random() < 0.7 else f"{self.scalar(d)}+0"

    def func(self, d):
        r = self.r
        f = r.choice(["SUM", "AVERAGE", "MIN", "MAX", "COUNT", "IF", "IF3", "IFERROR", "ROUND", "ABS", "LEN",
                      "CONCAT", "AND", "OR", "NOT"])
        if f in ("SUM", "AVERAGE", "MIN", "MAX", "COUNT"):
            return f"{f}({','.join(self.agg_arg(d) for _ in range(r.randint(1, 3)))})"
        if f == "IF":
            return f"IF({self.cond(d)},{self.scalar(d)})"
        if f == "IF3":
            return f"IF({self.cond(d)},{self.scalar(d)},{self.scalar(d)})"
        if f == "IFERROR":
            return f"IFERROR({self.scalar(d)},{self.scalar(d)})"
        if f == "ROUND":
            return f"ROUND({self.scalar(d)},{r.choice(['0', '1', '2', '-1'])})"
        if f == "CONCAT":
            return f"CONCAT({','.join(self.rng() if r.random() < 0.4 else self.scalar(d) for _ in range(r.randint(1, 3)))})"
        if f in ("AND", "OR"):
            return f"{f}({','.join(self.cond(d) for _ in range(r.randint(1, 3)))})"
        if f == "NOT":
            return f"NOT({self.cond(d)})"
        return f"{f}({self.scalar(d)})"

    def cond(self, d):
        r = self.r
        if r.random() < 0.15:
            return r.choice(["TRUE", "FALSE"])
        return f"{self.scalar(max(0, d - 1))}{r.choice(['=', '<>', '<', '>', '<=', '>='])}{self.scalar(max(0, d - 1))}"

    def raw(self):
        r = self.r
        k = r.random()
        if k < 0.12:
            return ""
        if k < 0.35:
            return r.choice(["1", "2", "3.5", "-4", "10", "0", " 7 ", ".5", "1e2", "2.5E-1"])
        if k < 0.45:
            return r.choice(["hello", "Abc", "'12", "TRUE", "false", "x y", "3"])
        return "=" + self.scalar(r.randint(1, 3))


def norm(v):
    if isinstance(v, gridcalc.CellError):
        return ["err", v.code]
    if isinstance(v, float):
        if math.isnan(v):
            return ["num", "nan"]
        return ["num", round(v, 9)]
    return [type(v).__name__, v]


class Timeout(Exception):
    pass


def on_alarm(*_):
    raise Timeout()


signal.signal(signal.SIGALRM, on_alarm)


def run_seed(seed):
    r = random.Random(seed)
    g = Gen(r)
    s = gridcalc.Sheet()
    trace = []
    for _ in range(r.randint(15, 45)):
        k = r.random()
        try:
            if k < 0.72:
                a = f"{col(r.randrange(6))}{r.randrange(1, 11)}"
                raw = g.raw()
                trace.append(["set", a, raw, sorted(s.set(a, raw))])
            elif k < 0.8:
                c1, r1 = r.randrange(5), r.randrange(1, 8)
                c2, r2 = r.randrange(c1, min(c1 + 2, 6)), r.randrange(r1, min(r1 + 2, 10))
                dc, dr = c1 + r.randrange(0, 2), r1 + r.randrange(0, 3)
                src = f"{col(c1)}{r1}:{col(c2)}{r2}" if (c1, r1) != (c2, r2) else f"{col(c1)}{r1}"
                trace.append(["copy", src, f"{col(dc)}{dr}", sorted(s.copy(src, f"{col(dc)}{dr}"))])
            else:
                op = r.choice(["insert_rows", "delete_rows", "insert_cols", "delete_cols"])
                at = r.randrange(1, 9) if "rows" in op else r.randrange(1, 6)
                cnt = r.choice([1, 1, 2])
                getattr(s, op)(at, cnt)
                trace.append([op, at, cnt])
        except Timeout:
            raise
        except Exception as e:  # implementation raised
            trace.append(["raised", type(e).__name__])
    snap = {}
    for c in COLS:
        for row in range(1, NROW + 1):
            a = f"{c}{row}"
            raw = s.get_raw(a)
            if raw != "" or s.get(a) is not None:
                snap[a] = [raw, norm(s.get(a))]
    return {"trace": trace, "snap": snap}


res = {}
for seed in range(1, SEEDS + 1):
    signal.alarm(10)
    try:
        res[seed] = run_seed(seed)
    except Timeout:
        res[seed] = {"crash": "timeout"}
    except Exception as e:
        res[seed] = {"crash": f"{type(e).__name__}: {e}"[:300]}
    finally:
        signal.alarm(0)
json.dump(res, open(out_path, "w"))
print("done", len(res))
