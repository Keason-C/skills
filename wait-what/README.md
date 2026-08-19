# wait-what + the Stop-hook gate

Two things live here: a copy of Matt Pocock's `wait-what` skill, and a `Stop`
hook that refuses to let a turn end until that skill has run.

## The gate

`.claude/hooks/stop-wait-what-gate.py`, registered as a `Stop` hook in
`.claude/settings.json`.

The `Stop` hook fires when the main loop is about to hand the turn back to you.
Printing `{"decision": "block", "reason": "..."}` on stdout sends the model back
into the same turn with `reason` as fresh instruction. So "force a skill before
answering" is really "refuse to stop until the transcript shows the skill ran".

The hook reads the transcript, finds the newest real user message, and looks for
any of these after it:

- a `Skill` tool call with `skill: "wait-what"`
- a `SlashCommand` tool call for `/wait-what`
- the user typing `/wait-what` themselves

Tool results, meta entries and subagent prompts are not treated as turn
boundaries, and a subagent's own skill call does not satisfy the gate — only the
main loop's does.

It cannot trap a session. Every failure path (bad stdin, unreadable transcript,
any exception) allows the stop, and a per-turn counter releases the gate after
2 blocks, below the CLI's global 8-block ceiling.

| env | effect |
| --- | --- |
| `WAIT_WHAT_GATE=0` | disable the gate |
| `WAIT_WHAT_GATE_SKILL=name` | gate on a different skill |
| `WAIT_WHAT_GATE_CAP=n` | blocks per turn before releasing (default 2) |

Tests: `python3 .claude/hooks/test_stop_wait_what_gate.py` — 16 cases over
synthetic transcripts, covering satisfaction paths, boundary handling, the cap,
and the never-trap paths.

## Why this copy of the skill exists

`SKILL.md` here is Matt Pocock's `wait-what`, body copied verbatim from
[mattpocock/skills](https://github.com/mattpocock/skills)
(`skills/productivity/wait-what`, MIT).

**One line is deliberately dropped: `disable-model-invocation: true`.**

Upstream that line is the design, not an oversight. From the upstream docs:
*"You invoke it by typing `/wait-what`. The agent will not reach for it on its
own, and it shouldn't. Only you know when you stopped following."*

The gate needs the opposite. It re-prompts until the **model** calls the skill,
and a skill the model may not invoke can never satisfy that — the model would be
told to use a tool it cannot see, twice, until the cap released it. Hence a
model-invocable copy.

Keep both if you want both behaviours: upstream `wait-what` as the user-only
`/wait-what`, and a gate-invocable copy under a different `name:`, with
`WAIT_WHAT_GATE_SKILL` set to match. They cannot share a name — the
narrower-scoped one wins and the other becomes unreachable.
