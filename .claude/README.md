# Getting third-party skills into every session — two approaches, tested

Goal: make Matt Pocock's skills available to sessions on this repo — including
to **subagents** — reliably enough to drive an issue loop in a fresh cloud
sandbox.

Two approaches were tested against Claude Code 2.1.221 using headless
(`claude -p`) sessions. **Approach B is what this repo ships.**

---

## Approach A — plugin injected via project config

`.claude/settings.json` declares the marketplace and enables the plugin; no
skill files live in the repo:

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

### What worked

Once bootstrapped, skills appear as `mattpocock-skills:<name>`, and **subagents
can invoke them**. A `general-purpose` subagent called
`Skill{skill: "mattpocock-skills:tdd"}` and reported content only present in the
skill body (the term *seam*, the files `tests.md` / `mocking.md`, the
anti-pattern *horizontal slicing*).

### What broke

1. **Only 9 of 22 skills are reachable.** The other 13 set
   `disable-model-invocation: true` — including every issue-loop skill
   (`to-tickets`, `triage`, `to-spec`, `implement`, `wayfinder`). Subagents get:

   ```
   Skill mattpocock-skills:to-tickets cannot be used with Skill tool
   due to disable-model-invocation
   ```

   They work only as slash commands typed in a user turn.

2. **The project must be trusted.** With `hasTrustDialogAccepted: false`,
   project-scoped `extraKnownMarketplaces` is ignored entirely — three
   consecutive fresh sessions registered nothing. Fresh cloud containers start
   untrusted.

3. **It does not converge in session 1.** Reconciliation is lazy and staged
   across sessions (register marketplace → record install → materialize files →
   skills visible), and it can stall with `installed_plugins.json` recording an
   install whose files were never written; later sessions then skip it. A
   `SessionStart` hook makes convergence deterministic but still runs after the
   skill listing is built, so session 1 never sees the skills. Only a pre-warm
   in the **environment setup script** fixes session 1:

   ```sh
   claude plugin marketplace add mattpocock/skills --scope project
   claude plugin install mattpocock-skills@mattpocock --scope project
   ```

---

## Approach B — local install + dynamic routing  ← shipped

Install the skills into the repo, park them where nothing auto-registers them,
and expose **one** router skill that hands out paths.

```
.claude/skills/mattpocock/SKILL.md   # the only registered skill — index + how to load
.claude/mp-skills/<name>/SKILL.md    # 41 skill bodies, not registered
.claude/reroute-skills.sh            # re-applies the layout after an upstream update
skills-lock.json                     # written by `npx skills`, enables updates
```

Installed with:

```sh
npx skills@latest add mattpocock/skills --skill '*' --agent claude-code --copy -y
.claude/reroute-skills.sh
```

The router tells the agent the bodies live at `.claude/mp-skills/<name>/SKILL.md`
and that loading one means `Read`-ing it and following it verbatim — for itself,
or by handing the path to a subagent.

### Results

| | Approach A (plugin) | Approach B (routing) |
|---|---|---|
| Subagent can reach `disable-model-invocation` skills | **no** | **yes** |
| Skills reachable | 9 of 22 | 41 of 41 |
| Works in session 1 of a cold container | no (needs pre-warm) | **yes** |
| Works untrusted | no | **yes** |
| Needs `.claude/settings.json` | yes | **no config at all** |
| Needs network at session start | yes | no (files are in the repo) |
| Registered skill entries | 9 | 1 |

The decisive test, run **cold, untrusted, with `.claude/settings.json` deleted
and `~/.claude/plugins` wiped**: asked for a triage in a subagent, the subagent
called `Skill{skill: "mattpocock", args: "triage …"}`, read
`.claude/mp-skills/triage/SKILL.md`, and applied it — reciting the skill's own
label vocabulary (`bug`/`enhancement` × `needs-triage`, `needs-info`,
`ready-for-agent`, `ready-for-human`, `wontfix`) and the one-category-one-state
rule. The same shape worked for `to-tickets`, which recited its 5-step process
and the *expand–contract* sequencing rule for wide refactors, then produced
tickets with blocking edges.

Because routing loads skills with `Read` rather than the Skill tool,
`disable-model-invocation` never applies. That flag is the single biggest reason
Approach A cannot drive an issue loop.

### Cost

The router is ~7 KB always-on (41 indexed rows) and replaces 17 registered
entries; the 41 bodies total ~167 KB and are read only on demand. Listed skills
went 43 → 27.

### Maintenance

```sh
npx skills update          # pulls upstream changes into .claude/skills/
.claude/reroute-skills.sh  # moves them back to .claude/mp-skills/ and rebuilds the index
```

`reroute-skills.sh` is idempotent, so it is safe to run any time.
