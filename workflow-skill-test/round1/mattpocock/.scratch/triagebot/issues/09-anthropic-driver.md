# 09 — A real model can be dropped in

**What to build:** a second adapter at the Driver seam that talks to Claude — proving the seam is
real rather than hypothetical. It is written, typed and reviewable, but no test ever calls a
model: the suite must run with no network.

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] The adapter satisfies the same Driver interface the Mock adapter does
- [ ] Constructing it without credentials fails loudly rather than at request time
- [ ] Its response parsing turns a well-formed structured reply into a Suggestion
- [ ] A malformed or hostile reply is rejected rather than trusted
- [ ] Nothing in the test suite performs network I/O
