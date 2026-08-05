# `.claude/skills/` — Matt Pocock's engineering skills, vendored

The 22 skills of [mattpocock/skills](https://github.com/mattpocock/skills) (MIT) are
committed here as project-level skills, installed with the [skills.sh](https://skills.sh)
installer:

```sh
npx skills@latest add mattpocock/skills -a claude-code --copy -y \
  -s ask-matt -s code-review -s codebase-design -s diagnosing-bugs -s domain-modeling \
  -s grill-me -s grill-with-docs -s grilling -s handoff -s implement \
  -s improve-codebase-architecture -s prototype -s research -s resolving-merge-conflicts \
  -s setup-matt-pocock-skills -s tdd -s teach -s to-spec -s to-tickets -s triage \
  -s wayfinder -s writing-great-skills
```

`-s` takes one skill per flag (a comma-separated list matches nothing). `-a claude-code`
keeps the install to `.claude/skills/` — without it the installer also writes a duplicate
tree under `.agents/skills/`. `--copy` writes real files instead of symlinking into the
agent directory, which is what makes them survive a fresh clone.

Pull upstream changes with `npx skills update`; `skills-lock.json` at the repo root pins
the content hash of each skill.

## Cloud environment setup script

Nothing is needed — the skills are committed, so a cloud session gets them from the clone.
Leave the environment's **Setup script** box empty.

The alternative, if you ever want the skills fetched fresh instead of committed, is to put
the `npx skills add` command above into that box (it runs before Claude Code launches, so
the skills are on disk in time). Three caveats: it needs **Full** network access for the
npm registry and GitHub; it adds ~5s warm / ~30s cold to every session start; and the
fetched files land as untracked changes in `git status` every time.

`npx skills experimental_install`, which restores from `skills-lock.json` alone, is not a
substitute — it ignores agent scoping and writes to `.agents/skills/`, which Claude Code
does not read.

## Why vendored and not the plugin

The plugin route — `extraKnownMarketplaces` + `enabledPlugins` in `.claude/settings.json` —
works locally but **not in cloud sessions**. Verified on Claude Code 2.1.222 in a clean
cloud container: the headless startup path registers the marketplace but never populates
`~/.claude/plugins/cache/`, so the plugin resolves to a cache miss and nothing loads:

```
Skipping orphaned enabledPlugins entry mattpocock-skills@mattpocock: marketplace not registered
installPluginsForHeadless: installed marketplace mattpocock
Found 0 plugins (0 enabled, 0 disabled)
Plugin not available for MCP: mattpocock-skills@mattpocock - error type: plugin-cache-miss
```

Repeated sessions do not converge — the miss persists until `claude plugin install` is run
by hand. Unsetting `SKIP_PLUGIN_MARKETPLACE` (set by the cloud runner) does not change it,
nor does accepting the workspace trust dialog.

The vendored copy loads on the first session with no network and no install step:

```
Loading skills from: …, project=[/home/user/Skills/.claude/skills]
Loaded 34 unique skills (… user: 12, project: 22 …)
```

Don't add the plugin back alongside these files — upstream's README warns that installing
both leaves you with every skill twice.

## Per-repo skill config

`/implement`, `/code-review`, `/triage` and `/to-tickets` read their repo config from
**`docs/agents/`** — `issue-tracker.md`, `triage-labels.md`, `domain.md` — as written by
`/setup-matt-pocock-skills`. Upstream has no `.skills-doc/` directory at any point in its
history, so config kept under that path will not be found. Run
`/setup-matt-pocock-skills` in this repo to generate `docs/agents/`.
