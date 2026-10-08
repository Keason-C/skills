"""Supplementary scalability probe: python3 -I scale_py.py <impl_dir> <scenario>  -> prints ms"""
import sys, time
sys.path.insert(0, sys.argv[1]); sys.setrecursionlimit(10000)
import gridcalc
name = sys.argv[2]; s = gridcalc.Sheet()

def chain_100k():
    s.set("A1", "1")
    for i in range(2, 100001): s.set(f"A{i}", f"=A{i-1}+1")
    t = time.perf_counter(); s.set("A1", "2"); assert s.get("A100000") == 100001.0; return t

def sum_100k_edits():
    for i in range(1, 100001): s.set(f"A{i}", str(i))
    s.set("B1", "=SUM(A1:A100000)")
    t = time.perf_counter()
    for k in range(300): s.set(f"A{k*7+1}", "0")
    return t

def range_index_2k_formulas():
    for i in range(1, 2001): s.set(f"A{i}", "1")
    for i in range(1, 2001): s.set(f"B{i}", f"=SUM(A1:A{i})")
    t = time.perf_counter()
    for k in range(2000): s.set(f"D{k+1}", str(k))   # unrelated edits
    return t

def fanout_20k():
    s.set("A1", "1")
    for i in range(1, 20001): s.set(f"B{i}", "=A1*2")
    t = time.perf_counter()
    for k in range(20): s.set("A1", str(k))
    return t

def insert_rows_50k():
    for i in range(1, 25001): s.set(f"A{i}", str(i)); s.set(f"B{i}", f"=A{i}+A{i+1}")
    t = time.perf_counter()
    for k in range(10): s.insert_rows(100 * k + 1, 1)
    s.delete_rows(5, 3)
    return t

def copy_block_100x50():
    for r in range(1, 101):
        for c in range(1, 51):
            col = ""; n = c
            while n: n, rem = divmod(n - 1, 26); col = chr(65 + rem) + col
            s.set(f"{col}{r}", f"={col}{r+1}+1" if r < 100 else "1")
    t = time.perf_counter(); s.copy("A1:AX100", "A201"); return t

t0 = time.perf_counter(); t = globals()[name](); t1 = time.perf_counter()
print(f"{(t1 - t) * 1000:.0f} {(t1 - t0) * 1000:.0f}")
