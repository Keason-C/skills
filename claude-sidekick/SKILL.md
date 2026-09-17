---
name: claude-sidekick
description: Run Claude Code headlessly for a delegated task, continued conversation, or detached long run.
---

# Claude sidekick

Resolve the installed `claude` CLI and check `claude --version` and `claude --help` for current flags. Claude runs as an agent in the supplied directory, capable of editing files and running commands. Carry the assignment scope, applicable project/user instructions, and existing execution/commit permissions in the prompt file; do not assume Claude discovers Codex's AGENTS.md.

Model is the user's call. Reuse their choice for this task; if none was supplied, ask before a model call. Accept an alias or full model ID supported by their provider. Claude has no `agy models` equivalent in the checked CLI; help examples do not prove account access. Report authentication or model-access failures without switching models or providers.

## Run a turn

Use [scripts/claude_turn.sh](scripts/claude_turn.sh), relative to this skill:

```text
claude_turn.sh <prompt-file> --model <id> [--conv <session-id>] [--cwd <dir>] [--detach <new-logdir>] [-- <claude-options...>]
```

Prompt paths resolve before changing directory. Claude-specific file paths after `--` resolve from `--cwd`; prefer absolute paths. Keep prompts and logs outside the project repository.

The helper supplies print mode, text stdin, and JSON output; detached runs use stream-json with verbose events. Reuse the returned `session_id` with `--conv`. It preserves configured permissions and supplies `--permission-prompts none`: actions requiring a prompt are denied. For already-authorized unattended edits, pass suitable `--allowedTools` rules or an appropriate permission mode. `--dangerously-skip-permissions` is available explicitly for a host-authorized bypass run; it never expands the assignment's authority.

Additional options go after `--`, for example `--effort high --max-budget-usd 2 --tools 'Read,Grep,Glob'`. The helper owns model, conversation, input/output format, and process lifecycle; use direct CLI calls for native background mode or streaming input. Consult current help or the [official CLI reference](https://code.claude.com/docs/en/cli-reference) for other flags, checking the installed CLI when documentation differs.

## Worktree

需要在独立 Git worktree 中运行任务时，将 `--worktree [name]`（简写 `-w [name]`）放在脚本的 `--` 后透传。Claude 会为会话创建新的 worktree，名称可选；`--cwd` 指向原仓库。例如：

```bash
claude_turn.sh /tmp/task.txt --model <id> --cwd /path/to/repo -- --worktree task-name
```

本机 Claude Code 2.1.273 的 `--help` 已确认支持该参数；使用时仍按开头要求核对当前 CLI。可选的 `--tmux` 会为 worktree 创建 tmux 会话，必须搭配 `--worktree`。

## Long runs and results

Prefer the host shell's session and polling tools for runs that merely outlast one tool call. The helper imposes no wall-clock timeout; use host timeout controls when needed. Claude's dollar budget is not a duration limit.

Detached mode requires Linux `setsid` and `nohup`, creates a fresh private log directory, and stores `prompt.txt`, `run.log`, and `meta`. An existing log directory is rejected. Poll `meta` for `exit=`; nonzero means process failure, and a missing completion entry is not success. Also inspect the final JSON result's `is_error`/`subtype` and requested deliverables: a zero process exit alone does not establish task completion. Preserve evidence until checked.

To stop, verify the recorded PID/process group still belongs to this run and signal only that run. Native `claude --bg` is an alternative workflow with `claude agents`, `logs`, and `stop`; check their help and use their session IDs, not this helper's PID metadata.
