---
name: ticket-queue
description: Unattended serial execution of a ticket queue (local Markdown ticket directory or GitHub issues) — three roles per ticket: the session judges, an implementer subagent builds, a fresh acceptor subagent verifies and triages the implementer's open items; the delegation mode (auto by difficulty, or a fixed model) is set once at start.
disable-model-invocation: true
argument-hint: <ticket-dir | GitHub repo/label> [--mode auto|fable|opus|sonnet] [ticket numbers ...]
---

# Serial ticket orchestration (unattended)

On invocation, the current session becomes the **judge** of an unattended run. Each ticket passes through three roles: an **implementer** subagent builds it, a fresh **acceptor** subagent verifies it independently and returns a **verdict**, and you rule on that verdict. You dispatch, read two short reports, rule, log — that is the whole job. Once startup is over no one is watching, and no answer will come if you ask: every branch resolves on your own and the run continues to the end.

## Startup

1. **Ticket source** — from the invocation arguments (one of two):
   - **Local directory**: a directory of ticket files whose names start with a number (e.g. `02-meta-request-billing.md`) and whose bodies carry a `**Status:**` field. Default queue = every ticket whose `**Status:**` is not `done`, in filename order.
   - **GitHub issues**: a repo (optionally with a label/milestone filter). Build the queue with `gh issue list`; default = every matching open issue, in issue-number order.

   If ticket numbers are given as arguments, run only those.

2. **Delegation mode** — `--mode` if given; otherwise ask once with AskUserQuestion, options `auto` (Recommended), `fable`, `opus`, `sonnet`. This is the run's only question.
   - A fixed mode names the model for implementer and acceptor alike; a failed ticket is logged, never escalated.
   - `auto` grades every ticket **once, now**, from its title, type and scope, and records the grades in the run log's first entry. A grade is a **rung**:

     | rung | implementer | the ticket looks like |
     |---|---|---|
     | low | `sonnet` | doc-only, config, rename, single-file mechanical change, research |
     | medium | `opus` | ordinary implementation with tests |
     | high | `fable` | cross-module contract, state machine, concurrency, migration, marked high-risk, or design decisions the ticket leaves open |

     Acceptor rung = the implementer's, floored at `opus`. Escalation ladder: `sonnet` → `opus` → `fable`.

