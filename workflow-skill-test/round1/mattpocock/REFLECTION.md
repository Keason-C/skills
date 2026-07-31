# REFLECTION — running the mattpocock/skills workflow on TriageBot

Process log. One section appended as each skill/phase completes, written at the time,
not reconstructed afterwards.

---

## 0. Routing — `/ask-matt` + top-level README

**What I did.** Read `skills/engineering/ask-matt/SKILL.md` and the plugin `README.md` before
touching anything else. ask-matt describes a "main flow: idea → ship":
`grill-with-docs` → (optional prototype detour) → branch on multi-session → `to-spec` →
`to-tickets` → `implement` (which drives `/tdd` internally) → `/code-review`, with
`/setup-matt-pocock-skills` as a hard precondition, and `domain-modeling` / `codebase-design`
as "vocabulary underneath" that the other skills pull in.

**Did it clarify or interrupt?** Clarified, cheaply. ask-matt is one page and it is a genuine
router: it told me the order, told me which steps are user-invoked (so they need me to actually
stop and ask), and it told me the *shape* of the deliverables (spec → tickets → red/green
slices → two-axis review). Without it I would have defaulted to "write models, write tests,
write README", which is the same artifacts in a much worse order.

**One real ambiguity.** ask-matt says: start at `/grill-with-docs` when you **have a codebase**;
"No codebase? Use `/grill-me`". TriageBot is greenfield, but it is greenfield *into a repo I
own from turn one*, and it has a dense domain (guard rules, a triage state machine, "the LLM
only suggests"). `grill-me` is explicitly stateless — "it saves nothing locally, builds no
CONTEXT.md". Throwing away the glossary for a project whose whole risk is vocabulary drift
(escalate vs. flag, category vs. priority, suggestion vs. verdict) would have been a bad trade.
**Decision: run `/grill-with-docs`** (= `/grilling` + `/domain-modeling`) and note the deviation
here. This is the one place I knowingly did not take ask-matt's literal branch.

**Urge to skip?** No. It is the cheapest step in the whole chain.

**Overhead.** Very low — two file reads.

**What it changed.** The whole downstream ordering, plus the decision to write `CONTEXT.md`
before writing any code.

---

## 1. `/setup-matt-pocock-skills` (precondition)

**What I did.** Followed its 5-step process. Explored: no git remote, no `CLAUDE.md`/`AGENTS.md`,
no `CONTEXT.md`, no `docs/`, no `.scratch/`, no monorepo signals, `triage` skill present in the
plugin. Then wrote `docs/agents/issue-tracker.md` (local-markdown template),
`docs/agents/triage-labels.md` (defaults kept), `docs/agents/domain.md` (single-context), and a
`CLAUDE.md` carrying the `## Agent skills` block.

**Adaptations, declared.**
- The skill wants each of Sections A/B/C put to the user one at a time. All three are *tooling*
  decisions, not product decisions, so per my operating protocol I answered them myself as the
  engineer: **A** = local markdown (there is no remote and no tracker credentials — GitHub was
  not an option), **B** = keep the five default labels, **C** = single-context.
- Step 4 says "if neither `CLAUDE.md` nor `AGENTS.md` exists, ask the user which to create —
  don't pick for them". I picked `CLAUDE.md` (this is a Claude Code environment). Declared
  deviation.

**Did it clarify or interrupt?** Mildly interrupted, and I want to be honest about that. For a
brand-new empty directory with no tracker and no team, three quarters of this skill is a no-op:
it is designed for *your existing repo*, and it shows. The exploration checklist ran against a
directory containing exactly one file.

**Urge to skip?** Yes, strongly — this was the first real temptation. I did not skip it, because
`to-spec`, `to-tickets` and `code-review` all say "the issue tracker should have been provided
to you — run `/setup-matt-pocock-skills` if not", and I did not want to discover a missing
convention three steps later. That turned out to be the right call for one narrow reason: it
fixed `.scratch/<feature>/spec.md` + `.scratch/<feature>/issues/NN-*.md` as the artifact layout,
so `to-tickets` had somewhere to put things without me inventing a scheme on the spot.

**Overhead.** Real but small — three template copies and one short file. Call it 5% of effort
for maybe 5% of value. Roughly break-even, no more.

**What it changed in the output.** Only the *location* and *naming* of the planning artifacts,
plus `CLAUDE.md` existing at all. Zero effect on the code. If I had been told "use `.scratch/`,
local files" in one sentence, I would have lost nothing.

---

## 2a. `/grill-with-docs` — round 1 (interview opened, blocked on the product owner)

**What I did.** `grill-with-docs` is two lines: "run a `/grilling` session, using the
`/domain-modeling` skill". So the real content is `grilling` (interview relentlessly, one
question at a time, recommend an answer for each, look facts up instead of asking, don't act
until confirmed) plus `domain-modeling` (challenge fuzzy terms, capture them in `CONTEXT.md` the
moment they resolve, offer ADRs only when hard-to-reverse + surprising + a real trade-off).

