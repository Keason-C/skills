# CLAUDE.md

Commodity know-how Q&A bot for a procurement department. Python, CLI-first.

## Agent skills

### Issue tracker

Issues and specs live as local markdown under `.scratch/<feature-slug>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

The five default triage roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` at the repo root plus `docs/adr/`. See `docs/agents/domain.md`.

## Engineering constraints (non-negotiable)

- Python 3.11 managed with `uv`. Tests run with `pytest`.
- **Every test must run offline.** Real LLM calls sit behind a driver interface and are written but never exercised in tests; tests use deterministic fakes.
- Never `git push`. Local commits only.
