---
name: ticket-queue
description: Orchestrate a ticket queue in a confirmed serial order or parallel waves, with delegated implementation, diagnosis, and integration. Explicit invocation only.
---

# Ticket queue

You are the **commander**, responsible for planning, dispatching work, reading results, advancing the queue, and maintaining the run log. Delegate through native subagents (the `collaboration` tools); each role's internal workflow and further delegation follow its own AGENTS.md and skills.

The commander may read tickets, specifications, configuration, Git status, commit information, and final replies. Delegate implementation, required checks, diagnosis, and merging to the appropriate roles; do not edit application code, fix tests, or read application diffs yourself.

## 1. Confirm the plan

Read the repository's AGENTS.md, tickets, referenced specs, role assignments, and standards. Verify the repository, target branch, HEAD, working tree, and existing PRs. Preserve existing changes.

Accept local Markdown tickets or GitHub issues. Collect the queue within the user's scope and exclusions; recognize the project's completion states, including done and closed. Retrieve every page of GitHub results. Order tickets by number and dependencies, and check for obvious overlap in the changes they require.

Determine from the project and conversation: repository, target branch, ticket source and scope, serial or parallel mode, concurrency limit N, role models, fallback implementation model, project initialization and required checks, existing authorization, and a private run directory. Optional settings include the expected HEAD and check interval. Read the [launch template](references/run-template.md) only when the user needs to provide configuration.

Model configuration is defined only here:

| Role | Model | Effort |
|---|---|---|
| Implementation, repair, diagnosis | Use the role model confirmed for this run; fallback implementation uses the confirmed fallback model | The ticket's value takes precedence; otherwise inherit the current parent conversation |
| Merge | Inherit the orchestrator's current model by default | Inherit the orchestrator's current effort by default |

Explicit user choices for roles take precedence. Resolve missing or unsupported required values while confirming the plan; do not silently switch models or lower settings. Clarify authorization for commits, pushes, remote comments, and closing tickets in the same confirmation, reusing existing authorization. Leave unauthorized actions pending delivery.

Show the plan and wait for explicit confirmation:

- **Serial:** execution order, dependencies, and skipped tickets.
- **Parallel:** N, tickets in each wave, grouping rationale, possible overlap, and merge order within each wave.

Start once configuration and the plan are confirmed, then proceed autonomously. Confirm a revised plan before changing scope, wave assignments, dependency order, or model configuration. Skipping failed dependencies under the agreed rules needs no further confirmation.

## 2. Dispatch and advance the queue

Before the first dispatch, read only [subagent dispatch](references/subagents.md) and confirm that the required skills are discoverable. The implementer's task body has exactly one template; attach the working directory and other dispatch context as specified in that reference:

```text
$implement issue n
```

Replace n with the actual ticket number. The implementer locates the ticket and completes the work through `$implement`.

**A wave is the unit of a merge delegation.** Serial mode has one ticket per wave; parallel mode has at most N tickets implemented independently. Wait until all implementation and necessary repairs in the wave have finished, and every ticket has passed or is explicitly blocked, before merging the deliverable portion. Enter the next wave after delivery of the current wave.

Use natural completion replies, commit information, and runtime state to decide the next step; do not impose response fields, report templates, or decision checklists. A ticket may enter merging only when its work is complete and the required checks have actually passed, or when the user has approved an explicit exception. Continue implementation if the reply identifies unfinished ticket work. If information is insufficient, ask the original role to verify it; a subagent finishing its reply does not itself mean the ticket passed.

Read the reference for the current event rather than loading every reference in advance:

- **Implementation incomplete or checks failing:** read [repair and diagnosis](references/diagnosis.md).
- **Deliverable tickets in this wave ready:** read [merge the wave](references/merge.md) and dispatch one merger.
- **Session interrupted, runtime error, or continuation needed:** read [session recovery](references/recovery.md).

Preserve the work of blocked tickets and skip tickets that depend on them; continue independent tickets in the plan. Skip merging when the wave contains no deliverable tickets.

## 3. Wait and check

Keep the session waiting when there is no work that can advance immediately. By default, check all in-flight tasks together every **30 minutes**: runtime state, final replies, escalations, and merge progress. Advance the queue or schedule the next check afterward.

Use `collaboration.wait_agent` to wait for completion or message events, with each wait no longer than 60 seconds. A partial wait returning does not trigger a full status check or repeated waiting updates. Read the relevant result and advance immediately when an event arrives; follow the host's requirements for progress updates. At each scheduled full check, use `collaboration.list_agents` to inspect all in-flight roles.

External scheduled wakeups are optional; save the task identifier when using them. A background sleep after the session ends cannot replace a real wakeup.

## 4. State, records, and completion

Maintain `run-log.md` in a private run directory outside the repository. Record only what recovery needs: the confirmed plan, current wave and ticket, subagent IDs or task names and role configuration, worktrees and starting HEADs, retry stages, merge progress, blockers, and delivery commits. Save dispatch context, key messages, failures, and final replies in the same directory. Subagent IDs apply only while the current host can still access the session; they are not persistent recovery credentials across sessions.

Mark each ticket as delivered, pending delivery, blocked, or skipped because of a dependency. Stop waiting and cancel this run's scheduled task when all work has finished, or when no task is running and nothing can advance. Briefly report delivery, preserved work, blockers, and pending publication. Continue waiting for tasks that are still running.
