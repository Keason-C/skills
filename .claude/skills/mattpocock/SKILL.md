---
name: mattpocock
description: Matt Pocock's engineering skills — TDD, code review, diagnosing bugs, specs, tickets, triage, domain modeling, codebase design, grilling, handoff, research. Use whenever the user asks for any of those, names one of the skill names indexed below, or types /mattpocock.
---

# Matt Pocock skills — router

These skills are installed at `.claude/mp-skills/<name>/SKILL.md`. They are
deliberately **not** registered with the Skill tool, so none of them are subject
to `disable-model-invocation` and all of them are reachable from subagents.

## How to load one

1. Pick the entry from the index whose "use when" matches the request.
2. `Read` `.claude/mp-skills/<name>/SKILL.md`.
3. Follow it verbatim, as if its body were your own instructions. Resolve any
   file it references relative to `.claude/mp-skills/<name>/`.

## How to delegate one to a subagent

Put the path in the subagent prompt and make reading it the first step:

> Read `.claude/mp-skills/<name>/SKILL.md` in full and follow it verbatim for
> the following task: <task>

Do not paraphrase the skill for the subagent — hand it the path so it loads the
whole thing itself.

## Index

| skill | use when |
|---|---|
| `ask-matt` | Ask which skill or flow fits your situation. A router over the skills in this repo. |
| `batch-grill-me` | A relentless interview that asks every frontier question at once, round by round. |
| `claude-handoff` | Hand the current conversation off to a fresh background agent that picks up the work immediately. |
| `code-review` | Review the changes since a fixed point (commit, branch, tag, or merge-base) along two axes — Standards (does the code follow this repo's… |
| `codebase-design` | Shared vocabulary for designing deep modules. Use when the user wants to design or improve a module's interface, find deepening opportunities,… |
| `design-an-interface` | Generate multiple radically different interface designs for a module using parallel sub-agents. Use when user wants to design an API, explore… |
| `diagnosing-bugs` | Diagnosis loop for hard bugs and performance regressions. Use when the user says "diagnose"/"debug this", or reports something… |
| `domain-modeling` | Build and sharpen a project's domain model. Use when the user wants to pin down domain terminology or a ubiquitous language, record an… |
| `edit-article` | Edit and improve articles by restructuring sections, improving clarity, and tightening prose. Use when user wants to edit, revise, or improve an… |
| `git-guardrails-claude-code` | Set up Claude Code hooks to block dangerous git commands (push, reset --hard, clean, branch -D, etc.) before they execute. Use when user wants to… |
| `grill-me` | A relentless interview to sharpen a plan or design. |
| `grill-with-docs` | A relentless interview to sharpen a plan or design, which also creates docs (ADR's and glossary) as we go. |
| `grilling` | Grill the user relentlessly about a plan, decision, or idea. Use when the user wants to stress-test their thinking, or uses any 'grill' trigger… |
| `handoff` | Compact the current conversation into a handoff document for another agent to pick up. |
| `implement` | "Implement a piece of work based on a spec or set of tickets." |
| `improve-codebase-architecture` | Scan a codebase for deepening opportunities, present them as a visual HTML report, then grill through whichever one you pick. |
| `loop-me` | Grill me about specs for the workflows I want to build, within this workspace. |
| `migrate-to-shoehorn` | Migrate test files from `as` type assertions to @total-typescript/shoehorn. Use when user mentions shoehorn, wants to replace `as` in tests, or… |
| `obsidian-vault` | Search, create, and manage notes in the Obsidian vault with wikilinks and index notes. Use when user wants to find, create, or organize notes in… |
| `prototype` | Build a throwaway prototype to answer a design question. Use when the user wants to sanity-check whether a state model or logic feels right, or… |
| `qa` | Interactive QA session where user reports bugs or issues conversationally, and the agent files GitHub issues. Explores the codebase in the… |
| `request-refactor-plan` | Create a detailed refactor plan with tiny commits via user interview, then file it as a GitHub issue. Use when user wants to plan a refactor,… |
| `research` | Investigate a question against high-trust primary sources and capture the findings as a Markdown file in the repo. Use when the user wants a topic… |
| `resolving-merge-conflicts` | "Use when you need to resolve an in-progress git merge/rebase conflict." |
| `scaffold-exercises` | Create exercise directory structures with sections, problems, solutions, and explainers that pass linting. Use when user wants to scaffold… |
| `setup-matt-pocock-skills` | Configure this repo for the engineering skills — set up its issue tracker, triage label vocabulary, and domain doc layout. Run once before first… |
| `setup-pre-commit` | Set up Husky pre-commit hooks with lint-staged (Prettier), type checking, and tests in the current repo. Use when user wants to add pre-commit… |
| `setup-ts-deep-modules` | Wire dependency-cruiser into a TypeScript repo so each package is a deep module — implementation hidden in subfolders, reachable only through its… |
| `tdd` | Test-driven development. Use when the user wants to build features or fix bugs test-first, mentions "red-green-refactor", or wants integration tests. |
| `teach` | Teach the user a new skill or concept, within this workspace. |
| `to-questionnaire` | Turn a decision you can't fully answer into a questionnaire for someone else to fill in. |
| `to-spec` | Turn the current conversation into a spec and publish it to the project issue tracker — no interview, just synthesis of what you've already discussed. |
| `to-tickets` | Break a plan, spec, or the current conversation into a set of tracer-bullet tickets, each declaring its blocking edges, published to the… |
| `triage` | Move issues and external PRs through a state machine of triage roles — categorise, verify, grill if needed, and write agent-ready briefs. |
| `ubiquitous-language` | Extract a DDD-style ubiquitous language glossary from the current conversation, flagging ambiguities and proposing canonical terms. Saves to… |
| `wayfinder` | Plan a huge chunk of work — more than one agent session can hold — as a shared map of decision tickets on your issue tracker, and resolve them one… |
| `wizard` | Generate an interactive bash wizard that walks a human through a manual procedure — third-party setup, a one-off migration, an A→B state… |
| `writing-beats` | Writing, exploit — assemble raw material into a journey of beats, grounding each term before a beat leans on it. |
| `writing-fragments` | Writing, explore — mine raw fragments, no structure yet. |
| `writing-great-skills` | Reference for writing and editing skills well — the vocabulary and principles that make a skill predictable. |
| `writing-shape` | Writing, exploit — shape raw material into an article, paragraph by paragraph. |
