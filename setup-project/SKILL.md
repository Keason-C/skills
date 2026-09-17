---
name: setup-project
description: Set up a project — inject stack/workflow modules from the global template set into its AGENTS.md as snapshot blocks (the constitution module scaffolds constitution-doc/).
---

# Set up project

Inject selected modules from this skill's `modules/` folder into the project's root `AGENTS.md` as marked snapshot blocks (the `constitution` module also includes `file` routing and scaffolds the project's `constitution-doc/` folder). Evidence informs the user; the user decides which modules to select. Re-runs refresh existing blocks; removal is the user's own edit, except the `design` → `file` replacement described below.

This is a prompt-driven skill, not a deterministic script. Resolve supporting skills from the current catalog and read their `SKILL.md` files directly. Use the current question tool within its availability rules; use a concise chat question when a required answer cannot be collected through that tool. Existing session authorization covers the same scope; ask only for choices or changes still unresolved. The project instruction file is `AGENTS.md`; maintain it directly without installing a second instruction file, sync hooks, or a file watcher.

## Process

### 0. Language — the first question

If the project's `AGENTS.md` already carries a `language` block, its value is the answer: skip the question and speak that language from the first word. Otherwise use an established session language preference; if none exists, ask the user in English: "What language should I use when talking with you?" (English, because the answer isn't known yet.) Conduct the rest of the session in the answered language.

The answer is also the value of `{{USER_LANGUAGE}}`, rendered on injection into every template that carries it — today that is `modules/language.md`. `modules/mattpocock-rules.md` carries `{{MATTPOCOCK_RULES_PATH}}`, rendered the same way (see the mattpocock-rules file section). Agent-facing text inside every template stays English.

### 1. Explore

- Root `AGENTS.md`, and `constitution-doc/tech-stack.md` when it exists — which `<!-- module:NAME -->` blocks does each contain, and does each block's content match the current template in `modules/`, rendered? A stack block sitting in `AGENTS.md` while `constitution` is in play is recorded as **to move**.
- Root `constitution-doc/` — exists? Which of the content files (`README.md`, `mission.md`, `tech-stack.md`) are missing or retired (see Retired content)? And each method file — `CONVENTIONS.md`, plus every blank in `template/` — missing / matching the current template / differing? A filled doc says nothing about its blank; judge each blank by its own path under `template/`.
- The mattpocock overrides file — inspect the current pointer and intended `{{MATTPOCOCK_RULES_PATH}}`; record any relocation and compare the existing snapshot with the template (see mattpocock-rules file). Only matters when `mattpocock-rules` is injected or gets selected.
- Gather the evidence in the Modules and evidence table. Record the concrete findings (file names, dependency names), not just yes/no.
- Include `file` when `constitution` is in play; identify legacy `design` blocks for replacement (see File routing).

Done when every module in the table has both an injection status (injected & up to date / injected & differs / not injected, plus its host file and whether it is to move) and its evidence recorded, the set of missing constitution content files is known and each method file (`CONVENTIONS.md`, every blank in `template/`) has one of its three states.

### 2. Present

One line per module: name, injection status, evidence verbatim ("found `pyproject.toml`", "no signal"). Then ask, with every choice starting unselected — evidence informs, the user selects (use the available question tool if it supports an unselected multi-select; otherwise ask for module names in one free-text question):

- **Not injected** → user picks which to inject.
- **Injected & differs** → the snapshot ask.
- **Injected & up to date** → report as up to date; nothing to ask.
- **To move** (a stack block in `AGENTS.md` with `constitution` in play) → a statement, "will move `backend-python` into `tech-stack.md`"; its diff status is presented like any other block.

`constitution` joins the module question like the rest. Everything that is not a module is a **statement**, not a choice: "will create `constitution-doc/` and add X, Y", "will write the overrides file at `{{MATTPOCOCK_RULES_PATH}}`" — or "in place" where nothing is missing. Beyond the module choices, ask only about a snapshot that differs.

### 3. Confirm

Show a draft of exactly what will be written: full block content for new injections and the chosen resolution for each differing block. Apply it when the session already authorizes those exact choices; otherwise collect the remaining choices before writing.

Done when every planned injection and replacement is covered by the user's choices and authorization.

### 4. Write

