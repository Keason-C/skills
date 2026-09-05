---
name: setup-project
description: Set up a project — inject stack/workflow modules from the global template set into its CLAUDE.md as snapshot blocks (the constitution module scaffolds constitution-doc/) and install the two-way CLAUDE.md <-> GEMINI.md mirror (git hooks plus a local file watcher).
disable-model-invocation: true
---

# Set up project

Inject selected modules from this skill's `modules/` folder into the project's root `CLAUDE.md` as marked snapshot blocks (the `constitution` module also scaffolds the project's `constitution-doc/` folder) and install the two-way `CLAUDE.md` <-> `GEMINI.md` mirror. Evidence informs the user; the user decides every module. Re-runs refresh existing blocks; the set of injected blocks only grows — removing one is the user's own edit (delete the marker block).

This is a prompt-driven skill, not a deterministic script.

## Process

### 0. Language — the first question

If the project's `CLAUDE.md` already carries a `language` block, its value is the answer: skip the question and speak that language from the first word. Otherwise ask the user in English: "What language should I use when talking with you?" (English, because the answer isn't known yet.) Conduct the rest of the session in the answered language.

The answer is also the value of `{{USER_LANGUAGE}}`, rendered on injection into every template that carries it — today that is `modules/language.md`. `modules/mattpocock-rules.md` carries `{{MATTPOCOCK_RULES_PATH}}`, rendered the same way (see the mattpocock-rules file section). Agent-facing text inside every template stays English.

### 1. Explore

- Root `CLAUDE.md`, and `constitution-doc/tech-stack.md` when it exists — which `<!-- module:NAME -->` blocks does each contain, and does each block's content match the current template in `modules/`, rendered? A stack block sitting in `CLAUDE.md` while `constitution` is in play is recorded as **to move**.
- Root `constitution-doc/` — exists? Which of the content files (`README.md`, `mission.md`, `tech-stack.md`) are missing? And each method file — `CONVENTIONS.md`, plus every blank in `template/` — missing / matching the current template / differing? A filled doc says nothing about its blank; judge each blank by its own path under `template/`.
- The mattpocock overrides file, at whichever `{{MATTPOCOCK_RULES_PATH}}` applies — missing / matches the template / differs? (Only matters when `mattpocock-rules` is injected or gets selected.)
- Root `GEMINI.md` — missing / identical to `CLAUDE.md` / this skill's former pointer / other content? And the mirror artifacts: `.githooks/sync-gemini-md` missing / matches the template / differs; `.githooks/pre-commit` missing / carries the marker block (matching or differing) / exists without it; `git config core.hooksPath` value; `systemctl --user` available, and is `sync-gemini-md-<slug>.path` already enabled?
- Gather the evidence in the Modules and evidence table. Record the concrete findings (file names, dependency names), not just yes/no.

Done when every module in the table has both an injection status (injected & up to date / injected & differs / not injected, plus its host file and whether it is to move) and its evidence recorded, the set of missing constitution content files is known and each method file (`CONVENTIONS.md`, every blank in `template/`) has one of its three states, `GEMINI.md` has one of the four states above with every mirror artifact's state recorded.

### 2. Present

One line per module: name, injection status, evidence verbatim ("found `pyproject.toml`", "no signal"). Then ask, with every choice starting unselected — evidence informs, the user selects (AskUserQuestion with multiSelect works well):

- **Not injected** → user picks which to inject.
- **Injected & differs** → the snapshot ask.
- **Injected & up to date** → report as up to date; nothing to ask.
- **To move** (a stack block in `CLAUDE.md` with `constitution` in play) → a statement, "will move `backend-python` into `tech-stack.md`"; its diff status is presented like any other block.

`constitution` joins the module question like the rest. Everything that is not a module is a **statement**, not a choice: "will create `constitution-doc/` and add X, Y", "will write the overrides file at `{{MATTPOCOCK_RULES_PATH}}`", "will mirror GEMINI.md from CLAUDE.md and install the sync hooks + watcher" — or "in place" where nothing is missing. Beyond the module choices only two things ask: a snapshot that differs, and `GEMINI.md` holding other content (fold into `CLAUDE.md`, or skip the mirror).

### 3. Confirm

Show a draft of exactly what will be written: full block content for new injections, the chosen resolution for each differing block. End the turn on the draft; the user edits or approves it in their reply.

Done when the user has replied to the draft. Step 4 runs in that next turn, on the version the user confirmed.

### 4. Write