Produced before asking anything: `CONTEXT.md` (13 terms), ADR-0001 (Guards adjudicate, Drivers
only suggest), ADR-0002 (eager enrichment, deliberately context-free first pass), and
`.scratch/triagebot/grilling-notes.md` with 12 self-answered technical decisions. Then 12
product questions went to the product owner.

**Adaptation, declared.** `grilling` insists on one question at a time ("asking multiple
questions at once is bewildering"). My operating protocol caps me at two batched rounds, so I
batched all 12. This is a real loss, not a formality: one-at-a-time lets answer #3 rewrite
question #7, and batching forces me to guess the branch structure in advance. I compensated by
making every question carry an explicit recommended default, so a silent or partial answer still
lands somewhere sane.

**Did it clarify or interrupt?** This is the step that changed my thinking the most, and it did
it in a way I did not expect. The forcing function was not the questions — it was
`domain-modeling`'s rule that `CONTEXT.md` is *a glossary and nothing else, devoid of
implementation detail*. Writing "Suggestion" and "Verdict" as two entries with `_Avoid_` lists is
what made me see that they must be two **types**, and ADR-0001 fell straight out of that. If I
had started from the TASK bullet list I would have written one `TriageResult` model that the
rules mutate in place, and the "LLM only suggests" philosophy would have been a comment rather
than something the type system enforces. That is a genuine, traceable improvement caused by a
process constraint.

ADR-0002 is the second one. The rule "only write an ADR if a future reader would wonder *why on
earth*" made me actually interrogate the retry design — and I noticed that if the first pass
already carries the tool context, the low-confidence retry is an identical call and therefore
pure theatre. I would have shipped that bug. The ADR criterion caught it *before* any code
existed.

**Urge to skip?** Yes — on the glossary specifically, before I wrote it. It felt like documentation
tax for a project I could hold in my head. That instinct was wrong here; noted with some
embarrassment.

**Overhead.** The highest of any step so far in raw effort. Worth it, but I would not claim it is
cheap: four documents before a line of code exists.

**Open at end of round 1.** Blocked on the product owner for 12 product decisions. Continuation
logged in section 2b.

---

## 2b. `/grill-with-docs` — round 2 (answers in, phase closed)

**What came back.** Six of twelve answers overruled my recommendation: threshold 1000 not 500,
confidence 0.6 not 0.70, `SATISFIED` not `POSITIVE`, BILLING added to the unknown-order
escalation set, bilingual v1 instead of English-only, and a revised priority matrix where the
amount Guard floors at P1 rather than P0. Two answers added requirements I had not thought to
ask about: injected text must never reach a tool-call argument, and `subject` needs its own
200-character cap.

**This is the part that justifies the whole interview.** Five of those six overrules are values
that appear in **test assertions** — `amount > 1000`, `confidence < 0.6`, the enum member name.
Had I shipped my own defaults, every threshold-boundary test would have been green against the
wrong number, which is the most expensive kind of wrong: confidently verified and useless. No
amount of careful implementation recovers from that. The questions were the only mechanism that
could have caught it.

The tool-argument requirement (P5) turned into ADR-0003 immediately — it is hard to reverse (it
rules out model-chosen tool calls entirely), genuinely surprising (a reader will ask why this
"agent" cannot pick its own tools), and a real trade-off (flexibility for a removed attack
class). That is `domain-modeling`'s three-part ADR test doing actual work rather than generating
paperwork.

**Where the process pushed back usefully.** Two contradictions surfaced between the answers: the
P1 definition ("blocks a core user action, e.g. payment failure") versus the P11 matrix, which
sends a calm BILLING Ticket to P3; and `P0_URGENT` being defined as "outage **or** security
event" when only the security half is reachable by any rule v1 has. My instinct was to quietly
smooth both over — add an outage-keyword detector, promote BILLING to P2. `to-spec` has a "Further
Notes" section and the tickets have acceptance criteria, both of which made "write the tension
down and follow the explicit instruction" the cheaper option than inventing scope. That is a
process constraint preventing scope creep, and I would not have resisted it unaided.

**Did it clarify or interrupt?** Clarified, decisively. The only friction was the batching
adaptation, and I felt its cost concretely: answer P6 ("no automatic refund at any amount")
reshapes what auto-resolution even means, and in a one-at-a-time interview it would have spawned
two follow-ups (does `AUTO_REFUND` remain a legal Action at all? does it set the escalation flag
or a separate needs-execution flag?). I had to settle both myself afterwards.

**Urge to skip?** Not once answers were pending — by then the value was obvious.

**Overhead.** Highest of any phase, and the only phase where I had to stop and wait. Still the
best-value step in the chain by a wide margin.

**What it changed in the output.** Six constants and one enum member — i.e. the correctness of
roughly a third of the test suite — plus ADR-0003, plus two documented tensions that I would
otherwise have papered over with unasked-for features.

---

## 3. `/to-spec`

**What I did.** Followed its three steps: explore (already done), **sketch the seams before
writing the spec**, then write to the template and publish to the tracker at
`.scratch/triagebot/spec.md` with `Status: ready-for-agent`. 30 user stories, an Implementation
Decisions section with no file paths in it, a Testing Decisions section naming six seams, an
explicit Out of Scope list, and the two unresolved tensions in Further Notes.

**Adaptation, declared.** Step 2 says "check with the user that these seams match their
expectations". Seam placement is a technical decision, so I settled it myself: `triage_ticket()`
is the primary seam and everything behavioural is observed through it; the `LLMDriver` interface
is the substitution seam; three narrow seams (model constructors, stage transition function,
tools module) carry the rejection tests.

**The step that did the most work per word: "use the highest seam possible; the fewer seams, the
better — the ideal number is one."** I had been drifting toward testing each Guard as its own
function, which is the comfortable shape and completely wrong: it would have produced a suite
that passes while the *chain* is misordered, and that breaks every time I reorder Guards without
any behaviour changing. Forcing myself to write the seam list down first is what produced the
scripted-adapter idea — substitute at the Driver interface, observe at `triage_ticket` — which
gets full control over model opinions *and* keeps every assertion at the top seam. That single
constraint is the difference between a suite I'd trust and a suite I'd delete in three months.

**Did it clarify or interrupt?** Clarified. The one part that felt like ceremony was the user
stories: the template demands "a LONG, numbered list… extremely extensive", and around story 20
I was clearly padding. Then stories 8, 14 and 25 turned out to be the exact edge assertions I
later wrote as tests (threshold *equality*, injected text having *no* effect rather than merely
being flagged, OTHER never auto-resolving). So the padding pressure did surface real cases — an
uncomfortable finding, since it means the bit that felt most like waste was partly earning its
place.

**Urge to skip?** Moderate. Having just done a deep interview, writing a formal spec feels like
saying the same thing twice, and it partly is — the grilling notes and the spec overlap heavily.
What the spec adds over the notes is the *seam sketch* and the *Out of Scope* list, both of which
directly shaped the code. The user stories mostly restate the interview.

**Overhead.** Substantial and only partly earned. If I were tuning this workflow I would cut the
user-story section by half and keep the seam sketch untouched.

**What it changed in the output.** The seam list changed the entire test architecture. The Out of
Scope list is what let me answer "should I add outage detection?" with a flat no. The user stories
changed maybe three assertions — worth something, but not their length.

---

## 4. `/to-tickets`

**What I did.** Split the spec into 12 tracer-bullet tickets, one file each under
`.scratch/triagebot/issues/`, numbered in dependency order with explicit "Blocked by" edges and
acceptance criteria, per the local-ticket template. Ticket 01 is the spine (Ticket in → Verdict
out, no Guards); 03–06 are one Guard each; 07 is adjudication and terminal outcome; 08–12 are
bilingual support, the Anthropic adapter, schema export, the TypeScript CLI, and the demo/README.

**Adaptation, declared.** Step 4 ("quiz the user: does the granularity feel right, are the
blocking edges correct") is a technical judgement, so I answered it myself.

**The constraint that bit — and it bit hard.** "Each slice cuts a narrow but COMPLETE path
through every layer — vertical, NOT a horizontal slice of one layer." My first instinct for a
greenfield library was, unmistakably, horizontal: ticket 1 = all the models, ticket 2 = all the
tools, ticket 3 = all the guards, ticket 4 = all the tests. That is the natural decomposition and
it is exactly the one `tdd` names as an anti-pattern, because it means you write every test
against imagined behaviour before any of it runs. Being forced to make ticket 01 *end-to-end but
trivial* — a real Ticket producing a real Verdict through a real stage walk, with no Guards at
all — meant that by the end of the first slice I had a running pipeline I could interrogate, and
each Guard afterwards was added against something that already worked. Every later slice's tests
were written against observed behaviour, not imagined behaviour. This is the single most
valuable constraint in the whole workflow for a from-scratch build, and it is the one I was most
inclined to ignore.

**Did it clarify or interrupt?** Clarified. The blocking edges also caught a real ordering error:
I had drafted the confidence Guard (04) as startable immediately, when it cannot be — the retry
is *defined* as "the call that receives the Tool Context", so it is blocked by enrichment (02).
Writing the edge down made the dependency obvious; in my head it had been invisible.

**Urge to skip?** Yes, and this one is the most honest complaint I have about the workflow.
Twelve markdown files for a project one agent builds in one session is real ceremony — nobody
will ever "grab the frontier", because there is only one worker and no parallelism to exploit.
The *slicing* is worth everything; the *filing* is worth very little at this size.

**Overhead.** The worst ratio so far. Maybe 20 minutes of writing, of which the thinking (the
slice boundaries and the edges) was 5 and the formatting was 15.

**What it changed in the output.** The order in which the code was built, and therefore the fact
that no test in the suite was written against imagined behaviour. The files themselves changed
nothing that a numbered list in my head would not have.

---

## 5. `/implement` driving `/tdd` — twelve slices

**What I did.** Worked the tickets in dependency order, one red-green cycle per slice: write the
test, run it and *watch it fail*, write the minimum implementation, run again. Twelve slices,
twelve observed reds. Final state: 127 pytest tests and 20 vitest tests, all offline, plus a
clean `tsc --noEmit`.

**Where the loop earned its keep — three bugs it caught that review would not have.**

1. **Slice 04 (the retry).** Writing `test_the_second_look_gets_the_facts_the_first_one_did_not`
   *before* the code forced me to assert that `driver.calls[0][1] is None` and
   `driver.calls[1][1] is not None`. That assertion is the entire content of ADR-0002, made
   executable. If someone later "simplifies" the pipeline by passing context on both calls, the
   test fails with an exact explanation.
2. **Slice 05 (refund policy).** My first draft of the guard order put the refund-execution check
   *before* the policy rewrite. The test `test_a_refund_is_never_executed_without_a_human` went
   red, and the failure told me why: the policy Guard sets `AUTO_REFUND`, so anything checking for
   money-moving Actions must run after it. Ordering bug, caught in seconds, now pinned by a test
   and a comment on `GUARD_CHAIN`.
3. **Slice 06 (injection).** The twin test — two Tickets identical but for the injected lines,
   asserted to produce the same Category, Sentiment and Action — is what forced redaction to
   happen *before* the Driver call rather than as a flag afterwards. My first instinct was
   "detect and mark"; the test says "detect and *neutralise*", and only the second design passes.

**Where it felt like overhead.** Slices 01 and 02 were nearly pure ceremony: writing a test for
`advance(NEW, ENRICHED)` before writing a five-line transition table is theatre. The value of TDD
scaled directly with how much *decision* was in the code — near zero for a data structure,
enormous for the Guard chain.

**Adaptations, declared.**
- `/tdd` says "test only at pre-agreed seams; confirm them with the user". Confirmed with myself
  as the engineer, using the seam list `to-spec` produced.
- I broke `to-tickets`' ordering once, knowingly: ticket 11 (the TypeScript CLI) requires
  "fixtures the Python side actually produced", so ticket 12's demo script had to land first. The
  blocking edge was drawn in the wrong direction and I discovered it only when I needed the
  fixtures. A real cost of front-loading the graph.
- The `anthropic` SDK is a genuine external boundary, so the adapter's tests stub the client —
  the one kind of mocking `mocking.md` allows. Nothing internal is patched anywhere in the suite.

**Urge to skip?** Constantly, on the small slices, and I gave in to it exactly zero times — but
only because the workflow made the cost of skipping visible. Left alone I would have written
slices 01–03 in one pass and lost the ordering bug in slice 05.

**Overhead.** The best ratio of any phase. Red-green costs one extra command per slice and paid
for itself three times over.

**What it changed in the output.** Guard ordering, the retry semantics, and the entire shape of
the injection defence. Not decoration — those are the three things most likely to be wrong.

---

## 6. `/code-review` (two axes)

**Adaptation, declared.** The skill spawns two parallel sub-agents so the axes cannot pollute one
another. I ran them serially myself, deliberately doing the Standards pass without looking at the
spec and the Spec pass without re-reading my own code style notes. Honest caveat: serial-in-one-head
is a weaker version of the real thing — I cannot truly un-know the spec while reviewing standards,
and the separation the skill is buying is exactly the thing my adaptation erodes.

**Standards axis — three findings, all fixed.**
- *Duplicated Code*: the policy-lookup loop appeared twice in `tools.py`, identical in shape and
  error message. Extracted to `_policy_for`.
- *Divergent config* (a Duplicated Code variant): two `_STRICT` `ConfigDict`s in two modules with
  *different* contents — one had `validate_assignment`, one did not. Worse than duplication,
  because a reader assumes they match. Unified as `STRICT_MODEL`.
- *Mysterious Name*: `Adjudication.fired(...)` reads as a predicate but records and mutates.
  Renamed to `record(...)`.

Two smells I looked at and deliberately left: guard names are bare strings rather than an enum
(*Primitive Obsession*) — they are part of the exported wire schema, so a type would have to
serialise back to those strings anyway; and `ANGER_SENSITIVE_CATEGORIES` duplicates the members of
`EVIDENCE_DEPENDENT_CATEGORIES` — same members today, two unrelated reasons, and collapsing them
would couple two rules that will drift.

**Spec axis — the finding that justifies the second axis existing.** The spec described a
**six**-Guard chain; the code has **eight**. The two extra Guards (refund-execution,
escalation-consistency) implement behaviour the product owner explicitly asked for, so the *code*
is right and the *spec* was stale. A single-axis review would very likely have missed this: the
code is internally consistent, well named, and passes every test. Only asking "does this match
what was promised?" as a separate question surfaces it. I updated the spec, including a note
saying the two Guards were found after the fact — because silently back-filling a spec to match
the code is how specs become fiction.

Also spec-axis: the Modules list omitted the injection and schema-export modules, and the
auto-resolution wording contradicted answer P8. Both corrected in the spec, with the
interpretation written down rather than assumed.

**Did it clarify or interrupt?** Clarified — but note *when* the value landed. Both axes found
things, and the two sets of findings had zero overlap, which is the strongest argument for the
two-axis split I could have produced by accident.

**Urge to skip?** Yes, and this is the most dangerous skip in the workflow, because at this point
147 tests are green and everything *feels* finished. Green tests say nothing about whether you
built the right thing — that is precisely the Spec axis's job.

**Overhead.** Low, and the only phase where I would have accepted much higher overhead for the
same findings.

**What it changed in the output.** Three code fixes and a spec that now matches reality — plus
the discovery that my own spec had drifted from my own code within a single session, which is a
useful thing to know about myself.

---

## 7. Summary — the whole chain

**Skill chain actually walked:**

```
/ask-matt (router)
  → /setup-matt-pocock-skills   (precondition: local tracker, labels, single-context docs)
  → /grill-with-docs            (= /grilling + /domain-modeling)  ← 2 rounds, 12 product questions
      ├─ CONTEXT.md (glossary)
      └─ docs/adr/0001, 0002, 0003
  → /to-spec                    (.scratch/triagebot/spec.md, seams sketched first)
  → /to-tickets                 (12 tracer-bullet tickets with blocking edges)
  → /implement                  (12 slices, each driving /tdd red→green)
      └─ /codebase-design as the vocabulary underneath (deep module, seam, adapter)
  → /code-review                (Standards + Spec, run serially instead of in parallel agents)
```

### Scores, 1–10

**Thinking-clarity gain: 8/10.**
Three specific improvements I can point at, none of which I would have reached alone. Writing the
glossary before the code turned "the LLM only suggests" from a slogan into two types. The ADR
test ("would a reader ask *why on earth*?") caught a retry that would have been pure theatre —
before any code existed. And the seam sketch in `to-spec` stopped me building a per-Guard test
suite that would have passed while the chain was misordered. Not a 9 or 10 because a chunk of the
clarity came from the *questions being answered*, which any structured interview would have
delivered — the skills sharpened that, they did not create it.

**Process overhead burden: 6/10** (higher = more burdensome).
Real and unevenly distributed. Twelve ticket files for a single-session, single-agent build is
ceremony — nobody ever "worked the frontier"; the *slicing* was worth everything and the *filing*
was worth almost nothing. The 30 user stories are roughly half padding. `/setup-matt-pocock-skills`
against an empty directory is a near-no-op. Against that: `/tdd` and `/code-review` cost almost
nothing and paid the most. If I ran this again I would keep grilling, the seam sketch, slicing,
TDD and the two-axis review, and cut ticket files and user stories by half.

**Contribution to final quality: 8/10.**
Concretely: six threshold constants and one enum member are correct only because the interview
happened — those appear in test assertions, and confidently-verified-but-wrong is the most
expensive failure mode there is. Guard ordering, retry semantics and the injection defence's
shape all came from red-green. The spec-vs-code drift came from the second review axis. The
counterfactual is not "no tests" — I would have written tests anyway — it is *worse* tests
against *guessed* thresholds in a *wrong* order.

### Honest overall

The two things I expected to resent, I resented — twelve markdown tickets and thirty user
stories, both of which restate what I already knew. The two things I would have skipped are the
two that mattered most: the glossary (which produced the type split that defines this codebase)
and the Spec axis of the review (which caught my own spec drifting from my own code inside a
single session, with everything green).

The workflow's real character is that it front-loads decisions. Almost every one of its
constraints — write the vocabulary first, sketch the seams before the tests, slice vertically,
red before green, review against the spec separately — forces a decision earlier than I would
naturally make it, when it is still cheap to change. That is genuinely different from "write the
code and then check it", and it is where the value sits.

What it is *not* is lightweight. The claim in the repo README is that these skills are "small,
easy to adapt, composable" versus process frameworks that "own the process". Half true: each
skill is short and I adapted several without friction. But the *chain* is a process, and running
it end to end on a mid-sized project produced four planning documents, three ADRs, twelve ticket
files and a glossary before the first line of code — that is not a small ritual, and pretending
otherwise would be dishonest. The right read is that the ceremony scales badly downward: on a
one-session build it is heavy, and on the multi-session build it is actually designed for
(clear context between tickets, grab the frontier, hand work to another agent) the same
artifacts would be doing real work instead of sitting there.

One more honest note: the biggest single lever in the whole run was not a skill at all. It was
being *made to stop and ask twelve questions*, and having six of the answers come back different
from my defaults. Every skill in this chain is downstream of that.
