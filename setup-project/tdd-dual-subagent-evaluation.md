# Evaluating the TDD dual-subagent addendum

An A/B experiment on whether the **TDD dual-subagent** rule in
`setup-project/modules/mattpocock-rules.md` produces better code than the `tdd` skill
alone.

Date: 2026-08-17. Three real open-source repositories, two development tasks and one
bug fix, judged against tests the agents never saw.

---

## What was compared

Both arms load the same `tdd` skill. The addendum is an *addendum*, so the only
independent variable is the pairing rule:

| | Arm A — with the addendum | Arm B — baseline |
|---|---|---|
| Who writes tests | a dedicated Tester subagent | the same agent that writes the code |
| Who writes code | a dedicated Implementer subagent | same agent |
| Can the coder read the tests? | **no** — handover documents and failing-test output only | yes |
| Orchestration | main session adjudicates every slice | none |

Arm A was run exactly as the addendum specifies: file ownership enforced per side,
handover documents under a git-ignored `.skills-doc/tdd-pair/<feature>/`, ping-pong
reuse of the same pair across slices, and the main session verifying ownership,
re-running RED and GREEN, and committing each accepted slice.

## Task design

Each task is a real merged upstream pull request. The repository is rewound to that
PR's **parent commit**, so the tests that shipped with the PR do not exist in the
working tree. Agents get a specification written from the issue — the behavioural
contract, never the implementation. The upstream tests are held back as an oracle.

| Repo | Language | Kind | Task | Upstream PR |
|---|---|---|---|---|
| python-trio/trio | Python | feature | `MemoryChannelStatistics.peak_buffer_used` high-water mark | #3474 (issue #1723) |
| colinhacks/zod | TypeScript | feature | `.exactPartial()` on ZodObject, classic + mini | #6065 (issue #5983) |
| evanw/esbuild | Go | bug fix | minifier must prune empty `case` clauses before a trailing `default` | fix for #4359 |

The oracle was sanity-checked before use: with no implementation it fails, with the
real upstream implementation it passes.

Scoring is done on the implementation alone. Each arm's non-test changes are replayed
onto a pristine checkout, then the upstream tests are applied on top and run — so an
arm cannot score by writing agreeable tests.

## Result 1 — functional correctness: a dead tie

Every one of the six runs passes the held-out upstream tests in full.

| Task | Arm A | Arm B |
|---|---|---|
| trio | 32/32 | 32/32 |
| zod | 96/96, no type errors | 96/96, no type errors |
| esbuild | pass | pass |

No regressions either: trio 544 passed, zod 3005 passed across the classic and mini
suites, esbuild green across `./internal/...`.

## Result 2 — test strength: the baseline is consistently ahead

Passing the oracle only shows the feature works. To measure whether each arm's *own*
tests actually constrain behaviour, a neutral baseline (the real upstream
implementation) was mutated with one genuine bug at a time, and each arm's test suite
was asked whether it notices. A suite that stays green did not constrain that
behaviour.

| Mutation score | trio | esbuild | zod |
|---|---|---|---|
| Arm A (dual-subagent) | 4/5 | 4/5 | 4/5 |
| **Arm B (single agent)** | **5/5** | **5/5** | **5/5** |
| Upstream's own tests | 1/5 | 4/5 | 4/5 |

Arm B caught every mutant in all three tasks. Arm A missed exactly one in each — too
consistent to be noise.

What Arm A missed:

- **trio** — a peak wrongly raised by `receive_nowait`'s transient buffer append (a
  value passing through from a blocked sender on an unbuffered channel).
- **esbuild** — dropping the "the `default` must be the last clause" guard. Arm A
  tested the example from the specification, which is caught by an *earlier* condition
  and therefore does not isolate this guard. Arm B noticed the example was
  non-discriminating and substituted one that is.
- **zod** — the mini API silently discarding its `mask` argument.

The pattern is the same each time: **secondary paths and second API surfaces**. Arm B,
having written the implementation, knows which branches exist and aims at them. Arm A's
Tester is deliberately blind to the implementation, which is exactly what stops tests
from overfitting — and equally what leaves it unaware of the branch that needs cover.

