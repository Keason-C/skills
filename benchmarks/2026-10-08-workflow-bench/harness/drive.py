"""Drive one contestant on one task:  python3 drive.py <matt|grill|pstack> <py|ts>

Each turn is a `claude -p` call inside arena.sh (private namespaces). Questions the agent leaves for
"the user" at the end of a turn are relayed to the product-owner oracle and its answer is sent back
with --resume, so every workflow gets the same simulated user.
"""
import json, os, re, shutil, subprocess, sys, time, urllib.request
from pathlib import Path

BENCH = Path(__file__).resolve().parent
MODEL = "claude-opus-5-5"
TURN_TIMEOUT = 4 * 3600
MAX_RELAYS = 8

ALLOWED = ["Read", "Glob", "Grep", "Skill", "Agent", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet",
           "TaskOutput", "TodoWrite", "Edit", "Write"] + [f"Bash({c}:*)" for c in (
    "python3 python pytest npm npx node tsc vitest git ls cat head tail wc mkdir mv cp touch find grep sed awk "
    "sort uniq diff echo printf ask-po time timeout cd pwd which test true env tee xargs").split()]

TOOLCHAIN = {
    "py": "Python 3.13 (standard library only for the library itself); run tests with `python3 -m pytest`.",
    "ts": "Node 22 + TypeScript; `npm test` (vitest) and `npm run typecheck` (tsc) are set up and "
          "node_modules is already installed (there is no network for installing packages).",
}

def common(task):
    return f"""Build the library specified in /arena/BRIEF.md. The starter code and toolchain are already in /arena (a git repo). {TOOLCHAIN[task]}

Working conditions:
- You are working unattended: the user has gone to bed and will review the result in the morning. Do not stop to wait for the user.
- The user's product owner is reachable from the shell: `ask-po "your question"` prints their answer (it can take a minute). Use it for requirement/behaviour questions the brief leaves open.
- Work only inside /arena. There is no internet access.
- Commit your finished work to the git repo in /arena.
- When the whole job is complete, end your final message with a line containing exactly BENCH-DONE."""

MATT_CLAUDE_MD = """## Agent skills

### Issue tracker

Issues and specs live as local markdown files under `.scratch/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default five-role vocabulary (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.
"""


def log(run_dir, msg):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(run_dir / "driver.log", "a") as f:
        f.write(line + "\n")


def setup(contestant, task, run_dir):
    if run_dir.exists():
        raise SystemExit(f"{run_dir} exists")
    work, home = run_dir / "work", run_dir / "home"
    starter = BENCH / "tasks" / ("py-gridcalc" if task == "py" else "ts-taskflow") / "starter"
    shutil.copytree(starter, work, symlinks=True)
    (home / ".claude/skills").mkdir(parents=True)
    (work / ".gitignore").write_text("node_modules/\n__pycache__/\n*.pyc\n.pytest_cache/\n")
    if contestant in ("matt", "grill"):
        for s in (BENCH / "skills/matt").iterdir():
            shutil.copytree(s, home / ".claude/skills" / s.name)
        src = Path.home() / ".claude/skills/setup-matt-pocock-skills"
        (work / "docs/agents").mkdir(parents=True)
        shutil.copy(src / "issue-tracker-local.md", work / "docs/agents/issue-tracker.md")
        shutil.copy(src / "triage-labels.md", work / "docs/agents/triage-labels.md")
        shutil.copy(src / "domain.md", work / "docs/agents/domain.md")
        (work / "CLAUDE.md").write_text(MATT_CLAUDE_MD)
    else:
        shutil.copytree(BENCH / "plugins/pstack", home / "pstack")
    git = lambda *a: subprocess.run(["git", *a], cwd=work, check=True, capture_output=True)
    git("init", "-q", "-b", "main")
    git("-c", "user.name=bench", "-c", "user.email=bench@localhost", "add", "-A")
    git("-c", "user.name=bench", "-c", "user.email=bench@localhost", "commit", "-qm", "starter")
    subprocess.run(["git", "config", "user.name", "dev"], cwd=work, check=True)
    subprocess.run(["git", "config", "user.email", "dev@localhost"], cwd=work, check=True)
    (run_dir / "logs").mkdir()


