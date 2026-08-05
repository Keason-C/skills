# `.claude/` — session config for this repo

`settings.json` declares the [mattpocock/skills](https://github.com/mattpocock/skills)
marketplace and enables the `mattpocock-skills` plugin, so a checkout of this repo
carries its own plugin source instead of relying on per-machine setup.

## What was verified (Claude Code 2.1.222, cloud container)

Local / interactive Claude Code: works. `claude plugin install mattpocock-skills@mattpocock`
materialises the plugin cache and all 22 skills load
(`Loaded 1 skills from plugin mattpocock-skills custom path: …` ×22).

Cloud sessions (Claude Code on the web): **the declaration alone is not enough.**
From a clean container, the headless startup path registers the marketplace but never
populates `~/.claude/plugins/cache/`, so plugin lookup fails:

```
Skipping orphaned enabledPlugins entry mattpocock-skills@mattpocock: marketplace not registered
installPluginsForHeadless: starting
installPluginsForHeadless: installed marketplace mattpocock
Found 0 plugins (0 enabled, 0 disabled)
Plugin not available for MCP: mattpocock-skills@mattpocock - error type: plugin-cache-miss
```

Repeated sessions do not converge — the miss persists until `claude plugin install` is
run by hand. Unsetting `SKIP_PLUGIN_MARKETPLACE` (set by the cloud runner) does not
change this; accepting the workspace trust dialog does not change it either.

What does load on the very first cloud session, with no network and no install step, is
project-level skills committed under `.claude/skills/<name>/SKILL.md`:

```
Loading skills from: …, project=[/home/user/Skills/.claude/skills]
Loaded 14 unique skills (… user: 12, project: 2 …)
```

So: keep `settings.json` for local use; vendor into `.claude/skills/` if the skills are
also needed in cloud sessions.

## Per-repo skill config

The engineering skills (`/implement`, `/code-review`, `/triage`, `/to-tickets`) read their
repo config from **`docs/agents/`** — `issue-tracker.md`, `triage-labels.md`, `domain.md` —
as written by `/setup-matt-pocock-skills`. Upstream has no `.skills-doc/` directory at any
point in its history; if this repo uses that path, it is a local rename and the plugin
skills will not find it.