3. **Derived paths** (local source: the ticket directory's parent; GitHub source: `.skills-doc/ticket-queue/` in the current repo; an explicit argument overrides either):
   - Run log: `run-log.md`
   - Contentious-decisions document: `contentious-decisions.md`

   Create either file if missing, with a title line only. Under the decisions document's title, add one explanatory sentence: per-ticket record of contentious decisions made during implementation — readings of ambiguous wording, review disagreements, trade-offs between viable approaches; a ticket with none records "none". All produced documents follow the language the tickets themselves are written in.

## Judge discipline

- After startup you read no ticket, run no command, write no code, run no review, make no commit. Your only write is the run log; your only reads are the reports the two roles send you.
- **One ticket at a time, serial.** The decisions document is a shared append-only file and there is only one working tree — serial execution is the no-conflict precondition, not a performance trade-off.
- Both roles are dispatched with the Agent tool (`subagent_type: "general-purpose"`, `model` per the delegation mode), each with its fixed block below as the prompt **verbatim**, replacing only the `{PLACEHOLDERS}`. Change nothing else in them. Later turns with a live agent go through SendMessage, using the judge messages below verbatim.
- A ticket that blocks or asks a question is logged and left behind; the queue continues.
- If an agent dies on an infrastructure error (API interruption etc.), resume the same agent once via SendMessage; if it dies again, log the ticket as failed and continue.

### Per-ticket loop

1. Dispatch the implementer with `{PRIOR_FINDINGS}` = `none`. Its return is the **build report**.
2. Dispatch a fresh acceptor with the build report as `{IMPLEMENTER_REPORT}` and the reported hashes as `{COMMITS}`. Its return is the verdict.
3. Rule on the verdict:
   - `PASS` → send the implementer the **close-out** message; its reply is the final report. Go to 4.
   - `FAIL`, implementer's feedback budget (2 rounds) remaining → send the implementer the **feedback** message; on its reply, send the acceptor the **re-review** message. Back to 3.
   - `FAIL`, budget spent, mode `auto`, not yet escalated → dispatch a fresh implementer one rung up with `{PRIOR_FINDINGS}` = the last verdict, and a fresh acceptor at the matching rung. Back to 2.
   - `FAIL` otherwise → send the implementer the **reject** message; its reply is the final report. Go to 4.
   - The implementer disputes a finding → rule once on the ticket's letter, record the ruling in this ticket's run log entry, and forward it to the side that must act.
4. Append this ticket's run log entry: ticket number, models and rungs used, rounds used, outcome, the last verdict's `VERDICT` / `GATES` / `TRIAGE` lines, the implementer's final report verbatim, commit hashes, judge rulings, and the `genuine` open items. Next ticket.

**Completion criterion: queue exhausted → append a final entry** — every ticket's outcome and models, every commit produced, every escalation, and the consolidated list of `genuine` open items for the adjudicator. The run ends only once this entry is written.

### Judge messages

Feedback:

```text
Acceptance FAIL. Fix every finding below in a follow-up commit, then reply with
what changed and the new commit hash(es). Dispute a finding only with reasoning
against the ticket's letter.

{VERDICT}
```

Re-review:

```text
The implementer replied as follows; re-check your findings against the new
commit(s), re-run the gates, and return a fresh verdict in the same format.

{IMPLEMENTER_REPLY}
```

Close-out:

```text
Accepted. Close out the ticket: set its status to done, then give your final
report.
```

Reject:

```text
Rejected after the feedback budget. Set the ticket's status to blocked, quoting
the unresolved findings below, then give your final report.

{VERDICT}
```

## Fixed block — implementer

```text
Implement the work described in the ticket:
  {TICKET_REF}
(a local file path, or a GitHub issue — read the latter with `gh issue view`,
including its comments).

Findings from a previous attempt at this ticket: {PRIOR_FINDINGS}

Use Skill(skill="mattpocock-skills:tdd") where possible, at pre-agreed seams.

Run typechecking regularly, single test files regularly, and the full test suite
once at the end.

Once done, use Skill(skill="mattpocock-skills:code-review") to review the work,
and act on the findings.

Commit your work to the current branch. Stage by name the files you changed for
this ticket — the tree may carry unrelated uncommitted work and untracked files,
and those stay exactly as you found them. The commit message describes the
change and ends there: no trailers of any kind.

Then append one section for this ticket to:
  {DECISIONS_PATH}
Its audience is the human adjudicator, not another agent — write it in the
same language the ticket itself is written in. Heading:
`## Issue {ISSUE} — <short title> (commit <hash>)`. Numbered entries, one per
contentious decision: readings you chose for ambiguous ticket wording, review
disagreements and how they resolved, alternatives weighed and why the loser
lost, deviations from the ticket's letter (mark these as needing sign-off), and
refactors you rejected with reasons. A question the ticket, its spec or the
repo's design docs already answer is settled here with the source cited; only
a question none of them can answer is an open item, and gets its own bolded
entry. Record "none" only if the ticket was genuinely uncontentious.

Reply with a build report: what changed and why, gate results, commit
hash(es), and the open items you are leaving for the adjudicator. An
independent acceptor then verifies the work; the judge relays its findings.
Fix findings in a follow-up commit, refresh the hashes in your decisions
section, and reply with what changed and the new hash(es).

When the judge tells you to close out, update the ticket's status:
  - Local file: rewrite its `**Status:**` line in place — `done` with the
    commit hash(es), branch and date, plus a one-line gate summary; or
    `blocked` with the exact blocker. Commit this edit only if the ticket file
    is already tracked by git; otherwise leave it uncommitted on disk.
  - GitHub issue: if done, leave a comment stating exactly which commits
    implemented it (hashes, branch, one-line gate summary), then close the
    issue; if blocked, leave a comment stating the exact blocker and keep it
    open.
Then give your final report, in the same shape as the build report.
```

## Fixed block — acceptor

```text
You are the independent acceptor for ticket {ISSUE}:
  {TICKET_REF}
(a local file path, or a GitHub issue — read the latter with `gh issue view`,
including its comments).

Under review: commit(s) {COMMITS} on the current branch, and the section
`## Issue {ISSUE}` in {DECISIONS_PATH}. The implementer's build report:

{IMPLEMENTER_REPORT}

You are read-only on the tree: your output is the verdict alone. Verify along
three axes:

1. Result — every acceptance criterion in the ticket, checked against the diff
   (`git show {COMMITS}`) and against gates you run yourself: typecheck and
   the full test suite. A gate result counts once you have run it. If the
   ticket states no criteria, derive them from its deliverable and mark
   `CRITERIA: derived`.

2. Quality — the code follows the repo's documented standards (CLAUDE.md and
   the design docs it points to); the commit(s) contain only this ticket's
   files (`git show --stat`) and their messages carry no trailers; the
   decisions section exists and matches the diff.

