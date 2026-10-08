"""Verify judge-claimed defects. python3 -I repro_py.py <impl_dir>"""
import json, signal, sys, time
sys.path.insert(0, sys.argv[1])
import gridcalc
out = {}
def check(name, fn, secs=30):
    def alarm(*_): raise TimeoutError()
    signal.signal(signal.SIGALRM, alarm); signal.alarm(secs)
    try: out[name] = "ok" if fn() else "DEFECT"
    except TimeoutError: out[name] = f"DEFECT: >{secs}s"
    except Exception as e: out[name] = f"DEFECT: {type(e).__name__}: {str(e)[:80]}"
    finally: signal.alarm(0)
def deep(n):
    s = gridcalc.Sheet(); s.set("A1", "=" + "(" * n + "1" + ")" * n); return s.get("A1") == 1.0
check("nesting_1000", lambda: deep(1000))
check("nesting_5000", lambda: deep(5000))
def neg_zero():
    s = gridcalc.Sheet(); s.set("B1", "=-A1&\"\""); s.set("B2", "=ROUND(-0.4,0)&\"\""); return s.get("B1") == "0" and s.get("B2") == "0"
check("negative_zero_prints_0", neg_zero)
def copy_sparse_column():
    s = gridcalc.Sheet(); s.set("A1", "1"); s.set("A500000", "=A1+1"); t = time.time(); s.copy("A1:A1048576", "B1")
    return s.get("B500000") == 2.0 and time.time() - t < 5
check("copy_whole_sparse_column_fast", copy_sparse_column, 60)
def sum_whole_column():
    s = gridcalc.Sheet(); s.set("A1", "2"); s.set("A1048576", "3"); s.set("B1", "=SUM(A:A)" if False else "=SUM(A1:A1048576)")
    t = time.time()
    for i in range(200): s.set("C1", str(i))
    return s.get("B1") == 5.0 and time.time() - t < 2
check("whole_column_range_unrelated_edits_fast", sum_whole_column, 60)
def struct_on_big_sheet():
    s = gridcalc.Sheet()
    for i in range(1, 20001): s.set(f"A{i}", str(i)); s.set(f"B{i}", f"=A{i}*2")
    t = time.time()
    for k in range(20): s.insert_rows(1, 1)
    el = time.time() - t; out["20_inserts_secs"] = round(el, 2)
    return s.get("B20020") == 40000.0 and el < 10
check("20_inserts_on_40k_cells_under_10s", struct_on_big_sheet, 120)
print(json.dumps(out))
