"""Blind code-quality judging.  python3 judge.py <py|ts> [n_judges]

Packs each contestant's source + tests (process artifacts stripped) as anonymous Submission X/Y/Z, with a
different random label mapping per judge, and asks `claude -p` (no tools) for rubric scores. Writes
judging/<task>/judge-<i>.json and the de-anonymised mapping.
"""
import json, random, re, subprocess, sys
from pathlib import Path

BENCH = Path(__file__).resolve().parent
CONTESTANTS = ["matt", "grill", "pstack"]
MODELS = ["claude-opus-5-5", "claude-fable-5-1", "claude-opus-5-5", "claude-fable-5-1"]
SKIP_DIRS = {".git", "node_modules", ".scratch", ".audit", "docs", "__pycache__", ".pytest_cache", ".wt-impl", "coverage"}
SKIP_FILES = {"CLAUDE.md", "todo.md", "BRIEF.md", "package-lock.json", "GLOSSARY.md", "AGENTS.md", ".gitignore"}


def pack(task, contestant):
    work = BENCH / "runs" / f"{contestant}-{task}" / "work"
    exts = {".py"} if task == "py" else {".ts"}
    parts = []
    for p in sorted(work.rglob("*")):
        rel = p.relative_to(work)
        if any(x in SKIP_DIRS or x.startswith(".wt") for x in rel.parts) or not p.is_file():
            continue
        if p.name in SKIP_FILES or (p.suffix not in exts and p.name != "NOTES.md") or p.name.endswith(".config.ts"):
            continue
        text = p.read_text(errors="replace")
        # strip workflow fingerprints that would de-anonymise the submission
        text = re.sub(r"(?i)(pstack|poteto|matt pocock|grill(ing)?|to-spec|\.scratch|\.audit)", "[redacted]", text)
        parts.append(f"=== FILE: {rel} ===\n{text}")
    return "\n\n".join(parts)


RUBRIC = """You are a principal engineer doing a blind review of three independent implementations of the same
specification. Judge only what is in front of you. All three already pass a large hidden acceptance suite, so
focus on engineering quality rather than re-deriving correctness from scratch (but do flag real bugs you see).

Score each submission 1-10 (10 = exemplary, 5 = acceptable, use the full range, ties allowed) on:
1. design: architecture, module boundaries, data structures, algorithmic choices (incl. scalability)
2. readability: naming, clarity, function size, comments where useful, ease of onboarding
3. maintainability: how safely could a new engineer extend it (e.g. add a function / a new event); coupling; duplication
4. robustness: edge-case handling, invariants, failure modes, resource hygiene; any real bugs you spot (list them)
5. tests: quality of the submission's own tests (behavioural, meaningful assertions, coverage of tricky cases, not tautological)
6. docs: NOTES.md / docstrings: does it explain design and the decisions it made
Then give overall (1-10) and a ranking best-to-worst.

Reply with ONLY a JSON object, no prose before or after:
{"scores": {"X": {"design":n,"readability":n,"maintainability":n,"robustness":n,"tests":n,"docs":n,"overall":n,
 "bugs":["..."],"strengths":["..."],"weaknesses":["..."]}, "Y": {...}, "Z": {...}}, "ranking": ["X","Y","Z"],
 "rationale": "3-5 sentences"}
"""


def main():
    task = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    spec = (BENCH / "tasks" / ("py-gridcalc" if task == "py" else "ts-taskflow") / "starter/BRIEF.md").read_text()
    packs = {c: pack(task, c) for c in CONTESTANTS}
    outdir = BENCH / "judging" / task
    outdir.mkdir(parents=True, exist_ok=True)
    rnd = random.Random(20261008 + (0 if task == "py" else 1))
    for i in range(n):
        labels = ["X", "Y", "Z"]
        order = CONTESTANTS[:]
        rnd.shuffle(order)
        mapping = dict(zip(labels, order))
        body = "\n\n".join(f"########## SUBMISSION {lab} ##########\n{packs[mapping[lab]]}" for lab in labels)
        prompt = f"{RUBRIC}\n\n<SPEC>\n{spec}\n</SPEC>\n\n{body}\n\nNow reply with the JSON object only."
        out = outdir / f"judge-{i}.json"
        if out.exists():
            continue
        p = subprocess.run(["claude", "-p", "--model", MODELS[i % len(MODELS)], "--tools", "", "--strict-mcp-config",
                            "--output-format", "text"], input=prompt, capture_output=True, text=True, timeout=3600,
                           cwd=str(outdir))
        txt = p.stdout.strip()
        m = re.search(r"\{.*\}", txt, re.S)
        try:
            data = json.loads(m.group(0)) if m else None
        except json.JSONDecodeError:
            data = None
        out.write_text(json.dumps({"model": MODELS[i % len(MODELS)], "mapping": mapping, "result": data,
                                   "raw": None if data else txt[-4000:]}, indent=2, ensure_ascii=False))
        print(task, i, mapping, "ok" if data else "PARSE-FAIL", flush=True)


if __name__ == "__main__":
    main()
