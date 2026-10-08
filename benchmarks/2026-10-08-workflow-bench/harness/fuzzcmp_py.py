import json, re, sys
RANGE = re.compile(r"(\$?)([A-Z]+)(\$?)(\d+):(\$?)([A-Z]+)(\$?)(\d+)")
def cnum(c):
    n = 0
    for ch in c: n = n*26 + ord(ch)-64
    return n
def canon(raw):
    def f(m):
        a = (m.group(1), m.group(2), m.group(3), m.group(4)); b = (m.group(5), m.group(6), m.group(7), m.group(8))
        c1, c2 = sorted([(cnum(a[1]), a[0], a[1]), (cnum(b[1]), b[0], b[1])])
        r1, r2 = sorted([(int(a[3]), a[2]), (int(b[3]), b[2])])
        return f"{c1[1]}{c1[2]}{r1[1]}{r1[0]}:{c2[1]}{c2[2]}{r2[1]}{r2[0]}"
    return RANGE.sub(f, raw) if raw.startswith("=") else raw
ref = json.load(open(sys.argv[1])); cand = json.load(open(sys.argv[2])); show = int(sys.argv[3]) if len(sys.argv) > 3 else 0
full = 0; cells = cell_bad = val_hard = val_errcode = raw_bad = trace_bad = crashes = 0; shown = 0
for k, a in ref.items():
    b = cand.get(k, {"crash": "missing"})
    if "crash" in a: continue
    if "crash" in b: crashes += 1; continue
    ok = True
    if a["trace"] != b["trace"]:
        trace_bad += 1; ok = False
    for addr in set(a["snap"]) | set(b["snap"]):
        x = a["snap"].get(addr, ["", ["NoneType", None]]); y = b["snap"].get(addr, ["", ["NoneType", None]])
        x = [canon(x[0]), x[1]]; y = [canon(y[0]), y[1]]
        cells += 1
        if x == y: continue
        cell_bad += 1; ok = False
        if x[0] != y[0]: raw_bad += 1
        if x[1] != y[1]:
            if x[1][0] == "err" and y[1][0] == "err": val_errcode += 1
            else: val_hard += 1
        if shown < show:
            shown += 1; print(f"seed {k} {addr}: ref={x} cand={y}")
    full += ok
n = len(ref)
print(json.dumps({"seeds": n, "seed_exact_pct": round(100*full/n, 1), "crash_seeds": crashes, "trace_mismatch_seeds": trace_bad,
                  "cells": cells, "cell_mismatch": cell_bad, "value_hard_mismatch": val_hard, "value_errcode_only": val_errcode, "raw_mismatch": raw_bad}))
