# Headless startup

Read this for the first dispatch. Use the resolved model and effort values from the [configuration table in the main entry](../SKILL.md#1-confirm-the-plan); this file covers only runtime mechanics.

## Configuration and instructions

Check the local `claude --help` and whether the required skills are discoverable. Explicitly set model, effort, and runtime permissions through CLI arguments; omitting arguments does not mean they inherit the parent conversation. Match write permissions to the assigned working directory; apply read-only restrictions for diagnosis.

Claude Code automatically loads CLAUDE.md based on its working directory. New worktrees use the checked-out version, so uncommitted rules in the source directory are not automatically carried over. Existing project rules need no repeated injection. Add only the minimum necessary information when session-specific authorization or decisions are required for the task.

Send the prompt defined by the role's document as a single string argument. A leading `/skill-name` in the prompt expands and injects that skill's body in `-p` mode; `disable-model-invocation` does not affect this path. Preserve literal `/` and `&` characters through an argument array or correct shell quoting; do not manually copy skill bodies. Each role locates its own materials.

## Working directories

`claude` has no argument for setting a working directory; enter the target directory with `cd` before invoking it.

| Invocation | Directory and arguments |
|---|---|
| First implementation of a ticket | `cd <target-branch-directory>` and add `--worktree issue-<n>`; Claude Code creates and enters a managed worktree |
| New diagnosis or fallback implementation session | `cd <existing-ticket-worktree>` |
| Merge session | `cd <target-branch-directory>` |

Only the first kind of invocation adds `--worktree`. Managed worktrees are placed at `<repository-directory>/.claude/worktrees/<name>`. Naming them by ticket number gives their absolute paths directly, without discovering or claiming directories afterward. Before startup, verify that the source directory's branch and HEAD match the plan.

## Invocation structure

Generate a session UUID before dispatch and pass it through `--session-id`. Use it directly for continuation and recovery rather than locating it afterward. Fill `role_prompt` with actual values from the relevant task template; set runtime permission arguments according to the host and existing authorization:

```bash
session_uuid=$(cat /proc/sys/kernel/random/uuid)
cd "$ticket_source_dir" && claude -p \
  --worktree "issue-$n" \
  --session-id "$session_uuid" \
  --model "$role_model" \
  --effort "$role_effort" \
  --permission-mode bypassPermissions \
  --output-format json \
  "$role_prompt" \
  >"$call_dir/result.json" 2>"$call_dir/stderr.log"
```

Run through the host's background execution mechanism, with a separate log directory for each invocation. Save the ticket number, session UUID, background handle, absolute worktree path, starting HEAD, and output locations.

`--permission-mode bypassPermissions` requires the caller to have authorization. Without it, use an explicit `--allowedTools` allowlist rather than silently falling back to an invocation that will be denied.

## Reading results

With `--output-format json`, the `result` field contains the final reply as free text. Keep that format and require no response fields. Evaluate the exit code, `is_error`, `terminal_reason`, and `permission_denials` together to determine whether an invocation ended normally. No single field is sufficient, and a successful process exit does not itself mean the work passed acceptance.

## Worktree state

After startup, managed worktrees carry a `locked claude session <name>` lock and use a `worktree-<name>` branch; they may have a detached HEAD. Their paths and final HEADs are sufficient to identify the work, so there is no need to create a named branch unless one was required. The directory and lock remain after the process exits. Clean up with `git worktree unlock <path>` before `git worktree remove`.

Startup is complete when the background handle, session UUID, and ticket worktree are uniquely linked, and the starting HEAD matches the plan.
