---
name: setup-project
description: Set up a project — inject selected stack, workflow, and coding-standard modules as snapshot blocks into AGENTS.md and constitution-doc/.
---

# Set up project

Inject selected modules from this skill's `modules/` folder as marked snapshot blocks. Workflow modules live in root `AGENTS.md`; `code-style` lives in `constitution-doc/CODE_REVIEW_STANDARDS.md`; stack modules follow Stack modules below. The `constitution` module also includes `file` routing and scaffolds `constitution-doc/`. Evidence informs the user; the user decides which modules to select. Re-runs refresh existing blocks; removal is the user's own edit, except the `design` → `file` replacement described below.

This is a prompt-driven skill, not a deterministic script. Resolve supporting skills from the current catalog and read their `SKILL.md` files directly. Use the current question tool within its availability rules; use a concise chat question when a required answer cannot be collected through that tool. Existing session authorization covers the same scope; ask only for choices or changes still unresolved. The project instruction file is `AGENTS.md`; maintain it directly without installing a second instruction file, sync hooks, or a file watcher.

## Process

### 0. Language — the first question

If the project's `AGENTS.md` already carries a `language` block, its value is the answer: skip the question and speak that language from the first word. Otherwise use an established session language preference; if none exists, ask the user in English: "What language should I use when talking with you?" (English, because the answer isn't known yet.) Conduct the rest of the session in the answered language.

The answer is also the value of `{{USER_LANGUAGE}}`, rendered on injection into every template that carries it — today that is `modules/language.md`. Agent-facing text inside every template stays English.

### 1. Explore

- Root `AGENTS.md`, and `constitution-doc/tech-stack.md` and `constitution-doc/CODE_REVIEW_STANDARDS.md` when they exist — which `<!-- module:NAME -->` blocks does each contain, and does each block's content match the current template in `modules/`, rendered? Record a `code-style` block outside `CODE_REVIEW_STANDARDS.md`, or a stack block in `AGENTS.md` while `constitution` is in play, as **to move**.
- Root `.gitignore` — missing / already ignores root `archive/` / needs an ignore rule.
- Root `constitution-doc/` — exists? Which of the content files (`README.md`, `mission.md`, `tech-stack.md`) are missing or retired (see Retired content)? And each method file — `CONVENTIONS.md`, plus every blank in `template/` — missing / matching the current template / differing? A filled doc says nothing about its blank; judge each blank by its own path under `template/`.
- If an existing `mattpocock-rules` block is a pointer, read its referenced file as the current module snapshot (see Legacy Matt Pocock rules).
- Gather the evidence in the Modules and evidence table. Record the concrete findings (file names, dependency names), not just yes/no.
- Include `file` when `constitution` is in play; identify legacy `design` blocks for replacement (see File routing).

Done when every module in the table has both an injection status (injected & up to date / injected & differs / not injected, plus its host file and whether it is to move) and its evidence recorded, the set of missing constitution content files is known and each method file (`CONVENTIONS.md`, every blank in `template/`) has one of its three states.

### 2. Present

One line per module: name, injection status, evidence verbatim ("found `pyproject.toml`", "no signal"). Then ask, with every choice starting unselected — evidence informs, the user selects (use the available question tool if it supports an unselected multi-select; otherwise ask for module names in one free-text question):

- **Not injected** → user picks which to inject.
- **Injected & differs** → the snapshot ask.
- **Injected & up to date** → report as up to date; nothing to ask.
- **To move** → a statement naming its destination, such as "will move `code-style` into `constitution-doc/CODE_REVIEW_STANDARDS.md`" or "will move `backend-python` into `tech-stack.md`"; its diff status is presented like any other block.

`constitution` joins the module question like the rest. Everything that is not a module is a **statement**, not a choice: "will create `constitution-doc/` and add X, Y", ".gitignore will ignore root archive/" — or "in place" where nothing is missing. Beyond the module choices, ask only about a snapshot that differs.

### 3. Confirm

Show a draft of exactly what will be written: full block content for new injections and the chosen resolution for each differing block. Apply it when the session already authorizes those exact choices; otherwise collect the remaining choices before writing.

Done when every planned injection and replacement is covered by the user's choices and authorization.

### 4. Write

