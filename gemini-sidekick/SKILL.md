---
name: gemini-sidekick
description: How to run Gemini headlessly through the agy CLI (single turn, multi-turn, detached long runs).
---

`agy` is the Antigravity CLI on PATH. Auth was done once interactively and persists. It runs as a full agent in the current directory: reads `GEMINI.md` / `AGENTS.md` there, edits files, runs commands. `agy --help` lists every flag, `agy models` every model id; below is only what those do not tell you.

## Single turn

```bash
agy -p "$(cat prompt.md)" --model gemini-3.8-flash-high --dangerously-skip-permissions --print-timeout 240m --output-format json
```

- Without `--dangerously-skip-permissions` a headless run stalls on its first edit.
- `--print-timeout` defaults to 5m and kills the run when it expires; set it above the longest run you expect.
- `json` output is `{"conversation_id": "...", "response": "..."}`. `stream-json` is one NDJSON event per step: `conversation_id` is in the first event, the reply in the last `result` event.

## Multi-turn

```bash
agy -p "$(cat followup.md)" --conversation <id> --model gemini-3.8-flash-high --dangerously-skip-permissions --print-timeout 240m --output-format json
```

Context carries over: earlier turns and the files it touched. `--continue` resumes the most recent conversation when you did not keep the id.

## Detached long run

A Bash tool call caps at 10 minutes, so a longer run goes to the background and gets polled:

```bash
setsid nohup bash -c 'agy -p "$(cat prompt.md)" --model gemini-3.8-flash-high --dangerously-skip-permissions --print-timeout 240m --output-format stream-json > run.log 2>&1; echo "exit=$?" >> run.meta' > /dev/null 2>&1 < /dev/null &
```

Finished when `run.meta` has an `exit=` line. `pgrep -f "agy -p"` shows it running; `pkill -f "agy -p"` stops it. Keep `prompt.md`, `run.log` and `run.meta` outside the repo it works in.
