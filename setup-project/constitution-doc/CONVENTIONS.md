# Conventions

Keep the blank templates in [`template/`](template/).

## Roadmap

- **One version, one file**, at `roadmap/v<N>-<slug>.md`. A version is the shipping unit and a **Phase is one feature**; a file holds those two levels and no more, and **one Phase maps to one spec** — write `non-spec` when it needs none. Task-level progress belongs to issues.
- **The version file's shape** is [`template/v{{N}}-{{SLUG}}.md`](template/) — copy it to `roadmap/v<N>-<slug>.md` to start one.
- **A version's Status is recorded only in [`mission.md`](mission.md)'s version table**; a version file carries Phase `Status:` alone.
- At most three files in `roadmap/`, at most one version `in-progress`.
- Once every Phase in a version is closed, archive its roadmap file and drop its row from the mission table; `roadmap/` carries only what is still ahead.
- **A distant version is a guess, not a plan.** At each version close, review the remaining version files: keep what still holds and archive superseded plans, removing their mission table rows.

### Phase progress

For a task matching an existing Phase:

- Set the Phase to `in-progress` when work starts.
- On task completion, update only active documentation that the change would otherwise make misleading.

### Archival

When a spec or version is complete or superseded, archive its materials as a unit once active work no longer needs them. Preserve project-relative paths under root `archive/` and update referring links only in active documents; archived materials are no longer maintained.
