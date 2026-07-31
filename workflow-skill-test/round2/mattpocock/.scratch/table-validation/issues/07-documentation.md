# 07 — Document it the way this project documents things

**What to build:** someone reading the docs finds `validate` where they expect
it, learns exactly which JSON Schema keywords are evaluated, and is told plainly
what happens to the ones that are not.

**Blocked by:** 04, 06

**Status:** ready-for-agent

- [ ] The CLI docs gain a section for the command, in the house style, with worked examples
- [ ] The Python API docs cover `Table.validate()` and the validation result
- [ ] The supported keyword set is documented explicitly, along with the rule that anything else is rejected (ADR-0001)
- [ ] Exit code semantics are documented (ADR-0002)
- [ ] The generated CLI reference and the reference index include the new command
- [ ] The repo's own docs tests pass, including the one that fails the build for an undocumented command