- Create `AGENTS.md` if missing.
- New modules: append their blocks at the end of their host file, except `file` (stack modules with `constitution` in play → `tech-stack.md`, after the constitution docs have been scaffolded so the file exists). Render `file` using File routing below.
- Keep the `file` block at the top of root `AGENTS.md` on both initial setup and re-runs; move an existing block there without changing its content unless a refresh was chosen.
- Refreshed modules: replace content between their existing markers in place.
- Stack blocks to move: cut the block out of `AGENTS.md` (its markers and the blank line before them) and append it, unchanged, to `tech-stack.md`; a refresh the user chose applies after the move.
- Every line outside the markers is preserved verbatim, in both host files.
- If `constitution` was selected or its block already exists: copy every missing constitution doc file into `constitution-doc/` (creating it, and an empty `roadmap/`, if needed) — every blank into `template/` whatever the project has already filled in, and each missing content doc from its blank; overwrite a method file only where the user chose to refresh it; inject its block if not present.
- If `mattpocock-rules` was selected or its block already exists: relocate an existing snapshot when needed (see mattpocock-rules file); copy `agents/mattpocock-rules.md` only when no existing snapshot is available, or overwrite where the user chose to refresh. Under `constitution-doc/`, add the README row if absent.

Done when each selected module has exactly one marker block across active host files, whose content matches the confirmed draft, `constitution-doc/` contains every required, non-retired doc whenever the `constitution` module is in play — `template/` always holding all four blanks, and `roadmap/` present, empty until the first version — and each method file is the version the user chose.

### 5. Done

Report per module: injected / refreshed / kept / up to date / not selected, naming the host file, and "moved to `tech-stack.md`" where a stack block moved; plus, when `constitution` is in play, which doc files were scaffolded — and that scaffolded files are templates awaiting the user's authoring, filled section by section as the project earns the content — plus each method file's outcome (scaffolded / restored / refreshed / kept / up to date); plus, when `mattpocock-rules` is in play, the overrides file outcome (written / refreshed / kept / in place). Remind the user: re-run `$setup-project` after global template updates to refresh; remove a module by deleting its marker block.

## Reference

### Retired content

Content archived at `archive/<project-relative-path>` or explicitly retired by the project is retired, not missing; leave it retired on re-runs and resolve any selected module's dependency on it with the user.

### Snapshots

Everything this skill writes from a template — a module block, a method file, the overrides file — is a **snapshot**: copied verbatim, and owned by the project from that moment, so user edits inside it are expected and protected. A missing snapshot is restored.

