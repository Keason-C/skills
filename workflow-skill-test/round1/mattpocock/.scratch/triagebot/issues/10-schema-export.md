# 10 — The two languages share one schema

**What to build:** a script that exports the JSON Schema of the public models to a schema
directory, and a test that regenerates and compares — so a change to a Python model that is not
re-exported fails the suite, offline, instead of surfacing as a broken consumer later.

**Blocked by:** 07

**Status:** ready-for-agent

- [ ] Running the export writes schema files for the Ticket and the Verdict
- [ ] The committed schema matches what the current models produce
- [ ] Changing a model without re-exporting fails the comparison test
- [ ] The export needs no network and no arguments
