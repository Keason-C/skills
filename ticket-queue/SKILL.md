---
name: ticket-queue
description: Unattended serial execution of a ticket queue (local Markdown ticket directory or GitHub issues) — dispatch one implementation agent per ticket; each agent closes out by updating the ticket's status and appending its section to a shared contentious-decisions document; the orchestrator only keeps the run log.
disable-model-invocation: true
argument-hint: <ticket-dir | GitHub repo/label> [ticket numbers ...]
---

# Serial ticket orchestration (unattended)

On invocation, the current session becomes an unattended orchestrator: dispatch each ticket in the queue to an implementation agent, collect the return, log it, and continue until the queue is exhausted. No one is watching, and no answer will come if you ask — every branch resolves on your own and the run continues to the end.

## Startup

Identify the **ticket source** from the invocation arguments (one of two):

- **Local directory**: a directory of ticket files whose names start with a number (e.g. `02-meta-request-billing.md`) and whose bodies carry a `**Status:**` field. Default queue = every ticket whose `**Status:**` is not `done`, in filename order.
- **GitHub issues**: a repo (optionally with a label/milestone filter). Build the queue with `gh issue list`; default = every matching open issue, in issue-number order.

If ticket numbers are given as arguments, run only those.

Derived paths (local source: the ticket directory's parent; GitHub source: `.skills-doc/ticket-queue/` in the current repo; an explicit argument overrides either):

- Run log: `run-log.md`
- Contentious-decisions document: `contentious-decisions.md`

Create either file if missing, with a title line only. Under the decisions document's title, add one explanatory sentence: per-ticket record of contentious decisions made during implementation — readings of ambiguous wording, review disagreements, trade-offs between viable approaches; a ticket with none records "none". All produced documents follow the language the tickets themselves are written in.

## Orchestrator discipline

- During startup you may query the ticket source to build the queue (`gh issue list`, directory scan). Once the dispatch loop starts, you read no ticket, run no command, write no code, run no review, make no commit. You dispatch, wait, log, move on.
- **One ticket at a time, serial.** The decisions document is a shared append-only file and there is only one working tree — serial execution is the no-conflict precondition, not a performance trade-off.
- Dispatch with the Agent tool (`subagent_type: "general-purpose"`, `model: "opus"`), sending the fixed block below as the prompt **verbatim**, replacing only `{ISSUE}` (ticket number), `{TICKET_REF}` (ticket file path, or the GitHub issue's `owner/repo#N` / URL), and `{DECISIONS_PATH}` (decisions document path). Change nothing else in it.
- Every return, whatever it says, gets one entry appended to the run log: ticket number, outcome, the agent's summary verbatim, and any commit hashes it reports. Then dispatch the next ticket.
- A ticket that fails, blocks, or asks a question is logged and left behind; the queue continues.
- If an agent dies on an infrastructure error (API interruption etc.), resume the same agent once via SendMessage; if it fails again, log it as a failed ticket and continue.
- **Completion criterion: queue exhausted → append a final entry** — every ticket's outcome, every commit produced, and a consolidated list of the open items each ticket left for the adjudicator (collected from the agents' final reports and the decisions document). The run ends only once this entry is written.

## Fixed block — sent once per ticket

```text
Implement the work described in the ticket:
  {TICKET_REF}
(a local file path, or a GitHub issue — read the latter with `gh issue view`,
including its comments).

Use Skill(skill="mattpocock-skills:tdd") where possible, at pre-agreed seams.

Run typechecking regularly, single test files regularly, and the full test suite
once at the end.

Once done, use Skill(skill="mattpocock-skills:code-review") to review the work,
and act on the findings.

Commit your work to the current branch. Stage by name the files you changed for
this ticket — the tree may carry unrelated uncommitted work and untracked files,
and those stay exactly as you found them.

Then close out the ticket:

1. Update the ticket's status.
   - Local file: rewrite its `**Status:**` line in place — `done` with the
     commit hash(es), branch and date, plus a one-line gate summary; or
     `blocked` with the exact blocker. Commit this edit only if the ticket file
     is already tracked by git; otherwise leave it uncommitted on disk.
   - GitHub issue: if done, leave a comment stating exactly which commits
     implemented it (hashes, branch, one-line gate summary), then close the
     issue; if blocked, leave a comment stating the exact blocker and keep it
     open.

2. Append one section for this ticket to:
     {DECISIONS_PATH}
   Its audience is the human adjudicator, not another agent — write it in the
   same language the ticket itself is written in. Heading:
   `## Issue {ISSUE} — <short title> (commit <hash>)`. Numbered entries, one
   per contentious decision: readings you chose for ambiguous ticket wording,
   review disagreements and how they resolved, alternatives weighed and why the
   loser lost, deviations from the ticket's letter (mark these as needing
   sign-off), and refactors you rejected with reasons. Escalated discoveries
   that need a human or product decision get their own bolded entry. Record
   "none" only if the ticket was genuinely uncontentious.

3. End with a final report: what changed and why, gate results, commit hashes,
   and any open items you are leaving for the adjudicator.
```

## Why the fixed block is written this way (read before editing it)

1. **`Skill(...)` calls by full name, not slash commands.** Inside a dispatched prompt a slash command is inert text — the harness expands slash commands only in user input. The bare name `code-review` also resolves to a different skill: forked execution owned by the fork, which the ticket agent cannot stop once launched.
2. **Staging by name is a hard guardrail.** The tree may carry unrelated uncommitted work and untracked files; an unattended `git add -A` / `commit -a` would silently sweep them into the ticket's commit.
3. **Status and decisions are written by the ticket agent itself, never transcribed by the orchestrator.** The context behind each decision — the rejected alternatives, the reviewer's exact objection — lives only in the implementing agent; relaying it loses information. Serial execution guarantees conflict-free appends.
4. **Language is not hardcoded.** The fixed block itself is a prompt to an agent (English); the language of the decisions document and status updates follows the tickets' own language, judged by the agent — whatever language the tickets are written in is the language their adjudicator reads.