On a re-run, every snapshot is diffed against its template **rendered** (`{{USER_LANGUAGE}}` and `{{MATTPOCOCK_RULES_PATH}}` substituted first, so rendered values never count as diffs and a literal `{{...}}` never reaches the project; constitution blanks in `template/` are the exception: their placeholders are content, copied as-is):
- **Identical**: marked as up to date; nothing to ask.
- **Differs**: the **snapshot ask** — show the diff and ask **keep** (the difference may be the project's own earned edits, and keep protects them) or **overwrite** (take the current template).

### Modules and evidence

| Module | Evidence to gather |
|---|---|
| `language` | none — parameterized by the language question in step 0 |
| `backend-python` | `pyproject.toml`, `setup.py`, or `environment.yml` exists |
| `database` | deps include `sqlmodel`, `sqlalchemy`, `alembic`, `asyncpg`, `psycopg`, `aiosqlite`, `duckdb` or `polars`, or a compose file defines a `postgres` service |
| `frontend-ts` | `package.json` deps include `vite` or `react`, or `tsconfig.json` exists |
| `agent-dev` | backend or frontend evidence holds AND deps include `pydantic-ai`, `open-interpreter`, `@anthropic-ai/*`, or `ai` (Vercel AI SDK) |
| `vibe-coding` | none — always presented as "no detection signal" |
| `mattpocock-rules` | Relevant skills such as `to-spec`, `to-tickets`, `grilling`, `implement`, or `teach` exist in the current skill catalog or installed skill roots; record their resolved paths |
| `constitution` | root `constitution-doc/` already exists; otherwise presented as "no signal" (see Constitution docs below) |
| `file` | root `.design/`, `.skills-doc/`, `archive/`, or `constitution-doc/` exists; legacy `design` block; included with `constitution` |

### File routing

`modules/file.md` holds paths, purposes, and read triggers only. Render its constitution rows when `constitution` is selected or the corresponding paths already exist; omit other constitution rows. Selecting `file` alone creates no directories or supporting docs.

Offer `design` → `file` as a snapshot replacement; if the user keeps the legacy block, leave it unchanged and omit its duplicate routes from `file`. An accepted replacement removes the old block and creates or refreshes a single `file` block. Refresh the constitution snapshot to remove its old routes; if the user keeps that snapshot, omit duplicate routes from `file`.

### Constitution docs

The `constitution` module carries more than its block: when it is selected (or already injected from an earlier run), this skill also scaffolds the project's constitution docs from its `constitution-doc/` template folder into a `constitution-doc/` folder at the project root. The folder holds **two layers**, and each is treated differently:

- **Content** — `README.md`, `mission.md`, `tech-stack.md`, each copied from its blank in `template/`. **Fill gaps only**: a blank is copied to the doc's own path where the doc is missing, and an existing doc stays exactly as it is. Once filled in, these are living project documents that keep their content across template updates. A project scaffolded from an earlier layout (`architecture/` + `api-design.md`, `modules/`, or a combined `constitution.md`) gets the new files added beside the old ones; moving its content over is the user's own migration.
- **Method** — `CONVENTIONS.md` (how a doc here is written and when one retires) and `template/`, holding the blank of every doc: `README.md`, `mission.md`, `tech-stack.md`, `v{{N}}-{{SLUG}}.md`. The folder is where an agent looks up the intended shape of a doc — a reference to consult and copy from, not a form the doc must match. These are **fixtures** the project reads as-is, and each is a snapshot — every blank in `template/` restored no matter which docs the project has already filled in. This is the path by which method learned on one project reaches the next: improve the template, and every project's next `$setup-project` offers it.

The rest:

- **User-selected like any module.** Selecting it includes the constitution policy block, `file` routing, and both document layers; once injected, re-runs keep them in play without re-asking.
- **Copy verbatim.** `{{...}}` placeholders and template comments stay as-is; they guide whoever authors the docs later, not this skill.
- The `file` block routes to this folder; `constitution` holds its document policies. Both are snapshots.

### Stack modules

`backend-python`, `database`, `frontend-ts` and `agent-dev` are **stack modules**: what the code is built on and how it is written. Their **host file** depends on the `constitution` module:

- `constitution` in play → the host is `constitution-doc/tech-stack.md`; the blocks append at its end, and that file is the only place they live. The `file` block's tech-stack pointer is how the agent reaches them. The doc's own Core table records the project's decisions with rationale; the blocks are the defaults those decisions were made against — the two are meant to coexist, and pruning a block down to what the table leaves unsaid is a user edit that snapshot semantics protect.
- otherwise → the host is `AGENTS.md`, as for every other module.

A stack block found in `AGENTS.md` while `constitution` is in play is **moved**: the block, content unchanged, leaves `AGENTS.md` and appends to `tech-stack.md`. Automatic — the user is informed, not asked; it stays the snapshot it was.

### mattpocock-rules file

The `mattpocock-rules` block is a pointer read before running the named skills. Shared rules and per-skill overrides live in a snapshot of this skill's `agents/mattpocock-rules.md`, written whenever the module is selected or already injected. Its location is `{{MATTPOCOCK_RULES_PATH}}`, rendered into the block on injection:

- `constitution` module in play → `constitution-doc/mattpocock-rules.md`, a method file beside `CONVENTIONS.md` (no blank in `template/`). Add its row to the layout table in `constitution-doc/README.md` when the table lacks one — the user is informed, not asked.
- otherwise → `.skills-doc/agents/mattpocock-rules.md`.

When the path changes, carry the existing snapshot and its project edits to the new location, then update its pointer; compare that snapshot with the global template through the normal snapshot choice. If both locations contain differing files, resolve which content to keep with the user before moving.

### Block format

One block per module in its host file — `AGENTS.md`, or `constitution-doc/tech-stack.md` for a stack module when `constitution` is in play (see Stack modules):

```markdown
<!-- module:backend-python -->
…snapshot of modules/backend-python.md…
<!-- /module:backend-python -->
```
