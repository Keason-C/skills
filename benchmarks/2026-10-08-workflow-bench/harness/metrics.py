"""Process metrics per run from stream-json logs + driver logs + PO logs -> grading/<run>/process.json"""
import json, re, sys
from collections import Counter
from pathlib import Path

BENCH = Path(__file__).resolve().parent
RUNS = ["matt-py", "grill-py", "pstack-py", "matt-ts", "grill-ts", "pstack-ts"]


def collect(run):
    rd = BENCH / "runs" / run
    m = {"turns": 0, "cost_usd": 0.0, "api_secs": 0, "tool_calls": Counter(), "skills": Counter(), "subagents": 0,
         "subagent_models": Counter(), "model_tokens": {}, "denied": 0, "bench_done": False}
    last = None
    for f in sorted((rd / "logs").glob("turn-*.jsonl")):
        m["turns"] += 1
        for line in f.read_text().splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            msg = e.get("message") if isinstance(e.get("message"), dict) else {}
            content = msg.get("content") if isinstance(msg.get("content"), list) else []
            if e.get("type") == "assistant":
                for c in content:
                    if c.get("type") == "tool_use":
                        m["tool_calls"][c["name"]] += 1
                        if c["name"] == "Skill":
                            m["skills"][c["input"].get("skill", "?")] += 1
                        if c["name"] in ("Agent", "Task"):
                            m["subagents"] += 1
                            m["subagent_models"][c["input"].get("model") or "inherit"] += 1
            if e.get("type") == "user":
                for c in content:
                    if c.get("type") == "tool_result" and c.get("is_error") and "denied" in str(c.get("content"))[:300]:
                        m["denied"] += 1
            if e.get("type") == "result":
                last = e
                if "BENCH-DONE" in (e.get("result") or ""):
                    m["bench_done"] = True
    if last:  # result totals are cumulative across --resume turns of one session
        m["cost_usd"] = last.get("total_cost_usd") or 0
        m["api_secs"] = round((last.get("duration_api_ms") or 0) / 1000)
        for model, u in (last.get("modelUsage") or {}).items():
            m["model_tokens"][model] = {"in": u.get("inputTokens", 0) + u.get("cacheCreationInputTokens", 0),
                                        "out": u.get("outputTokens", 0), "cache_read": u.get("cacheReadInputTokens", 0),
                                        "cost": round(u.get("costUSD", 0), 2)}
    drv = (rd / "driver.log").read_text()
    w = re.search(r"ALL DONE wall=(\d+)s", drv)
    m["wall_secs"] = int(w.group(1)) if w else None
    m["po_relays"] = drv.count("PO relay answer")
    po = BENCH / "po/logs" / f"{run}.jsonl"
    m["ask_po_calls"] = len(po.read_text().splitlines()) if po.exists() else 0
    m["cost_usd"] = round(m["cost_usd"], 2)
    m["tool_calls_total"] = sum(m["tool_calls"].values())
    for k in ("tool_calls", "skills", "subagent_models"):
        m[k] = dict(m[k].most_common())
    return m


if __name__ == "__main__":
    for run in sys.argv[1:] or RUNS:
        if not (BENCH / "runs" / run / "driver.log").exists():
            continue
        m = collect(run)
        (BENCH / "grading" / run).mkdir(parents=True, exist_ok=True)
        (BENCH / "grading" / run / "process.json").write_text(json.dumps(m, indent=2))
        print(run, {k: m[k] for k in ("wall_secs", "cost_usd", "turns", "tool_calls_total", "subagents", "ask_po_calls",
                                      "po_relays", "denied", "bench_done")}, m["skills"], list(m["model_tokens"]))
