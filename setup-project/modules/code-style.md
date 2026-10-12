# Code style

- YAGNI: start with concrete functions and types. A layer earns its place by isolating a real dependency, protecting an invariant, owning a lifetime, or exposing a simpler contract over existing complexity.
- Clarity: keep helpers that name a useful concept, even where inlining is shorter. Comments carry rationale, constraints, and invariants.
- DRY: knowledge that must change together has one owner. Code that merely looks alike but evolves independently stays separate.
- Contracts: validate untrusted data at runtime at trust boundaries; annotations and asserts are not validation. Inside a boundary, trust the contract and keep data typed. Model optional and alternative states explicitly.
- Fail fast: catch where you recover, clean up, or translate. A failure stays distinguishable from normal absence, never masked by a fabricated default. Retries and fallbacks need a concrete requirement.
- Change in place: update consumers and delete superseded code; keep compatibility only for supported contracts, persisted state, or rollout.
- Checker diagnostics: fix the cause. A suppression stays narrow and states the invariant that justifies it.
- Tests assert observable results through caller contracts, or of standalone internal logic. Expected values come from the spec, an independently worked case, or a trusted oracle; a tautological test proves nothing.
- Test doubles stand in at boundaries and for nondeterminism, leaving the behavior under test real. Where a double cannot establish correctness, use an integration test.
- Green honestly: production code handles its whole input domain, not just the fixtures. Assertion and snapshot changes follow intentional contract changes; skips and expected failures state their scope.
- Bug fixes: a reproducible bug gets a regression test that fails if it returns.