- Create `CLAUDE.md` if missing.
- New modules: append their blocks at the end of their host file (stack modules with `constitution` in play → `tech-stack.md`, after the constitution docs have been scaffolded so the file exists).
- Refreshed modules: replace content between their existing markers in place.
- Stack blocks to move: cut the block out of `CLAUDE.md` (its markers and the blank line before them) and append it, unchanged, to `tech-stack.md`; a refresh the user chose applies after the move.
- Every line outside the markers is preserved verbatim, in both host files.
- If `constitution` was selected or its block already exists: copy every missing constitution doc file into `constitution-doc/` (creating it, and an empty `roadmap/`, if needed) — every blank into `template/` whatever the project has already filled in, and each missing content doc from its blank; overwrite a method file only where the user chose to refresh it; inject its block if not present — pinned at the top of the file, above every other block.
- If `mattpocock-rules` was selected or its block already exists: copy `agents/mattpocock-rules.md` to `{{MATTPOCOCK_RULES_PATH}}` when missing, or overwrite it where the user chose to refresh; under `constitution-doc/`, add the README row if absent.
- Install the mirror per the GEMINI.md mirror section, in this order: write `GEMINI.md` as a copy of `CLAUDE.md` (unless the user chose to skip the mirror), copy or merge the two hook files and make them executable, set `core.hooksPath` if unset, then render and enable the systemd units where available.

Done when each selected module has exactly one marker block, in its host file and nowhere else, whose content matches the confirmed draft, `constitution-doc/` contains every doc whenever the `constitution` module is in play — `template/` always holding all four blanks, and `roadmap/` present, empty until the first version — and each method file is the version the user chose, `GEMINI.md` is byte-identical to `CLAUDE.md` with both hook files executable and the watcher enabled where systemd exists (or the user chose to skip the mirror).

### 5. Done

Report per module: injected / refreshed / kept / up to date / not selected, naming the host file, and "moved to `tech-stack.md`" where a stack block moved; plus, when `constitution` is in play, which doc files were scaffolded — and that scaffolded files are templates awaiting the user's authoring, filled section by section as the project earns the content — plus each method file's outcome (scaffolded / restored / refreshed / kept / up to date); plus, when `mattpocock-rules` is in play, the overrides file outcome (written / refreshed / kept / in place); plus the mirror outcome (`GEMINI.md` mirrored / already identical / skipped; each hook file installed / merged / refreshed / kept / in place; watcher enabled / already enabled / not available on this machine). Remind the user: re-run `/setup-project` after global template updates to refresh; remove a module by deleting its marker block; `CLAUDE.md` and `GEMINI.md` are mirrors — edit either, the last write wins, so avoid editing both at once; teammates get committed consistency from the hooks once they set `core.hooksPath`, and run `/setup-project` for their own watcher.

## Reference

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
| `agent-dev` | backend or frontend evidence holds AND deps include `pydantic-ai`, `claude-agent-sdk`, `@anthropic-ai/*`, or `ai` (Vercel AI SDK) |
| `vibe-coding` | none — always presented as "no detection signal" |
| `mattpocock-rules` | mattpocock-skills plugin installed (a `mattpocock` folder under `~/.claude/plugins/cache/`) |
| `constitution` | root `constitution-doc/` already exists; otherwise presented as "no signal" (see Constitution docs below) |
| `design` | root `.design/` exists; otherwise presented as "no signal" |

### Constitution docs

The `constitution` module carries more than its block: when it is selected (or already injected from an earlier run), this skill also scaffolds the project's constitution docs from its `constitution-doc/` template folder into a `constitution-doc/` folder at the project root. The folder holds **two layers**, and each is treated differently:

- **Content** — `README.md`, `mission.md`, `tech-stack.md`, each copied from its blank in `template/`. **Fill gaps only**: a blank is copied to the doc's own path where the doc is missing, and an existing doc stays exactly as it is. Once filled in, these are living project documents that keep their content across template updates. A project scaffolded from an earlier layout (`architecture/` + `api-design.md`, `modules/`, or a combined `constitution.md`) gets the new files added beside the old ones; moving its content over is the user's own migration.
- **Method** — `CONVENTIONS.md` (how a doc here is written and when one retires) and `template/`, holding the blank of every doc: `README.md`, `mission.md`, `tech-stack.md`, `v{{N}}-{{SLUG}}.md`. The folder is where an agent looks up the intended shape of a doc — a reference to consult and copy from, not a form the doc must match. These are **fixtures** the project reads as-is, and each is a snapshot — every blank in `template/` restored no matter which docs the project has already filled in. This is the path by which method learned on one project reaches the next: improve the template, and every project's next `/setup-project` offers it.

The rest:

