---
name: setup-project
description: Set up a project — inject stack/workflow modules from the global template set into its CLAUDE.md as snapshot blocks, scaffold its constitution-doc/ folder, inject the user-reminders hooks, and point AGENTS.md at CLAUDE.md.
disable-model-invocation: true
---

# Set up project

Inject selected modules from this skill's `modules/` folder into the project's root `CLAUDE.md` as marked snapshot blocks, scaffold the project's `constitution-doc/` folder, inject the user-reminders hook, and make `AGENTS.md` point at `CLAUDE.md`. Evidence informs the user; the user decides every module. Re-runs refresh existing blocks; the set of injected blocks only grows — removing one is the user's own edit (delete the marker block).

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

## AGENTS.md pointer

Root `CLAUDE.md` is the single source of truth. Non-Claude agents (Codex, Cursor, Copilot, Gemini CLI, Aider) read `AGENTS.md` instead, so the project gets an `AGENTS.md` that is a **pointer, never a copy** — a copy would drift the moment either file is edited, and this skill does not own a sync step.

Write exactly this file at the project root:

```markdown
# AGENTS.md

**READ `CLAUDE.md` IN THIS DIRECTORY FIRST — IT IS THE SINGLE SOURCE OF TRUTH FOR THIS PROJECT.**

Every instruction that applies to you lives in `CLAUDE.md`: stack conventions, workflow rules, and the design docs it routes to. This file is deliberately a pointer, not a copy, so the two can never fall out of sync.
```

Rules:

- **Missing, or already this exact pointer** → automatic, no selection. The user is informed, not asked.
- **Exists with other content** → never overwrite silently. Show the current content and ask: replace with the pointer, or keep as is. Content there is the user's own work.

## User-reminders hook

Instructions loaded at the top of context decay as a session grows. The project gets two hooks that hold the user's standing reminders at the **tail** — the end of context, read right before the model generates. `UserPromptSubmit` injects the reminders themselves beside each new prompt. `PostToolBatch` injects a one-line pointer back to them beside every batch of tool results, so a long tool-driven turn keeps re-activating them at a fraction of the tokens.

The pointer is an attention anchor, not an instruction: it repeats the `<user-reminders>` token at the freshest position and says the reminders still hold. No imperative, no copy of the rules — those live in `user-reminders.md` alone, so the user edits their reminders in one place.

Two artifacts, both automatic (the user is informed, not asked):

1. `.claude/hooks/user-reminders.md` — a snapshot of this skill's `hooks/user-reminders.md` template with `{{USER_LANGUAGE}}` rendered. Snapshot semantics match module blocks: the project owns its copy; on re-runs, diff it against the *rendered* template, and if it differs, show the diff and ask overwrite or keep.
2. These entries merged into `.claude/settings.json` — create the file if missing, preserve every existing key, and add only an entry whose exact command is absent (never duplicate):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "cat \"$CLAUDE_PROJECT_DIR/.claude/hooks/user-reminders.md\""
          }
        ]
      }
    ],
    "PostToolBatch": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "printf '%s' '{\"hookSpecificOutput\":{\"hookEventName\":\"PostToolBatch\",\"additionalContext\":\"User reminders are active, <user-reminders> above still apply.\"}}'"
          }
        ]
      }
    ]
  }
}
```

`PostToolBatch` takes no matcher — it fires once per batch, whatever ran. Tool-loop events read `additionalContext` and ignore raw stdout, hence the JSON.

The hooks take effect from the project's next Claude Code session (or after the user opens `/hooks` once in a running one) — say so in the report.

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

The answer is also the value of `{{USER_LANGUAGE}}`: every template carrying that placeholder renders it as the user's language on injection, both under `modules/` (the `language` module) and `hooks/user-reminders.md`. Agent-facing text inside every template stays English.

### 1. Explore

- Root `CLAUDE.md` — exists? Which `<!-- module:NAME -->` blocks does it already contain, and does each block's content match the current template in `modules/`?
- Root `constitution-doc/` — exists? Which of the template files are missing?
- Root `AGENTS.md` — missing / already the pointer / other content?
- `.claude/hooks/user-reminders.md` — missing / matches the template / differs? And does `.claude/settings.json` already carry the user-reminders `UserPromptSubmit` and `PostToolBatch` entries?
- Gather the evidence in the table. Record the concrete findings (file names, dependency names), not just yes/no.

Done when every module in the table has both an injection status (injected & up to date / injected & differs / not injected) and its evidence recorded, the set of missing constitution doc files is known, `AGENTS.md` has one of the three states above, and both user-reminders hook artifacts have a recorded state.

### 2. Present

One line per module: name, injection status, evidence verbatim ("found `pyproject.toml`", "no signal"). Then ask, with every choice starting unselected — evidence is information, never a preselection (AskUserQuestion with multiSelect works well):

- **Not injected** → user picks which to inject.
- **Injected & differs** → per module, show the diff between the block and the current template, and ask overwrite or keep. Say explicitly that the difference may be the user's own project edits — "keep" protects those.
- **Injected & up to date** → report as up to date; nothing to ask.

Constitution docs are a statement, not a question: "will create `constitution-doc/` and add X, Y" (or "constitution-doc/ complete — nothing to add").

`AGENTS.md` is a statement too — "will write the pointer to CLAUDE.md" / "pointer already in place" — unless it exists with other content, which is the one case that asks (replace or keep).

The user-reminders hooks are a statement as well — "will inject the reminders hooks" / "hooks in place" — unless the project's reminder file differs from the template, which diffs and asks like a module block.

### 3. Confirm

Show a draft of exactly what will be written: full block content for new injections, the chosen resolution for each differing block. Let the user edit before writing.

### 4. Write

- Create `CLAUDE.md` if missing.
- New modules: append their blocks at the end of the file.
- Refreshed modules: replace content between their existing markers in place.
- Every line outside the markers stays byte-for-byte untouched.
- Copy the missing constitution doc files into `constitution-doc/` (create the folder if needed); inject the `constitution` module block if not present — pinned at the top of the file, above every other block.
- Write `AGENTS.md` with the pointer content, unless the user chose to keep existing content. Never copy `CLAUDE.md` into it.
- Copy `hooks/user-reminders.md` into `.claude/hooks/` (create folders as needed) unless the user chose to keep their edited copy, and merge both settings entries per the User-reminders hook section.

Done when each selected module has exactly one marker block whose content matches the confirmed draft, `constitution-doc/` contains every template file, `AGENTS.md` holds the pointer (or the content the user chose to keep), and `.claude/settings.json` carries exactly one user-reminders `UserPromptSubmit` entry and one `PostToolBatch` entry.

### 5. Done

Report per module: injected / refreshed / kept / up to date / not selected; plus which constitution doc files were scaffolded — and that scaffolded files are templates awaiting the user's authoring; plus the `AGENTS.md` outcome (written / already in place / kept); plus the user-reminders hooks outcome (injected / refreshed / kept / in place) and when they take effect. Remind the user: re-run `/setup-project` after global template updates to refresh; remove a module by deleting its marker block; project instructions are edited in `CLAUDE.md` only — `AGENTS.md` stays a pointer.
