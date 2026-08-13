---
name: setup-project
description: Set up a project — inject stack/workflow modules from the global template set into its CLAUDE.md as snapshot blocks, and scaffold its constitution-doc/ folder.
disable-model-invocation: true
---

# Set up project

Inject selected modules from this skill's `modules/` folder into the project's root `CLAUDE.md` as marked snapshot blocks, and scaffold the project's `constitution-doc/` folder. Evidence informs the user; the user decides every module. Re-runs refresh existing blocks; the set of injected blocks only grows — removing one is the user's own edit (delete the marker block).

This is a prompt-driven skill, not a deterministic script.

## Modules and evidence

| Module | Evidence to gather |
|---|---|
| `language` | none — parameterized by the language question in step 0 |
| `backend-python` | `pyproject.toml`, `setup.py`, or `environment.yml` exists |
| `frontend-ts` | `package.json` deps include `vite` or `react`, or `tsconfig.json` exists |
| `agent-dev` | backend or frontend evidence holds AND deps include `pydantic-ai`, `claude-agent-sdk`, `@anthropic-ai/*`, or `ai` (Vercel AI SDK) |
| `vibe-coding` | none — always presented as "no detection signal" |
| `mattpocock-rules` | mattpocock-skills plugin installed (a `mattpocock` folder under `~/.claude/plugins/cache/`) |
| `constitution` | none — automatic, no selection (see Constitution docs below) |

## Constitution docs

Besides the selectable modules, this skill scaffolds project design docs from its `constitution-doc/` template folder into a `constitution-doc/` folder at the project root. Rules:

- **Automatic — no selection.** The user is informed, not asked.
- **Fill gaps only, never overwrite.** Copy a template file only if it is missing at the target. Once filled in, these are living project documents; template updates do NOT propagate to them — there is no diff/refresh semantics here, unlike module blocks.
- **Copy verbatim.** `{{...}}` placeholders and template comments stay as-is; they guide whoever authors the docs later, not this skill.
- The `constitution` module block in CLAUDE.md routes to this folder: first injection is automatic (no selection); on re-runs it diffs like any other block, since the user may have edited the routing text.

## Block format

One block per module in the project's `CLAUDE.md`:

```markdown
<!-- module:backend-python -->
…snapshot of modules/backend-python.md…
<!-- /module:backend-python -->
```

The block is a snapshot: the project owns it from the moment it is written. User edits inside the markers are expected and survive until the user approves an overwrite on a later run.

## Process

### 0. Language — the first question, asked in English

Before anything else, ask the user in English: "What language should I use when talking with you?" (English, because the answer isn't known yet.) Conduct the rest of the session in the answered language.

The answer is also the value of `{{USER_LANGUAGE}}`: when a module template contains that placeholder (the `language` module does), the injected snapshot renders it as the user's language. Agent-facing text inside every template stays English.

### 1. Explore

- Root `CLAUDE.md` — exists? Which `<!-- module:NAME -->` blocks does it already contain, and does each block's content match the current template in `modules/`?
- Root `constitution-doc/` — exists? Which of the template files are missing?
- Gather the evidence in the table. Record the concrete findings (file names, dependency names), not just yes/no.

Done when every module in the table has both an injection status (injected & up to date / injected & differs / not injected) and its evidence recorded, and the set of missing constitution doc files is known.

### 2. Present

One line per module: name, injection status, evidence verbatim ("found `pyproject.toml`", "no signal"). Then ask, with every choice starting unselected — evidence is information, never a preselection (AskUserQuestion with multiSelect works well):

- **Not injected** → user picks which to inject.
- **Injected & differs** → per module, show the diff between the block and the current template, and ask overwrite or keep. Say explicitly that the difference may be the user's own project edits — "keep" protects those.
- **Injected & up to date** → report as up to date; nothing to ask.

Constitution docs are a statement, not a question: "will create `constitution-doc/` and add X, Y" (or "constitution-doc/ complete — nothing to add").

### 3. Confirm

Show a draft of exactly what will be written: full block content for new injections, the chosen resolution for each differing block. Let the user edit before writing.

### 4. Write

- Create `CLAUDE.md` if missing.
- New modules: append their blocks at the end of the file.
- Refreshed modules: replace content between their existing markers in place.
- Every line outside the markers stays byte-for-byte untouched.
- Copy the missing constitution doc files into `constitution-doc/` (create the folder if needed); inject the `constitution` module block if not present — pinned at the top of the file, above every other block.

Done when each selected module has exactly one marker block whose content matches the confirmed draft, and `constitution-doc/` contains every template file.

### 5. Done

Report per module: injected / refreshed / kept / up to date / not selected; plus which constitution doc files were scaffolded — and that scaffolded files are templates awaiting the user's authoring. Remind the user: re-run `/setup-project` after global template updates to refresh; remove a module by deleting its marker block.
