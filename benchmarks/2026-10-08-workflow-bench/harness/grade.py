"""Grade every finished run.  python3 grade.py [run ...]   -> grading/<run>/report.json

Per run: hidden acceptance tests (per category), contestant's own tests, coverage, static metrics.
Runs on a fresh copy of each work tree so grading never mutates the contestant's repo.
"""
import json, os, re, shutil, subprocess, sys, xml.etree.ElementTree as ET
from pathlib import Path

BENCH = Path(__file__).resolve().parent
GRADING = BENCH / "grading"
RUNS = ["matt-py", "grill-py", "pstack-py", "matt-ts", "grill-ts", "pstack-ts"]


def sh(cmd, cwd, timeout=1800, env=None):
    e = dict(os.environ, **(env or {}))
    try:
        p = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=timeout, env=e)
        return p.returncode, p.stdout + p.stderr
    except subprocess.TimeoutExpired as ex:
        return "timeout", (ex.stdout or b"").decode(errors="replace") if isinstance(ex.stdout, bytes) else str(ex.stdout)


def fresh_copy(run):
    src = BENCH / "runs" / run / "work"
    dst = GRADING / run / "work"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, symlinks=True, ignore=shutil.ignore_patterns(".pytest_cache", "__pycache__"))
    return dst


def junit_by_file(xml_path):
    cats = {}
    root = ET.parse(xml_path).getroot()
    for tc in root.iter("testcase"):
        f = (tc.get("classname") or "").split(".")
        cat = next((x for x in f if x.startswith("test_")), f[0] if f else "?")
        failed = any(ch.tag in ("failure", "error") for ch in tc)
        skipped = any(ch.tag == "skipped" for ch in tc)
        c = cats.setdefault(cat, {"pass": 0, "fail": 0, "failed": []})
        if failed or skipped:
            c["fail"] += 1
            c["failed"].append(tc.get("name"))
        else:
            c["pass"] += 1
    return cats


def git_stats(work):
    _, log = sh("git log --oneline", work)
    _, status = sh("git status --porcelain", work)
    return {"commits": max(0, len(log.strip().splitlines()) - 1), "uncommitted_files": len(status.strip().splitlines())}


def loc(paths):
    n = 0
    for p in paths:
        for line in p.read_text(errors="replace").splitlines():
            s = line.strip()
            if s and not s.startswith(("#", "//", "*", "/*")):
                n += 1
    return n


def lizard_stats(files):
    if not files:
        return {}
    rc, out = sh("lizard --csv " + " ".join(f"'{f}'" for f in files), BENCH)
    funcs = []
    for line in out.splitlines():
        parts = line.split(",")
        if len(parts) > 3 and parts[0].isdigit():
            funcs.append((int(parts[0]), int(parts[1])))  # nloc, ccn
    if not funcs:
        return {}
    ccn = sorted(c for _, c in funcs)
    return {"functions": len(funcs), "avg_ccn": round(sum(ccn) / len(ccn), 2), "max_ccn": ccn[-1],
            "ccn_over_10": sum(c > 10 for c in ccn), "max_fn_nloc": max(n for n, _ in funcs),
            "avg_fn_nloc": round(sum(n for n, _ in funcs) / len(funcs), 1)}


def grade_py(run):
    work = fresh_copy(run)
    out = GRADING / run
    rep = {"run": run}
    src = [p for p in (work / "gridcalc").rglob("*.py")]
    tests = [p for p in work.rglob("test*.py") if not any(x in ("gridcalc", ".git") or x.startswith((".wt", ".audit")) for x in p.relative_to(work).parts)]
    rep["loc_src"], rep["loc_tests"] = loc(src), loc(tests)
    rep["lizard"] = lizard_stats([str(p) for p in src])
    rc, txt = sh(f"ruff check --select E,F,W,B,SIM,C90 --output-format concise gridcalc | tail -n 3", work)
    rep["ruff_tail"] = txt.strip()[-300:]
    rc, txt = sh("ruff check --select E,F,W,B,SIM,C90 --statistics gridcalc", work)
    rep["ruff_issues"] = sum(int(m.group(1)) for m in re.finditer(r"^\s*(\d+)\s", txt, re.M))
    # hidden acceptance
    hid = BENCH / "hidden/py/tests"
    rc, txt = sh(f"python3 -m pytest {hid} -q -p no:cacheprovider --timeout 120 --junitxml={out}/hidden.xml -o junit_family=xunit1",
                 out, timeout=3600, env={"PYTHONPATH": str(work)})
    (out / "hidden.txt").write_text(txt)
    rep["hidden"] = junit_by_file(out / "hidden.xml") if (out / "hidden.xml").exists() else {"error": txt[-2000:]}
    # own tests + coverage
    rc, txt = sh(f"python3 -m pytest -q -p no:cacheprovider --timeout 600 --junitxml={out}/own.xml", work, timeout=3600)
    (out / "own.txt").write_text(txt)
    rep["own_tests"] = junit_by_file(out / "own.xml") if (out / "own.xml").exists() else {"error": txt[-1500:]}
    sh("python3 -m coverage run --branch --source=gridcalc -m pytest -q -p no:cacheprovider --timeout 600", work, timeout=3600)
    rc, txt = sh("python3 -m coverage report --format=total", work)
    rep["own_coverage_pct"] = txt.strip().splitlines()[-1] if txt.strip() else None
    rep["git"] = git_stats(BENCH / "runs" / run / "work")
    return rep


