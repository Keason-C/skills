# 11 — A support agent can read a Verdict in the terminal

**What to build:** a small TypeScript CLI that takes the path to a Verdict JSON file, validates it
with zod, and prints it readably — with escalation and injection impossible to miss. `--json`
prints the normalised object instead. Anything that fails validation exits non-zero with a clear
message rather than printing half a Verdict.

**Blocked by:** 10

**Status:** ready-for-agent

- [ ] A Verdict produced by the Python side validates and prints
- [ ] A Verdict with a tampered enum value, a confidence out of range, or a missing field is
      rejected
- [ ] Extra unexpected fields are rejected
- [ ] Escalation and injection are prominent in the human-readable output
- [ ] `--json` emits the validated object; invalid input exits non-zero
- [ ] The tests run offline and read fixtures the Python side actually produced
