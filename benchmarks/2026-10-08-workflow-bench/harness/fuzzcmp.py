import json, sys
ref = json.load(open(sys.argv[1])); cand = json.load(open(sys.argv[2]))
rt, ct = ref["traces"], cand["traces"]
diff = [k for k in rt if rt[k] != ct.get(k)]
out = {"seeds": len(rt), "mismatch": len(diff), "agree_pct": round(100 * (len(rt) - len(diff)) / len(rt), 1),
       "unhandled": cand["unhandled"], "crashes": sum(1 for v in ct.values() if "crash" in v),
       "leaked_timer_seeds": sum(1 for v in ct.values() if v.get("pendingTimers"))}
print(json.dumps(out))
if len(sys.argv) > 3:
    for k in diff[: int(sys.argv[3])]:
        a, b = rt[k], ct[k]
        print("--- seed", k)
        if "crash" in b: print(" crash", b["crash"][:300]); continue
        la, lb = a["log"], b["log"]
        i = next((i for i in range(min(len(la), len(lb))) if la[i] != lb[i]), min(len(la), len(lb)))
        print(" ref :", la[max(0,i-2):i+4]); print(" cand:", lb[max(0,i-2):i+4])
        if a["states"] != b["states"]: print(" states ref", a["states"], "cand", b["states"])