VITEST_HIDDEN = """import { defineConfig } from "vitest/config";
export default defineConfig({ test: { include: ["hidden-test/**/*.test.ts"], testTimeout: 15000, hookTimeout: 15000,
  reporters: ["default", "junit"], outputFile: { junit: "%s" } } });
"""


def grade_ts(run):
    work = fresh_copy(run)
    out = GRADING / run
    rep = {"run": run}
    sh("npm i --no-save --no-audit --no-fund @vitest/coverage-v8@3.2.7", work, timeout=600)
    src = [p for p in (work / "src").rglob("*.ts")]
    tests = [p for p in work.rglob("*.test.ts") if not any(x == "node_modules" or x.startswith((".wt", ".audit", "hidden")) for x in p.relative_to(work).parts)]
    rep["loc_src"], rep["loc_tests"] = loc(src), loc(tests)
    rep["lizard"] = lizard_stats([str(p) for p in src])
    rc, txt = sh("npx tsc --noEmit -p .", work)
    rep["typecheck_ok"], rep["typecheck_tail"] = rc == 0, txt.strip()[-600:]
    any_count = sum(len(re.findall(r"\bany\b", p.read_text())) for p in src)
    rep["any_count"] = any_count
    # hidden acceptance
    shutil.copytree(BENCH / "hidden/ts/tests", work / "hidden-test", ignore=shutil.ignore_patterns("_scratch", "README.md"))
    (work / "hidden.vitest.config.ts").write_text(VITEST_HIDDEN % (out / "hidden.xml"))
    rc, txt = sh("npx vitest run --config hidden.vitest.config.ts", work, timeout=3600)
    (out / "hidden.txt").write_text(txt)
    rep["hidden"] = junit_by_file_ts(out / "hidden.xml") if (out / "hidden.xml").exists() else {"error": txt[-2000:]}
    rep["hidden_unhandled"] = "Unhandled" in txt
    shutil.rmtree(work / "hidden-test"); (work / "hidden.vitest.config.ts").unlink()
    # own tests (+coverage if the provider is installable)
    rc, txt = sh(f"npx vitest run --reporter=default --reporter=junit --outputFile.junit={out}/own.xml", work, timeout=3600)
    (out / "own.txt").write_text(txt)
    rep["own_tests"] = junit_by_file_ts(out / "own.xml") if (out / "own.xml").exists() else {"error": txt[-1500:]}
    sh("npx vitest run --coverage.enabled --coverage.provider=v8 --coverage.include='src/**' --coverage.reporter=json-summary "
       f"--coverage.reportsDirectory={out}/cov", work, timeout=3600)
    cov = out / "cov/coverage-summary.json"
    rep["own_coverage_pct"] = json.loads(cov.read_text())["total"]["lines"]["pct"] if cov.exists() else None
    rep["git"] = git_stats(BENCH / "runs" / run / "work")
    return rep


def junit_by_file_ts(xml_path):
    cats = {}
    root = ET.parse(xml_path).getroot()
    for tc in root.iter("testcase"):
        cls = tc.get("classname") or "?"
        cat = Path(cls.split(" ")[0]).name.replace(".test.ts", "")
        failed = any(ch.tag in ("failure", "error") for ch in tc)
        skipped = any(ch.tag == "skipped" for ch in tc)
        c = cats.setdefault(cat, {"pass": 0, "fail": 0, "failed": []})
        if failed or skipped:
            c["fail"] += 1
            c["failed"].append(tc.get("name"))
        else:
            c["pass"] += 1
    return cats


def main():
    runs = sys.argv[1:] or RUNS
    for run in runs:
        (GRADING / run).mkdir(parents=True, exist_ok=True)
        rep = grade_py(run) if run.endswith("-py") else grade_ts(run)
        (GRADING / run / "report.json").write_text(json.dumps(rep, indent=2, ensure_ascii=False))
        h = rep.get("hidden", {})
        tot = sum(v.get("pass", 0) for v in h.values() if isinstance(v, dict))
        n = tot + sum(v.get("fail", 0) for v in h.values() if isinstance(v, dict))
        print(f"{run}: hidden {tot}/{n}", flush=True)


if __name__ == "__main__":
    main()