- Create `AGENTS.md` if missing.
- On every setup, ensure root `archive/` is ignored by Git. Create root `.gitignore` if missing; append `/archive/` only when no effective existing rule already ignores that directory. Preserve existing `.gitignore` content and tracked files; this creates no `archive/` directory.
- New modules: append their blocks at the end of their host file, except `file`. For `code-style`, create its host using Code review standards below. Stack modules with `constitution` in play go into `tech-stack.md`, after the constitution docs have been scaffolded so the file exists. Render `file` using File routing below.
- Keep the `file` block at the top of root `AGENTS.md` on both initial setup and re-runs; move an existing block there without changing its content unless a refresh was chosen.
- Refreshed modules: replace content between their existing markers in place.
- Legacy `mattpocock-rules` pointers: replace the pointer with the chosen rules inside the existing block (see Legacy Matt Pocock rules).
- Blocks to move: cut the block out of its old host (its markers and the blank line before them) and append it, unchanged, to its destination; a refresh the user chose applies after the move.
- Every line outside the markers is preserved verbatim, in all existing host files.
- If `constitution` was selected or its block already exists: copy every missing constitution doc file into `constitution-doc/` (creating it, and an empty `roadmap/`, if needed) — every blank into `template/` whatever the project has already filled in, and each missing content doc from its blank; overwrite a method file only where the user chose to refresh it; inject its block if not present.

Done when root `.gitignore` effectively ignores `archive/`, each selected module has exactly one marker block in its designated host file, whose content matches the confirmed draft, `constitution-doc/` contains every required, non-retired doc whenever the `constitution` module is in play — `template/` always holding all four blanks, and `roadmap/` present, empty until the first version — and each method file is the version the user chose.

### 5. Done

Report per module: injected / refreshed / kept / up to date / not selected, naming the host file and destination of any move; plus, when `constitution` is in play, which doc files were scaffolded — and that scaffolded files are templates awaiting the user's authoring, filled section by section as the project earns the content — plus each method file's outcome (scaffolded / restored / refreshed / kept / up to date). Report whether `CODE_REVIEW_STANDARDS.md` was created or retained and whether the `mattpocock-rules` review entry is present. For a legacy Matt Pocock pointer, report that its rules were inlined and name the retained source file. Remind the user: re-run `$setup-project` after global template updates to refresh; remove a module by deleting its marker block.
Report the `.gitignore` outcome: created / updated / in place.

## Reference

### Retired content

Content archived at `archive/<project-relative-path>` or explicitly retired by the project is retired, not missing; leave it retired on re-runs and resolve any selected module's dependency on it with the user.

### Snapshots

Everything this skill writes from a template — a module block or a method file — is a **snapshot**: copied verbatim, and owned by the project from that moment, so user edits inside it are expected and protected. A missing snapshot is restored.