- **User-selected like any module.** Selecting it means the routing block and both layers; once injected, re-runs keep it in play without re-asking.
- **Copy verbatim.** `{{...}}` placeholders and template comments stay as-is; they guide whoever authors the docs later, not this skill.
- The `constitution` module block in CLAUDE.md routes to this folder; it is a snapshot like any other block.

### Stack modules

`backend-python`, `database`, `frontend-ts` and `agent-dev` are **stack modules**: what the code is built on and how it is written. Their **host file** depends on the `constitution` module:

- `constitution` in play → the host is `constitution-doc/tech-stack.md`; the blocks append at its end, and that file is the only place they live. The constitution block's tech-stack pointer is how the agent reaches them. The doc's own Core table records the project's decisions with rationale; the blocks are the defaults those decisions were made against — the two are meant to coexist, and pruning a block down to what the table leaves unsaid is a user edit that snapshot semantics protect.
- otherwise → the host is `CLAUDE.md`, as for every other module.

A stack block found in `CLAUDE.md` while `constitution` is in play is **moved**: the block, content unchanged, leaves `CLAUDE.md` and appends to `tech-stack.md`. Automatic — the user is informed, not asked; it stays the snapshot it was.

### mattpocock-rules file

The `mattpocock-rules` block stays short — the two rules every session needs plus one pointer. The per-skill overrides it points at (to-spec labels, to-tickets fields, grilling's question tool, implement's closing comment, teach paths) live in a snapshot of this skill's `agents/mattpocock-rules.md`, written whenever the module is selected or already injected. Its location is `{{MATTPOCOCK_RULES_PATH}}`, rendered into the block on injection:

- `constitution` module in play → `constitution-doc/mattpocock-rules.md`, a method file beside `CONVENTIONS.md` (no blank in `template/`). Add its row to the layout table in `constitution-doc/README.md` when the table lacks one — the user is informed, not asked.
- otherwise → `.skills-doc/agents/mattpocock-rules.md`.

### GEMINI.md mirror

Claude Code reads only `CLAUDE.md`; Antigravity and Gemini CLI read `GEMINI.md` — and Antigravity does not follow a symlink. So the project carries both files as **verbatim mirrors**, kept equal by a sync script: whichever file was modified last overwrites the other (`mtime` decides; a tie goes to `CLAUDE.md`; identical files are left untouched, so a sync never re-triggers itself). Editing either file is fine.

Three artifacts, all from this skill's `githooks/` and `systemd/` folders:

1. **`.githooks/sync-gemini-md`** — the sync script, a snapshot.
2. **`.githooks/pre-commit`** — when either file is staged, runs the script and stages both, so a commit never carries two different versions. The template is one marker block (`# >>> sync-gemini-md >>>` … `# <<< sync-gemini-md <<<`). Missing file → copy the template. Existing file without the markers → append the block before the final `exit`. Existing markers → the block is a snapshot. Both hook files must be executable. `git config core.hooksPath` unset → set it to `.githooks`; set to another path → put the two files there instead and say so.
3. **A per-project systemd user path unit** — the local watcher that keeps the files equal between commits. Render `systemd/sync-gemini-md.service` and `.path` with `{{PROJECT_ROOT}}` (absolute project path) and `{{PROJECT_SLUG}}` (project directory name) into `~/.config/systemd/user/sync-gemini-md-{{PROJECT_SLUG}}.{service,path}`, then `systemctl --user daemon-reload && systemctl --user enable --now sync-gemini-md-{{PROJECT_SLUG}}.path`. Machine-local by nature: install only where `systemctl --user` answers; elsewhere (macOS, Windows, WSL without systemd) report it as not installed and that the git hooks alone still guarantee committed consistency.

Order matters on first install: **make the two files identical before the watcher is enabled**, or the watcher's mtime rule may copy stale content over `CLAUDE.md`. By `GEMINI.md` state:

- **Missing, or identical to `CLAUDE.md`** → automatic. The user is informed, not asked.
- **This skill's former pointer** (a short file telling the reader to read `CLAUDE.md`) → automatic: overwrite it with `CLAUDE.md`. It is this skill's own artifact, not user content.
- **Other content** → show it and ask: fold it into `CLAUDE.md` (then mirror), or keep the project without the mirror (none of the three artifacts written). Content there is the user's own work; mirroring on top of it would let the mtime rule discard one side.

### Block format

One block per module in its host file — `CLAUDE.md`, or `constitution-doc/tech-stack.md` for a stack module when `constitution` is in play (see Stack modules):

```markdown
<!-- module:backend-python -->
…snapshot of modules/backend-python.md…
<!-- /module:backend-python -->
```
