# Repo-default skill injection — test results

This directory injects a third-party skill plugin into every session opened on
this repo **via configuration only**. No skill files are vendored into the repo.

## What is configured

`.claude/settings.json` declares the marketplace and enables the plugin:

```json
{
  "extraKnownMarketplaces": {
    "mattpocock": { "source": { "source": "github", "repo": "mattpocock/skills" } }
  },
  "enabledPlugins": { "mattpocock-skills@mattpocock": true }
}
```

`extraKnownMarketplaces` is documented as "additional marketplaces to make
available for this repository — typically used in repository
`.claude/settings.json` to ensure team members have required plugin sources."

`.claude/bootstrap-plugins.sh` runs on `SessionStart` and materializes the
plugin. It is idempotent and a no-op once the plugin is cached.

## Findings

Tested against Claude Code 2.1.221 with headless (`claude -p`) sessions.

### 1. Injection works — skills appear as `mattpocock-skills:<name>`

Once bootstrapped, a fresh session lists the plugin's model-invocable skills:

```
mattpocock-skills:tdd            mattpocock-skills:code-review
mattpocock-skills:diagnosing-bugs mattpocock-skills:codebase-design
mattpocock-skills:prototype       mattpocock-skills:domain-modeling
mattpocock-skills:research        mattpocock-skills:resolving-merge-conflicts
mattpocock-skills:grilling
```

### 2. Subagents CAN invoke injected skills

A `general-purpose` subagent spawned via the Agent tool called
`Skill{skill: "mattpocock-skills:tdd"}` successfully and reported content only
present in the skill body (the term *seam*, the files `tests.md` / `mocking.md`,
the anti-pattern *horizontal slicing*). Plugin skills are inherited by
subagents; no extra wiring is needed.

### 3. Subagents CANNOT invoke `disable-model-invocation: true` skills

9 of the plugin's 22 skills are model-invocable. The other 13 — including the
issue-loop ones (`to-tickets`, `triage`, `to-spec`, `implement`, `wayfinder`,
`setup-matt-pocock-skills`) — set `disable-model-invocation: true`. A subagent
calling them through the Skill tool gets:

```
Skill mattpocock-skills:to-tickets cannot be used with Skill tool
due to disable-model-invocation
```

They still work as slash commands typed in a user turn
(`/mattpocock-skills:to-tickets` loaded fine and its 5-step process was
recited). To use one inside a subagent, the orchestrator must read the
`SKILL.md` and pass its content in the subagent prompt.

### 4. The project must be trusted

With `hasTrustDialogAccepted: false` for the working directory, project-scoped
`extraKnownMarketplaces` is ignored entirely — three consecutive fresh sessions
registered nothing. A freshly created cloud container starts untrusted, so this
gate must be cleared before config injection does anything.

### 5. Config alone does not converge in the first session

Passive reconciliation from `settings.json` is lazy and staged across sessions
(register marketplace → record install → materialize files → skills visible),
and it can stall in a half-installed state where `installed_plugins.json`
records an install whose files were never written; later sessions then skip it.

The `SessionStart` hook makes convergence deterministic, but it still runs after
the skill listing is built, so **session 1 does not see the skills — session 2
onward does.**

For an issue loop where each issue gets a fresh container and a single session,
run the pre-warm in the **environment setup script** rather than a SessionStart
hook, so the plugin is cached before the session starts:

```sh
claude plugin marketplace add mattpocock/skills --scope project
claude plugin install mattpocock-skills@mattpocock --scope project
```

Pre-warmed this way, the very next fresh session answers `YES` to having the
skills — session 1 works.
