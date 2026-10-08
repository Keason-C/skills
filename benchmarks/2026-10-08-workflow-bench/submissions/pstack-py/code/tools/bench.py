import time, sys
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from gridcalc import Sheet
s = Sheet(); rows = 5000
t = time.perf_counter()
for r in range(1, rows + 1):
    s.set(f"A{r}", str(r)); s.set(f"B{r}", f"=A{r}+1"); s.set(f"C{r}", f"=B{r}*2"); s.set(f"D{r}", "'txt")
    s.set(f"E{r}", f"=IF(A{r}>2,C{r},0)"); s.set(f"F{r}", f"=SUM(A{r}:C{r})"); s.set(f"G{r}", "1")
    s.set(f"H{r}", "2.5"); s.set(f"I{r}", "TRUE"); s.set(f"J{r}", f"=H{r}*{r}")
s.set("L1", f"=SUM(B1:B{rows})")
print("build 50k", round(time.perf_counter() - t, 3))
t = time.perf_counter()
for i in range(5000):
    s.set(f"G{(i*7)%rows+1}", str(i + 100))
print("5000 unrelated edits", round(time.perf_counter() - t, 3))
t = time.perf_counter()
for i in range(200):
    s.set(f"A{(i*7)%rows+1}", str(i + 100))
print("200 edits feeding SUM(B1:B5000)", round(time.perf_counter() - t, 3))
t = time.perf_counter(); s.insert_rows(10, 2); print("insert_rows on 50k", round(time.perf_counter() - t, 3))
t = time.perf_counter(); s.delete_cols(4, 1); print("delete_cols on 50k", round(time.perf_counter() - t, 3))
t = time.perf_counter(); s.copy("A1:J1000", "M1"); print("copy 10k block", round(time.perf_counter() - t, 3))
s2 = Sheet(); n = 50000
t = time.perf_counter()
s2.set("A1", "1")
for r in range(2, n + 1): s2.set(f"A{r}", f"=A{r-1}+1")
print("chain build 50k", round(time.perf_counter() - t, 3))
t = time.perf_counter(); ch = s2.set("A1", "2"); print("chain head edit", len(ch), s2.get(f"A{n}"), round(time.perf_counter() - t, 3))
t = time.perf_counter(); s2.set("A1", f"=A{n}"); print("chain closed into cycle", s2.get("A100"), round(time.perf_counter() - t, 3))