On a re-run, every snapshot is diffed against its template **rendered** (`{{USER_LANGUAGE}}` substituted first, so rendered values never count as diffs and a literal `{{...}}` never reaches the project; constitution blanks in `template/` are the exception: their placeholders are content, copied as-is):
- **Identical**: marked as up to date; nothing to ask.
- **Differs**: the **snapshot ask** — show the diff and ask **keep** (the difference may be the project's own earned edits, and keep protects them) or **overwrite** (take the current template).

### Modules and evidence

| Module | Evidence to gather |
|---|---|
| `language` | none — parameterized by the language question in step 0 |
| `code-style` | none — optional coding rules across stacks; injected into `constitution-doc/CODE_REVIEW_STANDARDS.md` |
| `backend-python` | `pyproject.toml`, `setup.py`, or `environment.yml` exists |
| `database` | deps include `sqlmodel`, `sqlalchemy`, `alembic`, `asyncpg`, `psycopg`, `aiosqlite`, `duckdb` or `polars`, or a compose file defines a `postgres` service |
| `frontend-ts` | `package.json` deps include `vite` or `react`, or `tsconfig.json` exists |
| `agent-dev` | backend or frontend evidence holds AND deps include `pydantic-ai`, `open-interpreter`, `@anthropic-ai/*`, or `ai` (Vercel AI SDK) |
| `vibe-coding` | none — always presented as "no detection signal" |
| `mattpocock-rules` | Relevant skills such as `to-spec`, `to-tickets`, `grilling`, or `code-review` exist in the current skill catalog or installed skill roots; record their resolved paths |
| `constitution` | root `constitution-doc/` already exists; otherwise presented as "no signal" (see Constitution docs below) |
| `file` | root `.design/`, `archive/`, or `constitution-doc/` exists; legacy `design` block; included with `constitution` |

### File routing

`modules/file.md` holds paths, purposes, and read triggers only. Render its constitution rows when `constitution` is selected or the corresponding paths already exist; omit other constitution rows. Selecting `file` alone creates no directories or supporting docs.

Offer `design` → `file` as a snapshot replacement; if the user keeps the legacy block, leave it unchanged and omit its duplicate routes from `file`. An accepted replacement removes the old block and creates or refreshes a single `file` block. Refresh the constitution snapshot to remove its old routes; if the user keeps that snapshot, omit duplicate routes from `file`.

### Constitution docs

The `constitution` module carries more than its block: when it is selected (or already injected from an earlier run), this skill also scaffolds the project's constitution docs from its `constitution-doc/` template folder into a `constitution-doc/` folder at the project root. The folder holds **two layers**, and each is treated differently:

- **Content** — `README.md`, `mission.md`, `tech-stack.md`, each copied from its blank in `template/`. **Fill gaps only**: a blank is copied to the doc's own path where the doc is missing, and an existing doc stays exactly as it is. Once filled in, these are living project documents that keep their content across template updates. A project scaffolded from an earlier layout (`architecture/` + `api-design.md`, `modules/`, or a combined `constitution.md`) gets the new files added beside the old ones; moving its content over is the user's own migration.
- **Method** — `CONVENTIONS.md` (how a doc here is written and when one retires) and `template/`, holding the blanks of the authored constitution docs: `README.md`, `mission.md`, `tech-stack.md`, `v{{N}}-{{SLUG}}.md`. The folder is where an agent looks up the intended shape of a doc — a reference to consult and copy from, not a form the doc must match. These are **fixtures** the project reads as-is, and each is a snapshot — every blank in `template/` restored no matter which docs the project has already filled in. This is the path by which method learned on one project reaches the next: improve the template, and every project's next `$setup-project` offers it.

The rest:

- **User-selected like any module.** Selecting it includes the constitution policy block, `file` routing, and both document layers; once injected, re-runs keep them in play without re-asking.
- **Copy verbatim.** `{{...}}` placeholders and template comments stay as-is; they guide whoever authors the docs later, not this skill.
- The `file` block routes to this folder; `constitution` holds its document policies. Both are snapshots.

### Code review standards

`code-style` is independently selectable. Its host is always `constitution-doc/CODE_REVIEW_STANDARDS.md`, whether or not `constitution` is in play. For an injection or move, create the folder and host with the heading `# Code review standards` where missing; an existing block in this host follows the snapshot rules. The other constitution docs are scaffolded only when `constitution` is in play.

A legacy `code-style` block in `AGENTS.md` or `tech-stack.md` moves to this host with its content and markers unchanged. Snapshot choices apply to its content after the move. An existing `CODE_REVIEW_STANDARDS.md` keeps all content outside the module markers. When `code-style` is neither selected nor already injected, leave an existing standards file intact and create none.

The `mattpocock-rules` template carries the review read trigger under `## code-review`. Present it as the optional `AGENTS.md` entry for these standards; `code-style` and `mattpocock-rules` remain separate module choices.

### Stack modules

`backend-python`, `database`, `frontend-ts` and `agent-dev` are **stack modules**: what the code is built on and how it is written. Their **host file** depends on the `constitution` module:

- `constitution` in play → the host is `constitution-doc/tech-stack.md`; the blocks append at its end, and that file is the only place they live. The `file` block's tech-stack pointer is how the agent reaches them. The doc's own Core table records the project's decisions with rationale; the blocks are the defaults those decisions were made against — the two are meant to coexist, and pruning a block down to what the table leaves unsaid is a user edit that snapshot semantics protect.
- otherwise → the host is `AGENTS.md`.

A stack block found in `AGENTS.md` while `constitution` is in play is **moved**: the block, content unchanged, leaves `AGENTS.md` and appends to `tech-stack.md`. Automatic — the user is informed, not asked; it stays the snapshot it was.

### Legacy Matt Pocock rules

`mattpocock-rules` is an inline module in root `AGENTS.md`. For an older pointer block, treat its referenced rules file as the existing module snapshot: **keep** carries that content and its project edits into the block; **overwrite** takes the current module template. If the referenced file is missing, restore from the current inline template. Retain the old file for the project's own cleanup; re-runs manage only the inline block.

### Block format

One block per module in its host file — `constitution-doc/CODE_REVIEW_STANDARDS.md` for `code-style`, `constitution-doc/tech-stack.md` for a stack module when `constitution` is in play, otherwise `AGENTS.md`:

```markdown
<!-- module:backend-python -->
…snapshot of modules/backend-python.md…
<!-- /module:backend-python -->
```
