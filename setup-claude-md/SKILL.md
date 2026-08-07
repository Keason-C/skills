---
name: setup-claude-md
description: Inject stack/workflow modules from the global template set into this project's CLAUDE.md as snapshot blocks.
disable-model-invocation: true
---

# Setup CLAUDE.md

Inject selected modules from this skill's `modules/` folder into the project's root `CLAUDE.md` as marked snapshot blocks. Evidence informs the user; the user decides every module. Re-runs refresh existing blocks; the set of injected blocks only grows — removing one is the user's own edit (delete the marker block).

This is a prompt-driven skill, not a deterministic script. Explore, present what you found, confirm with the user, then write.

## Modules and evidence

| Module | Evidence to gather |
|---|---|
| `language` | none — parameterized by the language question in step 0 |
| `backend-python` | `pyproject.toml`, `setup.py`, or `environment.yml` exists |
| `frontend-ts` | `package.json` deps include `vite` or `react`, or `tsconfig.json` exists |
| `agent-dev` | backend or frontend evidence holds AND deps include `pydantic-ai`, `claude-agent-sdk`, `@anthropic-ai/*`, or `ai` (Vercel AI SDK) |
| `vibe-coding` | none — always presented as "no detection signal" |
| `mattpocock-rules` | mattpocock-skills plugin installed (a `mattpocock` folder under `~/.claude/plugins/cache/`) |

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
- Gather the evidence in the table. Record the concrete findings (file names, dependency names), not just yes/no.

Done when every module in the table has both an injection status (injected & up to date / injected & differs / not injected) and its evidence recorded.

### 2. Present

One line per module: name, injection status, evidence verbatim ("found `pyproject.toml`", "no signal"). Then ask, with every choice starting unselected — evidence is information, never a preselection (AskUserQuestion with multiSelect works well):

- **Not injected** → user picks which to inject.
- **Injected & differs** → per module, show the diff between the block and the current template, and ask overwrite or keep. Say explicitly that the difference may be the user's own project edits — "keep" protects those.
- **Injected & up to date** → report as up to date; nothing to ask.

### 3. Confirm

Show a draft of exactly what will be written: full block content for new injections, the chosen resolution for each differing block. Let the user edit before writing.

### 4. Write

- Create `CLAUDE.md` if missing.
- New modules: append their blocks at the end of the file.
- Refreshed modules: replace content between their existing markers in place.
- Every line outside the markers stays byte-for-byte untouched.

Done when each selected module has exactly one marker block whose content matches the confirmed draft.

### 5. Done

Report per module: injected / refreshed / kept / up to date / not selected. Remind the user: re-run `/setup-claude-md` after global template updates to refresh; remove a module by deleting its marker block.