3. Triage — every open item, escalation and deviation in the build report and
   the decisions section gets exactly one label:
   - genuine: needs a human or product decision the ticket, its spec and the
     design docs cannot make. Keep it.
   - resolvable: the ticket, spec or design docs already answer it. Resolve
     it, cite the source, and turn it into a finding.
   - drift: a departure from the ticket's letter or scope. Turn it into a
     finding: revert, or justify against the ticket.
   Only genuine items reach the adjudicator.

Verdict format — nothing else:

  VERDICT: PASS | FAIL
  CRITERIA: stated | derived
  GATES: <each gate you ran, with its result>
  FINDINGS:
    1. <file:line> — <what is wrong> — violates <criterion or standard>
  TRIAGE:
    - <item> — genuine | resolvable (<source>) | drift

FAIL while any finding remains. On re-review you receive the implementer's
reply and new commit hash(es): re-check the findings, re-run the gates, and
return a fresh verdict in the same format.
```

## Why the blocks are written this way (read before editing them)

1. **`Skill(...)` calls by full name, not slash commands.** Inside a dispatched prompt a slash command is inert text — the harness expands slash commands only in user input. The bare name `code-review` also resolves to a different skill: forked execution owned by the fork, which the ticket agent cannot stop once launched.
2. **Staging by name and trailer-free messages are hard guardrails.** The tree may carry unrelated uncommitted work and untracked files; an unattended `git add -A` / `commit -a` would silently sweep them into the ticket's commit. Commit history is audited for authorship, so the message ends with the change it describes.
3. **The acceptor is fresh per ticket and runs the gates itself.** A fork would inherit the judge's whole history and the attention cost that comes with it; a fresh agent holds one ticket and nothing else. Running the gates is what makes the verdict independent of the build report. The judge reads verdicts, never diffs — that is what keeps its attention intact across a long queue.
4. **Triage exists to stop drift.** Without it every uncertainty is punted upward and the adjudicator's list fills with questions the docs already answer; with it, `genuine` is the only label that reaches a human.
5. **Close-out happens after the verdict.** The ticket's status line then records the acceptor's ruling, not the implementer's self-assessment.
6. **Status and decisions are written by the implementer itself, never transcribed by the judge.** The context behind each decision — the rejected alternatives, the reviewer's exact objection — lives only in the implementing agent; relaying it loses information. Serial execution guarantees conflict-free appends.
7. **Language is not hardcoded.** The blocks are prompts to agents (English); the language of the decisions document and status updates follows the tickets' own language, judged by the agent — whatever language the tickets are written in is the language their adjudicator reads.
