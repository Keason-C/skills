"""Behaviour tests for .claude/hooks/stop-wait-what-gate.py"""
import json, os, subprocess, sys, tempfile, uuid

HOOK = "/home/user/skills/.claude/hooks/stop-wait-what-gate.py"

def user(text="hi", **kw):
    e = {"type": "user", "uuid": str(uuid.uuid4()),
         "message": {"role": "user", "content": [{"type": "text", "text": text}]}}
    e.update(kw); return e

def asst(tools=(), **kw):
    e = {"type": "assistant", "uuid": str(uuid.uuid4()),
         "message": {"role": "assistant", "model": "claude-opus-5",
                     "content": [{"type": "tool_use", "name": n, "input": i} for n, i in tools]}}
    e.update(kw); return e

def run(entries, env=None, home=None):
    fd, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(fd, "w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")
    e2 = dict(os.environ); e2["HOME"] = home or tempfile.mkdtemp(); e2.update(env or {})
    p = subprocess.run([sys.executable, HOOK], input=json.dumps({
        "session_id": "s", "transcript_path": path, "hook_event_name": "Stop",
        "stop_hook_active": False}), capture_output=True, text=True, env=e2)
    out = p.stdout.strip()
    return ("BLOCK" if out else "ALLOW"), out, p.stderr.strip()

fails = []
def check(name, got, want):
    ok = got == want
    print(("PASS " if ok else "FAIL ") + name + "  got=" + got + " want=" + want)
    if not ok: fails.append(name)

SKILL = ("Skill", {"skill": "wait-what"})
OTHER = ("Skill", {"skill": "grilling"})
BASH  = ("Bash", {"command": "ls"})

# 1. plain turn, no skill call
check("no skill call -> block", run([user(), asst([BASH])])[0], "BLOCK")
# 2. skill called this turn
check("Skill(wait-what) -> allow", run([user(), asst([BASH]), asst([SKILL])])[0], "ALLOW")
# 3. a different skill does not satisfy
check("Skill(other) -> block", run([user(), asst([OTHER])])[0], "BLOCK")
# 4. user typed the slash command
check("user /wait-what -> allow", run([user("/wait-what"), asst([BASH])])[0], "ALLOW")
# 5. SlashCommand tool
check("SlashCommand tool -> allow",
      run([user(), asst([("SlashCommand", {"command": "/wait-what"})])])[0], "ALLOW")
# 6. skill call belongs to the PREVIOUS turn
check("stale skill call -> block",
      run([user(), asst([SKILL]), user("next question"), asst([BASH])])[0], "BLOCK")
# 7. tool results between boundary and skill call must not shift the boundary
check("tool result is not a boundary",
      run([user(), asst([BASH]), user(toolUseResult={"ok": 1}), asst([SKILL])])[0], "ALLOW")
# 8. subagent skill call does not count
check("sidechain skill call -> block",
      run([user(), asst([SKILL], isSidechain=True)])[0], "BLOCK")
# 9. kill switch
check("WAIT_WHAT_GATE=0 -> allow", run([user(), asst([BASH])], env={"WAIT_WHAT_GATE": "0"})[0], "ALLOW")
# 10. configurable skill name
check("WAIT_WHAT_GATE_SKILL -> allow",
      run([user(), asst([OTHER])], env={"WAIT_WHAT_GATE_SKILL": "grilling"})[0], "ALLOW")
# 11. per-turn cap releases after N blocks
home = tempfile.mkdtemp(); t = [user(), asst([BASH])]
seq = [run(t, home=home)[0] for _ in range(3)]
check("cap releases on 3rd try", ",".join(seq), "BLOCK,BLOCK,ALLOW")
# 12. counter resets on a new turn
t2 = t + [user("new"), asst([BASH])]
check("new turn re-arms the gate", run(t2, home=home)[0], "BLOCK")
# 13. never trap: unreadable transcript / bad stdin
p = subprocess.run([sys.executable, HOOK], input='{"transcript_path":"/nope/x.jsonl"}',
                   capture_output=True, text=True)
check("missing transcript -> allow", "BLOCK" if p.stdout.strip() else "ALLOW", "ALLOW")
p = subprocess.run([sys.executable, HOOK], input="not json", capture_output=True, text=True)
check("bad stdin -> allow", "BLOCK" if p.stdout.strip() else "ALLOW", "ALLOW")
# 14. malformed transcript lines are tolerated
fd, path = tempfile.mkstemp(suffix=".jsonl")
with os.fdopen(fd, "w") as f:
    f.write(json.dumps(user()) + "\n{ broken\n" + json.dumps(asst([SKILL])) + "\n")
p = subprocess.run([sys.executable, HOOK], input=json.dumps({"transcript_path": path}),
                   capture_output=True, text=True, env={**os.environ, "HOME": tempfile.mkdtemp()})
check("broken jsonl line tolerated", "BLOCK" if p.stdout.strip() else "ALLOW", "ALLOW")

# block payload shape
_, out, _ = run([user(), asst([BASH])])
d = json.loads(out)
check("block payload shape", str(d.get("decision") == "block" and bool(d.get("reason"))), "True")
print("\n%d failed" % len(fails))
sys.exit(1 if fails else 0)
