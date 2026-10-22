# Subagent dispatch

Read this for the first dispatch. Use the model and effort values from the [configuration table in the main entry](../SKILL.md#1-confirm-the-plan); this file covers only runtime mechanics.

## Configuration and context

Check the current `collaboration` tools and supported models and effort levels, and confirm that the required skills are discoverable. Pass confirmed explicit overrides through `spawn_agent`'s `model` and `reasoning_effort` fields; omit those fields when inheriting the current parent conversation. Report a blocker if the required tools or configuration are unavailable rather than automatically switching execution methods.

`spawn_agent` has no working-directory, worktree, or permission parameters. Give each dispatch a unique `task_name`, set `fork_turns="all"` to inherit session rules, and begin `message` with the minimum necessary dispatch context before the role's task body. Include the role, absolute repository and working-directory paths, target branch, starting HEAD, run directory, existing authorization, and handoff information needed for this wave.

Explicitly require the subagent to enter its assigned directory, verify the branch and HEAD, read the applicable AGENTS.md and required skills, and then execute the task. Use that directory for every subsequent command. Treat the inherited parent conversation as background; this role and ticket define the task scope. New worktrees use the checked-out version, so uncommitted rules in the source directory are not automatically carried over. Include necessary session-specific rules in the dispatch context. When skills are discoverable, preserve literal `$skill-name` invocations rather than copying their bodies.

For read-only diagnosis, explicitly limit the role to reading and reporting; prohibit file changes, commits, and commands that write to the worktree. This is a behavioral restriction rather than tool-enforced permission isolation. Report a blocker if the project requires enforced read-only isolation and the host cannot provide it.

## Working directories

Before implementing a ticket for the first time, the commander verifies the target branch and HEAD and creates a separate worktree through Git. Use the confirmed target HEAD for this wave as the base, an unused absolute path, and a unique temporary branch:

```bash
git -C "$ticket_source_dir" worktree add -b "$ticket_branch" "$ticket_worktree" "$ticket_start_head"
```

Creating the worktree is dispatch preparation and includes no application changes. Save the ticket number, actual path, temporary branch, and starting HEAD. After verification, call `spawn_agent` and record its returned subagent ID or task name in the same record. Complete registration for each ticket before dispatching the next; dispatched subagents may work concurrently.

| Role | Assigned working directory |
|---|---|
| First implementation of a ticket | The separate worktree created for that ticket |
| Repair, diagnosis, fallback implementation | The ticket's registered worktree |
| Merge | The directory containing the confirmed target branch |

Each directory has only one writer at a time. Verify that the previous role has stopped before handing off; fallback implementation and recovery reuse the existing worktree. The commander explicitly manages worktrees; ending a subagent does not automatically remove its directory.

## Messages and lifecycle

Use `send_message` to provide additional information to a running role. Use `followup_task` when an idle role needs to continue working; sending a message alone does not start another turn. Follow the main entry's waiting and full-check rules; a wait timeout does not mean the role failed.

After receiving `FINAL_ANSWER` or `task_complete`, or confirming that a role is idle or errored, save its results and call `interrupt_agent` to close it out. Closing out a role does not mean its ticket passed acceptance. If the original role remains resumable, restart it later through `followup_task`; see [session recovery](recovery.md). Also use `interrupt_agent` to actively stop a running role. Before handing off, check its state and whether any commands are still writing to the worktree.

Startup is complete when the ticket, worktree, starting HEAD, and subagent ID are uniquely linked. If dispatch fails, preserve and reuse the worktree already created.
