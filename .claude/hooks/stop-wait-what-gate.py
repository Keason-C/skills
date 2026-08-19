#!/usr/bin/env python3
"""Stop hook: refuse to end a turn until the `wait-what` skill has run.

The Stop hook fires when the main loop is about to hand the turn back to the
user. Returning `{"decision": "block", "reason": ...}` on stdout sends the
model back into the same turn with `reason` as new instruction, so the gate is
"answer the user only after re-pitching through /wait-what".

Satisfied by any of, since the last real user message:
  - a `Skill` tool call whose `skill` input is the gated skill
  - a `SlashCommand` tool call for `/<gated skill>`
  - the user typing `/wait-what` themselves

Never traps the session. Every failure path allows, and a per-turn counter caps
the re-prompts below the CLI's global 8-block ceiling, so a model that cannot
comply (see WAIT_WHAT_GATE_SKILL below) still gets to stop.

Env:
  WAIT_WHAT_GATE=0            disable the gate entirely
  WAIT_WHAT_GATE_SKILL=name   gate on a different skill (default: wait-what)
  WAIT_WHAT_GATE_CAP=n        max blocks per turn (default: 2)
"""

import json
import os
import sys
import tempfile

DEFAULT_SKILL = "wait-what"
DEFAULT_CAP = 2


def allow(path, **kv):
    # exit 0 with empty stdout = let the turn end. One stderr marker so the
    # decision is observable in the hook log; identifiers only, no user content.
    parts = " ".join("%s=%s" % (k, v) for k, v in kv.items())
    sys.stderr.write(("wait_what_gate_allow path=%s %s" % (path, parts)).rstrip() + "\n")
    sys.exit(0)


def block(reason):
    json.dump({"decision": "block", "reason": reason}, sys.stdout)
    sys.exit(0)


def gated_skill():
    return (os.environ.get("WAIT_WHAT_GATE_SKILL") or DEFAULT_SKILL).strip()


def cap():
    try:
        return int(os.environ.get("WAIT_WHAT_GATE_CAP", ""))
    except ValueError:
        return DEFAULT_CAP


def read_transcript(path):
    entries = []
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue  # tolerate a partially-written tail line
    except OSError:
        return []
    return entries


def boundary_index(entries):
    """Index of the newest real user message. Everything after it is this turn.

    Tool results, meta entries and subagent prompts all land as user-type
    entries; anchoring on one of those would hide a skill call the main loop
    already made earlier in the turn.
    """
    for i in range(len(entries) - 1, -1, -1):
        e = entries[i]
        if (
            e.get("type") == "user"
            and not e.get("isMeta")
            and not e.get("toolUseResult")
            and not e.get("isSidechain")
        ):
            return i
    return -1


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(
            b.get("text", "")
            for b in content
            if isinstance(b, dict) and b.get("type") == "text"
        )
    return ""


def satisfied(entries, start, skill):
    """True when the gated skill ran at some point after `start`."""
    for e in entries[start:]:
        # The user typing /wait-what counts — the whole point of the skill is
        # that only they know when a message failed to land.
        if e.get("type") == "user" and not e.get("isSidechain"):
            body = text_of((e.get("message") or {}).get("content"))
            if "/%s" % skill in body or "<command-name>%s</command-name>" % skill in body:
                return "user_slash_command"

        # Only main-loop tool calls count: a subagent's skill call says nothing
        # about whether the coordinator re-pitched.
        if e.get("type") != "assistant" or e.get("isSidechain"):
            continue
        content = (e.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for blk in content:
            if not (isinstance(blk, dict) and blk.get("type") == "tool_use"):
                continue
            inp = blk.get("input") or {}
            if blk.get("name") == "Skill" and inp.get("skill") == skill:
                return "skill_tool"
            if blk.get("name") == "SlashCommand" and str(
                inp.get("command", "")
            ).lstrip("/").split()[:1] == [skill]:
                return "slash_command_tool"
    return None


def counter_path():
    # Keep the counter out of the working tree: a sibling git-check Stop hook
    # would otherwise see an untracked file and demand a commit.
    home = os.path.expanduser("~")
    if not home or home == "~" or not os.access(home, os.W_OK):
        home = tempfile.gettempdir()
    directory = os.path.join(home, ".wait-what-gate")
    return directory, os.path.join(directory, "turn-counter.json")


def bump(turn_key):
    """Increment the per-turn block count, resetting when the turn changed."""
    directory, path = counter_path()
    state = {}
    try:
        with open(path, encoding="utf-8") as f:
            state = json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        state = {}
    if not isinstance(state, dict):
        state = {}  # valid-but-non-dict JSON would break .get()
    count = (state.get("count", 0) if state.get("turn_key") == turn_key else 0) + 1
    try:
        os.makedirs(directory, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"turn_key": turn_key, "count": count}, f)
    except OSError:
        pass  # best-effort; the CLI's global block cap still bounds the loop
    return count


def reason_for(skill, attempt):
    if attempt <= 1:
        return (
            "Do not end the turn yet. This session gates every answer behind"
            " the `%s` skill. Call the Skill tool with skill=\"%s\", follow"
            " what it says, and deliver the re-pitched answer as your reply."
            " The re-pitch IS the answer — do not send the original message"
            " and the re-pitch both." % (skill, skill)
        )
    return (
        "Still gated: `%s` has not run this turn. Call the Skill tool with"
        " skill=\"%s\" now. If that skill is not in your available skills"
        " (upstream ships it with `disable-model-invocation: true`, which"
        " hides it from you), say so plainly in your answer rather than"
        " stopping silently." % (skill, skill)
    )


def run():
    if os.environ.get("WAIT_WHAT_GATE") == "0":
        allow("disabled_by_env")

    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        allow("stdin_decode_error")

    entries = read_transcript(payload.get("transcript_path") or "")
    if not entries:
        allow("transcript_empty")

    skill = gated_skill()
    start = boundary_index(entries)
    # Scan from the boundary entry itself: the user may have typed
    # /wait-what as this very message, which satisfies the gate.
    hit = satisfied(entries, max(start, 0), skill)
    if hit:
        allow("skill_ran", via=hit, skill=skill)

    boundary = entries[start] if start >= 0 else {}
    key = boundary.get("uuid") or boundary.get("timestamp") or "no-user-boundary"
    count = bump(key)
    if count > cap():
        # Degrade below the CLI's global block ceiling rather than trap a model
        # that cannot call the skill at all.
        allow("cap_exhausted", count=count, cap=cap())
    block(reason_for(skill, count))


def main():
    try:
        run()
    except Exception as e:
        # Type name only — the message could carry user content.
        sys.stderr.write("wait_what_gate_allow path=exception exc=%s\n" % type(e).__name__)
        sys.exit(0)


if __name__ == "__main__":
    main()
