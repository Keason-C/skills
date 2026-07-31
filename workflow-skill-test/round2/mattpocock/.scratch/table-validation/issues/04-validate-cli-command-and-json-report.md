# 04 — `sqlite-utils validate` on the command line, with the JSON report

**What to build:** `sqlite-utils validate data.db mytable schema.json` prints a
human summary and exits with a code a pipeline can gate on: `0` clean, `1`
violations found, `2` could not validate at all (ADR-0002). `--json report.json`
writes the **JSON report** for the next pipeline step. Every library control
from tickets 01–03 is reachable as an option.

**Blocked by:** 01, 02, 03

**Status:** ready-for-agent

- [ ] Clean table exits 0; table with violations exits 1
- [ ] Missing table, unreadable schema file, schema that is not JSON, and unsupported keyword all exit 2 with a message that says which
- [ ] `--json PATH` writes a JSON report containing the counts, the violations, the schema/table mismatches, and what was asked of the run
- [ ] The JSON report carries table name, database *basename*, schema file *basename* and generation timestamp — and no absolute paths
- [ ] Options exist for the scan limit, the detail cap, coercion, empty-as-null, and whole rows
- [ ] The command follows the repo's CLI conventions and is registered like its neighbours
