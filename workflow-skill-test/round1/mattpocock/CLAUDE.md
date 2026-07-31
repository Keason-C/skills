# TriageBot

A customer-support ticket triage agent. Design philosophy: **the LLM understands, deterministic rules decide.**

## Agent skills

### Issue tracker

Issues and specs live as local markdown under `.scratch/<feature-slug>/` (no git remote on this repo). See `docs/agents/issue-tracker.md`.

### Triage labels

The five canonical triage roles, used as-is (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` at the repo root plus `docs/adr/`. See `docs/agents/domain.md`.