Worth noting separately: both arms wrote considerably stronger tests than the human
authors upstream. On the trio task the real merged tests catch 1 of 5 mutants.

## Result 3 — cost: the addendum is roughly 2× and serialises the work

| | Arm A | Arm B |
|---|---|---|
| Subagent invocations | 16 | 3 |
| Subagent tokens | ~428k | ~247k |
| Main-session orchestration | ~11 adjudication rounds, each re-running the suite | none |
| Wall clock, zod task | ~27 min + main-session verification | ~14 min |

Arm B's three tasks run fully in parallel. Arm A's ping-pong is serial by construction,
and every slice adds a main-session round trip — on zod, four re-verifications at about
two minutes of type-checking each.

## Where the addendum did clearly win

- **Zero boundary violations.** Across nine Tester rounds and six Implementer rounds,
  not one agent touched the other's files. The Implementers worked purely from handover
  documents and failing-test output.
- **Minimal implementations.** Arm A's Implementers refused to build ahead of the tests —
  the zod Implementer shipped only the no-argument form until a later slice demanded the
  mask. Arm B tended to write the fuller change earlier.
- **Auditability.** Every slice leaves a handover document stating the seam, the pinned
  behaviour, and the observed RED, plus its own commit. Reconstructing why a test exists
  is trivial; in Arm B it lives only in the agent's final report.
- **One genuine find.** The zod Tester discovered that `expectTypeOf(...).toEqualTypeOf<Partial<T>>()`
  cannot distinguish `{k?: V}` from `{k?: V | undefined}` — so its own type assertion was
  vacuous — and strengthened it with `not.toExtend`. That is the precise distinction the
  feature exists to make, and the upstream tests carry the same weak assertion.

## Honest limits of this experiment

- n = 3, one run per arm per task. The mutation-score gap is consistent but small.
- All agents ran on the same strong model. Test-overfitting — the failure the addendum
  exists to prevent — did not visibly occur in the baseline arm, so the addendum was
  defending against a risk that never materialised here.
- Both arms were told to verify discriminating power by mutation when a test passed on
  arrival. Arm B's agents did this on their own initiative as well; Arm A was instructed
  to. **This requirement is not in the addendum** — without it Arm A's tests would likely
  have scored lower, since several of its slices passed by construction.
- The changes are small-to-medium (13–90 lines of implementation). Nothing here tests the
  addendum on a large refactor, where isolating the test author may pay off more.
- Arm A's main session was Claude with full context on the task, which is a stronger
  adjudicator than the addendum assumes.

## Recommendation

Do not apply the dual-subagent rule by default. On this evidence it costs about twice
the tokens and serialises the work for no gain in correctness and a small, consistent
loss in test strength.

Three changes would make it earn its cost:

1. **Give the Tester branch structure, not the diff.** The whole gap is coverage of
   secondary paths. The main session already reads the implementation during
   adjudication; it can hand the Tester a *description* of the branches that exist
   ("there is a second place the buffer is appended to, in the receive path") without
   showing the diff. That keeps the anti-overfitting property while closing the blind
   spot.
2. **Write the mutation requirement into the addendum.** "If a slice passes on arrival,
   prove the test discriminates by temporarily breaking the implementation, then revert"
   should be part of the rule, not something the orchestrator has to remember. It is what
   produced the single best find in the whole experiment.
3. **Scope it.** Reserve the pair for work where overfitting is a real risk — a large or
   long-lived change, or a codebase where tests have historically been written to match
   the implementation — rather than every task that triggers TDD.

## Reproducing

Harness lives in the session scratchpad, not in this repository:

- `exp/specs/{trio,zod,esbuild}.md` — the specifications handed to the agents
- `exp/heldout/*.patch` — the upstream tests, held back as the oracle
- `exp/verify.sh` — replays an arm's implementation onto a pristine tree and runs the oracle
- `exp/mutate.py`, `exp/mutate_esbuild.py`, `exp/mutate_zod.py` — the mutation experiments
