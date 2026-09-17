---
name: gemini-sidekick
description: Run Gemini through the agy CLI for one turn, continued conversations, or detached long tasks.
---

# Gemini sidekick

Resolve the installed `agy` CLI and check `agy --help` for its current flags. It operates in the supplied project directory as an agent capable of editing files and running commands. Its assignment must carry the task scope, applicable user instructions, and existing execution/commit permissions.

**Model is the user's call.** Reuse their choice for this task. If none was supplied, list `agy models` and ask for a choice before running. Report missing authentication when encountered; do not assume prior setup.

## Run a turn

Use [scripts/agy_turn.sh](scripts/agy_turn.sh), resolving its path relative to this skill. Arguments:

```text
agy_turn.sh <prompt-file> --model <selected-id> [--conv <conversation-id>] [--cwd <project-dir>] [--detach <new-logdir>]
```

The helper reads the prompt file before changing directory. Synchronous output is JSON; reuse its `conversation_id` with `--conv` for later turns. Keep prompt files and logs outside the project repository. The helper uses headless auto-approval and a 240-minute CLI timeout; run it only within the host-approved execution scope. The flag does not grant additional authority.

## Long runs

Prefer the host shell tool's session ID and polling tool when the run only needs to outlast one tool call. Use their current schemas for wait limits.

For a detached run, supply a new log directory whose parent exists. The helper writes `run.log` as stream-json and `meta` with start, PID, completion time, and exit status. Paths are resolved from the caller's directory; an existing log directory is rejected to preserve earlier evidence. Poll for the final `exit=` entry and report a nonzero status as failure. A missing completion entry is not success.

To stop a run, verify the recorded PID or process group still belongs to that run, then signal only that process or group. Keep the evidence until the task result has been checked.
