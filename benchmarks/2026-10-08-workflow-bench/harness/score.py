"""Composite scoring -> results.json. Weights are explicit so the reader can re-weight."""
import json
from pathlib import Path
B = Path(__file__).resolve().parent
W = {"correctness": 30, "robustness": 15, "scalability": 10, "quality": 25, "tests": 10, "efficiency": 10}
C = ["matt", "grill", "pstack"]
DEFECTS = {  # verified by repro (hidden/*/repro): (severity_points, description)
    "py": {"matt": [], "grill": [], "pstack": []},
    "ts": {"matt": [(5, "20k 依赖链 add 时递归找环导致栈溢出 (RangeError)")],
           "grill": [(1, "超时后 abort 监听器内 cancel，仍补发一次 retry 事件 (重入边界)")],
           "pstack": []},
}
res = {}
for task in ("py", "ts"):
    judge = json.load(open(B / f"judging/{task}/summary.json"))
    scale = {c: json.load(open(B / f"fuzzout/scale-{c}-{task}.json")) for c in C}
    rows = {}
    for c in C:
        run = f"{c}-{task}"
        g = json.load(open(B / f"grading/{run}/report.json")); p = json.load(open(B / f"grading/{run}/process.json"))
        cats = [v for v in g["hidden"].values()]
        hidden_pct = 100 * sum(v["pass"] / (v["pass"] + v["fail"]) for v in cats) / len(cats)
        hp, hn = sum(v["pass"] for v in cats), sum(v["pass"] + v["fail"] for v in cats)
        if task == "py":
            fz = json.loads(__import__("subprocess").run(["python3", "fuzzcmp_py.py", "fuzzout/ref-py.json", f"fuzzout/{run}.json"],
                            capture_output=True, text=True, cwd=B).stdout.strip().splitlines()[-1])
            fuzz_pct = fz["seed_exact_pct"]
        else:
            fz = json.loads(__import__("subprocess").run(["python3", "fuzzcmp.py", "fuzzout/ref-ts.json", f"fuzzout/{run}.json"],
                            capture_output=True, text=True, cwd=B).stdout.strip().splitlines()[-1])
            fuzz_pct = fz["agree_pct"]
        sev = sum(s for s, _ in DEFECTS[task][c])
        rows[c] = dict(hidden=f"{hp}/{hn}", hidden_pct=round(hidden_pct, 2), fuzz_pct=fuzz_pct, defects=DEFECTS[task][c],
                       defect_points=sev, scale=scale[c], judge=judge[c]["avg"], judge_ranks=judge[c]["ranks"],
                       own_tests=sum(v["pass"] for v in g["own_tests"].values()),
                       own_fail=sum(v["fail"] for v in g["own_tests"].values()),
                       coverage=float(str(g["own_coverage_pct"]).strip("%")), loc_src=g["loc_src"], loc_tests=g["loc_tests"],
                       lizard=g.get("lizard"), commits=g["git"]["commits"], cost=p["cost_usd"], wall_min=round(p["wall_secs"] / 60, 1),
                       tool_calls=p["tool_calls_total"], subagents=p["subagents"], ask_po=p["ask_po_calls"], po_relays=p["po_relays"],
                       turns=p["turns"], models=list(p["model_tokens"]), skills=p["skills"],
                       ruff=g.get("ruff_issues"), typecheck=g.get("typecheck_ok"))
    def tval(v):
        v = v[0] if isinstance(v, list) else v
        return None if isinstance(v, str) else float(v)
    scen = list(scale["matt"].keys())
    best = {s: min(tval(scale[c][s]) for c in C if tval(scale[c][s]) is not None) for s in scen}
    mincost = min(rows[c]["cost"] for c in C); minwall = min(rows[c]["wall_min"] for c in C)
    for c in C:
        r = rows[c]
        sc = {}
        sc["correctness"] = W["correctness"] * r["hidden_pct"] / 100
        sc["robustness"] = max(0.0, W["robustness"] * (2 / 3) * r["fuzz_pct"] / 100 + W["robustness"] / 3 - r["defect_points"])
        sc["scalability"] = W["scalability"] * sum((best[s] / tval(r["scale"][s])) if tval(r["scale"][s]) else 0 for s in scen) / len(scen)
        sc["quality"] = W["quality"] * (sum(r["judge"][k] for k in ("design", "readability", "maintainability", "robustness")) / 4) / 10
        sc["tests"] = W["tests"] * (0.7 * r["judge"]["tests"] / 10 + 0.3 * r["coverage"] / 100)
        sc["efficiency"] = W["efficiency"] * (0.5 * mincost / r["cost"] + 0.5 * minwall / r["wall_min"])
        r["score"] = {k: round(v, 2) for k, v in sc.items()}
        r["total"] = round(sum(sc.values()), 1)
    res[task] = rows
res["weights"] = W
json.dump(res, open(B / "results.json", "w"), indent=2, ensure_ascii=False)
for task in ("py", "ts"):
    print("==", task)
    for c in C:
        r = res[task][c]; print(f"{c:7} total {r['total']:5}  ", r["score"], f"cost ${r['cost']} wall {r['wall_min']}m")
print("== overall")
for c in C: print(c, round((res['py'][c]['total'] + res['ts'][c]['total']) / 2, 1))