def turn(contestant, task, run_dir, prompt, session=None):
    n = len(list((run_dir / "logs").glob("turn-*.jsonl"))) + 1
    out = run_dir / "logs" / f"turn-{n:02d}.jsonl"
    (run_dir / "logs" / f"turn-{n:02d}.prompt.txt").write_text(prompt)
    cmd = [str(BENCH / "arena.sh"), str(run_dir), "--", "env", f"BENCH_ID={run_dir.name}", f"BENCH_TASK={task}", "CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1",
           "claude", "-p", "--model", MODEL, "--effort", "high", "--output-format", "stream-json", "--verbose",
           "--strict-mcp-config", "--permission-mode", "auto", "--permission-prompts", "none",
           "--disallowedTools", "WebFetch", "WebSearch"]
    if contestant == "pstack":
        cmd[cmd.index("--strict-mcp-config")+1:cmd.index("--strict-mcp-config")+1] = ["--plugin-dir", "/root/pstack"]
    if session:
        cmd += ["--resume", session]
    log(run_dir, f"turn {n} start (resume={session})")
    t0 = time.time()
    with open(out, "w") as f:
        try:
            p = subprocess.run(cmd, input=prompt, stdout=f, stderr=subprocess.STDOUT, text=True, timeout=TURN_TIMEOUT)
            rc = p.returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
    result = None
    for line in out.read_text().splitlines():
        try:
            ev = json.loads(line)
        except ValueError:
            continue
        if ev.get("type") == "result":
            result = ev
        if ev.get("type") == "system" and ev.get("subtype") == "init" and not session:
            session = ev.get("session_id")
    secs = round(time.time() - t0)
    text = (result or {}).get("result") or ""
    session = (result or {}).get("session_id") or session
    log(run_dir, f"turn {n} end rc={rc} secs={secs} cost={(result or {}).get('total_cost_usd')} "
                 f"subtype={(result or {}).get('subtype')} last={text[-300:]!r}")
    return session, text, result


def ask_po(run_dir, task, message):
    q = ("(This is the developer's latest chat message to you, the user. Reply as the user would, briefly; "
         "answer any questions in it.)\n\n" + message)
    req = urllib.request.Request("http://127.0.0.1:8765/ask", method="POST",
                                 data=json.dumps({"id": run_dir.name + "-relay", "task": task, "question": q}).encode(),
                                 headers={"content-type": "application/json"})
    a = urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=1200).read().decode()
    log(run_dir, f"PO relay answer: {a[:300]!r}")
    return a


def until_done(contestant, task, run_dir, prompt, session=None):
    session, text, _ = turn(contestant, task, run_dir, prompt, session)
    for _ in range(MAX_RELAYS):
        if "BENCH-DONE" in text or not session:
            break
        reply = ask_po(run_dir, task, text or "(no message)")
        session, text, _ = turn(contestant, task, run_dir,
                                reply + "\n\n(Reminder: keep going autonomously until the whole job is complete and "
                                        "committed, then end with BENCH-DONE.)", session)
    return session


def main():
    contestant, task = sys.argv[1], sys.argv[2]
    run_dir = BENCH / "runs" / f"{contestant}-{task}"
    setup(contestant, task, run_dir)
    t0 = time.time()
    if contestant == "matt":
        until_done(contestant, task, run_dir, "/implement " + common(task))
    elif contestant == "pstack":
        until_done(contestant, task, run_dir, "/pstack:poteto-mode " + common(task))
    elif contestant == "grill":
        session, text, _ = turn(contestant, task, run_dir,
            "/grilling I want you to build the library specified in /arena/BRIEF.md (starter code is in /arena). "
            "Before anything is built, grill me about it until we reach a shared understanding.")
        rounds = 0
        while "❓" in text and rounds < 12:
            rounds += 1
            session, text, _ = turn(contestant, task, run_dir, ask_po(run_dir, task, text), session)
        log(run_dir, f"grilling finished after {rounds} answered rounds")
        session, text, _ = turn(contestant, task, run_dir,
            "/to-spec Yes, we have reached a shared understanding. Write the spec now.", session)
        for _ in range(4):
            specs = list((run_dir / "work/.scratch").glob("*/spec.md"))
            if specs:
                break
            session, text, _ = turn(contestant, task, run_dir, ask_po(run_dir, task, text), session)
        specs = list((run_dir / "work/.scratch").glob("*/spec.md"))
        spec = "/arena/" + str(specs[0].relative_to(run_dir / "work")) if specs else "you just wrote"
        log(run_dir, f"spec: {spec}")
        until_done(contestant, task, run_dir, f"/implement the spec at {spec}.\n\n" + common(task), session)
    log(run_dir, f"ALL DONE wall={round(time.time() - t0)}s")


if __name__ == "__main__":
    main()
