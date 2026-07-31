# REFLECTION.md — Spec Kit on an existing open-source codebase

Agent: speckit-runner-2. Task: 内部工单 #4821 (data-quality validation + interactive report)
on an existing checkout of `simonw/sqlite-utils`. Process log, appended one section per
workflow phase, written as I go rather than reconstructed at the end.

Baseline recorded before touching anything: `uv run pytest` → **1371 passed, 19 skipped** in
23.62s. (The task brief mentioned a "216 passed" figure for the `test_create` + `test_utils`
subset; the full-suite number above is the real regression baseline I will hold myself to.)

---

## Phase 0 — Setup and baseline

Not a Spec Kit phase, but worth logging. `specify init --here --force` on a repo that already
has 9904 lines of Python and a `.github/` directory was uneventful — it dropped `.claude/skills/`
and `.specify/` in and touched nothing else. That is the correct behaviour for a brownfield
init and I was mildly braced for worse (a `--force` flag on someone else's repo is a scary
thing to type).

One immediately useful side effect of having to read the repo before the constitution: I found
`tests/test_docs.py::test_commands_are_documented`, which parametrizes over
`cli.cli.commands.keys()` and asserts each one appears in `docs/cli.rst`. That means **adding a
CLI command without documenting it breaks the existing test suite**. On a greenfield project
"write docs" is a soft nice-to-have you can defer; here it is load-bearing and enforced. I would
have discovered this eventually by breaking the build — finding it in phase 0 instead is a
genuine, if accidental, win.

## Phase 1 — speckit.constitution

**Did it clarify thinking or interrupt it?** Genuinely clarified, and this surprised me. My
instinct was that a "constitution" for a repo I don't own is theatre — Simon Willison's project
already has a constitution, it's just implicit in the code. The urge to skip was real and it
was strong: I had a perfectly good TASK2.md with 老周's technical requirements already
enumerated, so why restate them?

What changed my mind mid-writing: filling the template forced me to go *read* `mypy.ini`,
`Justfile`, `pyproject.toml`, `docs/contributing.rst` and `.github/workflows/test.yml` and turn
them into rules, and that surfaced three things TASK2.md does not say:

1. `mypy.ini` contains `[mypy-sqlite_utils.cli] ignore_errors = True`. So 老周's "new Python
   code must pass mypy" has a hole in it — anything I put in `cli.py` is *not actually type
   checked*. That converts "library-first" from an architectural nicety into the only way to
   satisfy his requirement. I would not have noticed this by reading TASK2.md alone.
2. CI runs `mypy sqlite_utils tests` — tests are type-checked too (though `[mypy-tests.*]` sets
   `ignore_errors = True`, so in practice not).
3. `cog --check` runs in CI against `docs/*.rst`, so `docs/cli-reference.rst` is generated and
   I must re-run cog, not hand-edit it.

**Brownfield vs greenfield observation:** in a greenfield project the constitution is where you
*invent* your conventions, and it's mostly aspirational fiction until the code catches up. Here
it was an *archaeology exercise* — the conventions already exist and are enforced by CI, and my
job was to transcribe them accurately. That made it much more useful than I expected, and also
much more falsifiable: every clause I wrote can be checked against a file in the repo. Principle
II ("Existing Conventions Are Law") is the one doing real work; the generic template principles
about "Library-First" and "Test-First" would have been empty had I not grounded each one in a
specific file.

**Overhead worth it?** Yes, but partly for the wrong reason — the value came from the enforced
repo reading, not from the artifact. A phase called "read the repo and write down its rules"
would have produced the same benefit with less ceremony. The versioning/ratification-date/Sync
Impact Report machinery is pure overhead for a repo I will never amend twice.

**Constraint that actually changed the output:** the "no new runtime dependency without written
justification" principle. I had already half-decided to reach for `jsonschema` as a runtime
dep. Having written the rule down before making the decision means I now owe a real
justification in the plan, and I'm going to have to seriously price out the
"implement-the-subset-myself" alternative rather than just `pip install` my way past it.

## Phase 2 — speckit.specify

**Did it clarify thinking or interrupt it?** Mostly clarified, with one stretch of real friction.

The clarifying part: the template's insistence on *prioritized, independently testable user stories*
made me split what I had been treating as one feature into four, and the split immediately paid off.
"Validate a table" and "gate a pipeline on the result" felt like one thing when I read TASK2.md;
forcing them apart surfaced FR-010 (exit statuses must distinguish *dirty data* from *the tool
broke*). That requirement is genuinely important — a pipeline that treats "your schema file has a
syntax error" as "the data is fine" is worse than no validation at all — and it is not stated
anywhere in the ticket. Iris said "有没有问题得从退出码上看得出来", which only implies two states. I
got the third state from the template, not from the customer.

The friction: the template's "no implementation details, written for non-technical stakeholders"
rule fights the reality of the ticket. Iris *specified* JSON Schema by name and HTML by name. 老周
*specified* TypeScript and vitest. A spec that scrubs those out to stay "technology-agnostic" is
lying about its own constraints. I resolved it by drawing the line at *given business constraints*
(JSON Schema, a browser-openable file, offline operation — these stay, they're requirements) versus
*my design choices* (stdout, flag names, file extensions, module layout — these go). I wrote that
judgement call into the checklist rather than leave it implicit, because it's exactly the kind of
thing a reviewer would otherwise flag as sloppiness. But I spent noticeable time on a purely
presentational question, and on a brownfield ticket where the tech stack is dictated up front, the
"technology-agnostic" rule is closer to a tax than a benefit.

**Urge to skip?** Yes — a specific one. The checklist step ("write a checklist that validates your
own spec, then run it, then iterate up to 3 times") felt like grading my own homework, and my first
instinct was to write it green in one pass and move on. I made myself actually run it, and it
caught two real defects: a performance-budget "success criterion" (SC-004, "loads in under 2
seconds") that was untestable without pinning a machine spec, and a missing edge case — *schema
names a column the table doesn't have*. That second one matters a lot. Handled naively it silently
passes every row, which is the single worst failure mode a validation tool can have, and I did not
have it in the draft. So: the step I most wanted to skip was the step with the highest yield. Noted,
and slightly annoying.

**Brownfield vs greenfield:** the "Assumptions" section did more work here than it would greenfield.
On a new project, scope boundaries are whatever you say they are. On an existing project with a
stated philosophy — the README says outright "sqlite-utils is not intended to be a full ORM: the
focus is utility helpers" — the assumptions section became the place where I justify *not* building
things the ticket gestures at. Auto-fixing dirty data, cross-table referential checks, storing run
history: all plausible readings of "data quality", all wrong for this project. Writing them down as
explicit non-goals is more defensible than silently omitting them, and I only knew where to draw the
line because the project already has a stated identity to defer to.

**Constraint that actually changed the output:** the 3-marker cap on [NEEDS CLARIFICATION]. I had
six genuine product questions. Being forced to rank them made me notice that the type-coercion
question (Q1) is not a detail but a feature-killer — CSV-loaded SQLite stores nearly everything as
TEXT, so strict JSON Schema `type: integer` would flag *every row of every CSV-derived table*. The
cap pushed that from "one of six questions" to "the question", which is the right emphasis. The
other three got demoted to clarify-phase questions with defensible defaults, which is honest.

## Phase 3 — speckit.clarify (questions asked, awaiting answers)

**Did it clarify thinking or interrupt it?** This is the phase I expected to resent and didn't.

The taxonomy scan is a 29-row checklist covering things like "rate limiting", "observability",
"compliance", "conflict resolution" — for a local read-only CLI command, most of it is obviously
inapplicable, and grinding through it felt like filling in a form. But two rows earned their keep:

- **Security & privacy** came out **Missing**, and that is a genuine miss on my part. The whole
  point of this feature is that the report gets *forwarded out of the data team to operations*, and
  the report necessarily embeds raw cell values — the offending value is the most useful thing in
  it. So the feature's core deliverable is "take the dirtiest rows of a production table and email
  them to a wider audience". Nobody in the ticket raises this, I hadn't thought about it, and I
  would have shipped a privacy decision by accident. The generic checklist caught it purely by
  being generic. That is the single best argument for the taxonomy I can make.
- **Identity & uniqueness** came out Partial and pushed me to go look at how the repo already
  identifies rows, which is how I found `Table.pks` returning `["rowid"]` when `use_rowid` is true.
  Following that gives me row identifiers consistent with the rest of the library for free.

**The distinction I had to enforce myself:** the skill happily generates questions about anything
Partial. The ticket says business decisions go to Iris and technical ones are mine. So I explicitly
split the queue and wrote the dropped candidates into `clarification-session.md` with their answers
and rationale, rather than letting them silently vanish or, worse, spending scarce question budget
on things I'm supposed to decide. Four candidate questions got resolved that way. Iris said "别自己
猜我的业务" — she did *not* say "ask me about exit codes", and asking would waste her time and signal
I hadn't read her message.

**Where the process actively got in the way:** the skill mandates a strictly sequential loop, one
question per turn. My question delivery to Iris is asynchronous with a two-round budget, so
sequential questioning would burn the whole budget on questions 1 and 2 of 5. I deviated and asked
all five at once. I wrote the deviation and its justification into the artifact instead of quietly
ignoring the instruction, because a silently-broken process step is worse than a documented
departure from one. Still: this is a real design assumption in Spec Kit (synchronous human at a
terminal) that doesn't survive contact with asynchronous stakeholders.

**Brownfield note:** in a greenfield project, "Identity & uniqueness rules" is a question you'd have
to ask someone. Here the answer was sitting in `db.py` and the only correct move was to copy it.
That is a recurring pattern this run — the brownfield version of clarify is significantly *shorter*
on the technical axis, because the codebase has already answered most of the technical questions,
and correspondingly *sharper* on the business axis, because those are the only ones genuinely open.
The taxonomy doesn't know this, so I had to do the sorting by hand.

**Overhead:** moderate and worth it, mostly for the privacy catch. If I'd skipped this phase I'd
have gone into planning with a type-coercion policy I'd invented, which — given that CSV import
stores everything as TEXT — could easily have produced a tool that flags 100% of rows in every real
table and looks like it's working.

## Phase 3b — speckit.clarify (answers integrated)

Iris overrode **two of my five recommendations**, and both overrides made the design better. That is
worth recording honestly, because the tempting lesson from a smooth clarify phase is "I should have
just decided these myself and saved a round trip". This run is direct evidence against that.

- **Q1**: I recommended lenient type checking by default, reasoning that strict checking would flag
  100% of rows on CSV-loaded tables and make the tool look broken. Her answer: that 100% figure *is
  the finding*. The tool's job is to tell her the CSV arrived untyped, not to hide it behind a
  coercion rule. I was optimising for the tool looking good; she was optimising for it being honest.
  She also killed my actual objection — that an undifferentiated wall of violations is useless — with
  a better fix than mine: split type failures into *coercible* (`"42"` vs integer) and *invalid*
  (`"abc"` vs integer) so a strict run is still triageable. That is a genuinely better design than
  the one I proposed and I would not have arrived at it.
- **Q4**: I recommended NULL = "value absent" so `required` would catch empty CSV cells. She chose
  the JSON-Schema-faithful reading: the column always exists, so `required` never fires on NULL;
  `type` rejects it unless the schema says `"null"`. Consequence: nullability becomes something the
  schema author must *state*, and the tool never decides on their behalf. Consistent with her Q3
  answer ("don't invent private rules on top of JSON Schema"). More principled than mine.

**The integration step earned its keep, and not in a way I anticipated.** The skill's instruction —
"If the clarification invalidates an earlier ambiguous statement, replace that statement instead of
duplicating; leave no obsolete contradictory text" — sounds like documentation hygiene. It is not.
Q4's answer **inverted an acceptance scenario I had already written**: US1 scenario 3 asserted that
a NULL in a required column produces a *required* violation. Under Iris's answer it produces a
*type* violation and `required` never fires. Had I appended the clarification and left the scenario
in place, I would have had a spec containing two contradictory statements about the same case, and —
because I write tests from acceptance scenarios — a decent chance of implementing the stale one.
The knock-on was larger than the edit: with `required` no longer firing on NULL, it now only fires
for a column missing from the table *entirely*, which is a table-level fact, which forced FR-003 to
be restated as "emitted once per run, not once per row". One answer, three cascading corrections.
That cascade is the real product of this phase.

**Cost:** the mechanical part of integration was tedious — eight separate edits across scenarios,
edge cases, FRs, entities, assumptions, and success criteria, plus a checklist re-validation pass.
Perhaps 20% of the phase's effort was genuine thinking and 80% was propagating consequences by hand.
A tool that could trace "which sections depend on this answer" would collapse that, but Spec Kit
doesn't; it just tells you to do it, and it's on you not to miss one. I grepped for leftover
`NEEDS CLARIFICATION` and stale `clarification Q` cross-references at the end precisely because I did
not trust myself to have caught them all by reading.

**Brownfield note:** nothing about this phase was brownfield-specific — clarify is about the
requester's business, and the business doesn't care how old the codebase is. This is the one phase
so far that would have played out identically on a greenfield project. Worth saying plainly, since
the question I'm tracking is where brownfield changes the value of each step: here, it doesn't.

## Phase 4 — speckit.plan

**The single most valuable thing in this whole run happened here, and the process gets partial
credit for it.**

The plan template has a "Primary Dependencies" field and the constitution has a "justify every new
runtime dependency" clause. Between them, I was forced to actually *look up* what `jsonschema`
depends on instead of reaching for it reflexively. What I found:

- `jsonschema` 4.26.0 → `attrs`, `jsonschema-specifications`, `referencing`, **`rpds-py`**.
- `rpds-py` is a compiled Rust extension.
- Every one of `sqlite-utils`'s six current runtime deps ships as `py3-none-any` — pure Python, no
  binary, installable anywhere with an interpreter.

So adding `jsonschema` would make `sqlite-utils` — a library installed into all sorts of constrained
and air-gapped environments — require a binary wheel or a Rust toolchain, **for every user, whether
or not they ever run `validate`**. And `format` support, which Iris explicitly asked for, needs the
`[format]` extra: another eight packages. The "obvious" choice was about twelve transitive
dependencies wearing a trenchcoat.

Two further things fell out once I looked properly, and they inverted the decision rather than just
softening it:

1. `jsonschema` is *specified* to ignore unknown keywords — that is correct JSON Schema behaviour.
   But FR-002b demands the opposite: loudly reject them. So I would have had to walk the schema and
   reject unknowns **myself anyway**. The dependency doesn't remove that work, it just sits next to it.
2. FR-008b's coercible/invalid split doesn't exist in JSON Schema at all. Also custom code, also
   on top of the library.

Which means the library would have done maybe 60% of a 15-keyword job while adding 12 dependencies
and a compiled extension. Writing it in-tree is *less* total code and zero dependencies. I want to be
honest that I did not reason my way to this from first principles — I went looking because a template
field and a constitution clause made me, and the evidence did the rest. That is process earning its
keep, even if it's slightly deflating about my own instincts.

**Where the brownfield context did the heavy lifting again:** the `mypy.ini` finding from Phase 1
came back and *determined the architecture*. `[mypy-sqlite_utils.cli] ignore_errors = True` means any
logic I put in `cli.py` is invisible to mypy. 老周 requires new Python code to pass mypy. So
"library-first" stops being an architectural preference I could trade away under time pressure and
becomes the only arrangement that satisfies a stated requirement. On a greenfield project,
"library-first, CLI thin" is a principle you nod at and then erode. Here the repo's own config makes
it load-bearing. I could not have learned that from the ticket.

Same pattern with the exception type: my instinct was a fresh `TableNotFound`. `db.py` already has
`NoTable` for exactly this. Constitution Principle II says convention wins, so `NoTable` it is. Small
thing, but it's the kind of small thing that gets a PR rejected upstream.

**Friction, honestly:** the template's Project Structure section ships three commented-out layout
options (single project / web app / mobile+API) and instructs you to delete the unused ones. For a
feature that adds one Python module to an existing package, none of the three fit, and I spent real
time on what is essentially template debris. Similarly "Performance Goals: 1000 req/s" and
"Scale/Scope: 10k users" are prompts shaped for a web service. The template is visibly written for
greenfield product work and fits an upstream library contribution poorly. I filled the fields
honestly rather than leaving placeholders, but several are near-vacuous.

**The gate table was worth more than I expected**, for one specific reason: re-evaluating the five
principles *after* the design existed made me notice I had no plan for FR-002b's "reject unsupported
keywords" beyond a vague intention. I flagged it explicitly for `/speckit-analyze` to verify. It is
precisely the requirement most likely to get quietly dropped — ignoring unknown keywords is less
work *and* is what the JSON Schema spec itself prescribes, so a reasonable implementer could skip it
and feel correct. Writing that flag down is cheap insurance against my future self.

**Overhead:** this was the most expensive phase so far (five artifacts: plan, research, data-model,
three contracts, quickstart) and, unlike phases 1–3, most of it is genuinely reusable — the contracts
are what I'll write tests against, and `json-output.md` is a real API-stability commitment. Worth it.

## Phase 5 — speckit.tasks

**The step I was most ready to dismiss, and it produced one concrete save.**

Going in, my honest expectation was that this phase is bureaucratic transcription — I already had a
plan, a data model, and three contracts; enumerating 56 checkboxes felt like turning a design I
already understood into homework. Two-thirds of that expectation was right. Writing out T014–T024
told me nothing I didn't know from `data-model.md`.

The one-third that wasn't: **the template forces a "Polish & Cross-Cutting" phase, and putting docs
tasks there made me realise they aren't polish at all.** `tests/test_docs.py::test_commands_are_documented`
parametrizes over `cli.cli.commands.keys()` and asserts each name appears in `docs/cli.rst`. So the
moment T025 registers `@cli.command()` for `validate`, the *pre-existing* test suite starts failing
and stays failing until T048 writes the docs. Same for `cog --check` in CI and T050. I wrote an
explicit note into the phase — "Phase 7 is not optional polish" — because a reasonable reader
(including me, later, under time pressure) sees "Polish" as the droppable phase. On a greenfield
project it usually is. Here two of its nine tasks are load-bearing for a green build.

That's the sharpest brownfield-vs-greenfield contrast I've hit so far. Greenfield: docs are a
courtesy you write if there's time. Brownfield with a docs-completeness test: docs are a build
dependency of the feature, and the task list has to say so or it lies about what "done" means.

**Second thing the structure gave me:** organising by user story rather than by layer surfaced that
the entire frontend track (T031–T037) depends only on `contracts/json-output.md` — not on any Python
code existing. If I'd organised by layer ("all models, then all services, then all UI") that
parallelism would have been invisible, and I'd have serialised the frontend behind the validator for
no reason. The contract is what decouples them, and the contract only exists because Phase 1 made me
write one.

**Where it grated:** "Tests are OPTIONAL: Only generate test tasks if explicitly requested." For a
contribution to a mature open-source project with a 1371-test suite and a constitution I wrote saying
tests are non-negotiable, that default is simply wrong, and I had to open the file with a paragraph
overriding it. It's a small thing but it reveals the template's assumed audience: someone prototyping,
not someone contributing upstream. A brownfield-aware Spec Kit would invert that default when it
detects an existing test suite.

**Also grating:** 56 tasks is more ceremony than this feature needs. Perhaps 15 of them are real
decisions; the rest are "write the test for the thing you just designed". I don't regret writing them
— the checklist is a useful execution ledger and I'll tick through it — but I'd be lying if I called
the enumeration itself insight-generating. The insight was concentrated in the *dependency graph* and
the *phase ordering*, not the task bodies.

**Cost/benefit:** the cheapest phase so far in thinking-per-word, the most mechanical, and it still
paid for itself once (the Phase 7 realisation). Marginal call. I'd keep it, but I'd want it shorter.

## Phase 6 — speckit.analyze

**This phase caught a factual error that had propagated through every artifact, and I would have
shipped it.**

The finding: I had been asserting, in `spec.md`'s Assumptions, in `research.md` D9, in `quickstart.md`,
and — most embarrassingly — **in the argument I made to Iris when recommending lenient typing for
Q1**, that "CSV import stores everything as TEXT". Analyze made me build a coverage map instead of
eyeballing one, and while checking whether the quickstart's expected outcomes were actually testable I
ran the import for real:

```
CREATE TABLE "events" ("id" INTEGER, "age" TEXT, "status" TEXT);
```

`sqlite-utils insert --csv` **type-detects**. `id` became INTEGER because every value parsed; `age`
stayed TEXT because one row contains `"abc"`. The premise was half wrong. Consequences:

- My quickstart's expected-violations list was simply incorrect — it predicted `type-coercible` on
  `id`, which will not happen. Anyone implementing against it would have chased a phantom bug.
- The empty CSV cell becomes `''`, **not NULL** — so the NULL-semantics path (Q4, FR-008d) isn't even
  exercised by my own demo data. FR-008e governs it instead. I'd have written a NULL test that
  silently tested the empty string.
- Strict mode is *narrower and better* than I told Iris it would be: it flags exactly the columns that
  failed to type cleanly on import, rather than everything. Her Q1 answer was even more right than
  she knew, and my objection to it was built on a false premise. Slightly humbling.

The lesson I'll actually keep: I stated a confident empirical claim about a codebase's behaviour
without running it, then reused that claim as an argument to a stakeholder, and it survived four
artifacts because nothing in phases 2–5 required me to check. **Analyze is the only phase whose job
is to distrust the earlier phases**, and on a brownfield project that is worth a great deal more than
on greenfield — because on greenfield your assumptions are about code you haven't written yet
(unfalsifiable, harmless), whereas here they were about code that already exists and could have been
checked at any moment with one command.

**Other real findings** (7 total, 0 constitution violations):
- `format` was mandated by FR-002a but *nowhere* was it stated which format values are supported, or
  what happens for `{"format": "uuid"}`. That directly contradicts FR-002b's "never silently pretend"
  — an unrecognised format would have validated nothing while appearing to constrain. Added FR-002c
  plus tasks T015a/T024a.
- **FR-022b — the privacy control from Iris's Q5 — had an implementation task and zero test tasks.**
  The single requirement most tied to a stakeholder's explicit concern, untested. Added T043a.
- FR-022a mandated truncation "when excessively long" with no threshold anywhere. Vague adjective,
  exactly what the ambiguity pass is for. Pinned at 200 chars, added T043b.
- 8 of 40 FRs had no explicit task citation (80% traceability). All were implicitly covered, but at
  implement time I tick tasks, not requirements — an uncited requirement is one I can't prove I did.
  Now 41/41 = 100%.

**The read-only constraint was worth obeying.** My instinct on finding the CSV error was to
immediately go fix the quickstart. Holding off and completing the full detection pass first is what
surfaced F2 and F3 — if I'd context-switched into fixing, I'd have fixed one thing and moved on. I
verified compliance with `git status` (clean tree) before starting remediation, then applied fixes as
an explicitly separate, committed step.

**Cost:** high effort, highest yield of any phase. The mechanical coverage-map script took minutes and
found the traceability gaps; the factual error came from being suspicious enough to *run* the thing I
had been asserting. That suspicion is the phase's actual contribution — the template just creates the
occasion for it.

**Brownfield verdict for this phase: strongly more useful.** Every one of my assumptions here was
checkable against existing code, and one was wrong.

## Phase 7 — speckit.implement

**The plan mostly held, and where it didn't, the gates caught it.** Six things went wrong that the
artifacts had not anticipated. Recording them honestly, because "the plan worked perfectly" would be
a lie and the interesting content is in the gaps:

1. **`test_commands_are_documented[validate]` failed exactly as predicted.** The one thing the
   planning phases *did* foresee. Registering the command broke a pre-existing test until `docs/cli.rst`
   was written. Vindicated the "Phase 7 is not optional polish" note I put in `tasks.md`.
2. **Adding `frontend/` and `specs/` to the repo root broke the Python build.** setuptools flat-layout
   auto-discovery suddenly saw three top-level packages and refused to build — which broke `black`,
   `flake8` *and* `mypy` simultaneously, since `uv run` rebuilds the editable install. Nothing in any
   artifact predicted this. It is a purely brownfield failure: a greenfield project would have had
   explicit packaging from day one. Fixed with `packages = ["sqlite_utils"]`.
3. **Vite 8 dropped bundled esbuild** (it ships rolldown/oxc now), so `minify: "esbuild"` failed. My
   plan named "vite or esbuild" as interchangeable; in Vite 8 that is no longer true.
4. **Click 8.4 removed `CliRunner(mix_stderr=...)`.** I wrote the test helper from memory of an older
   Click. The repo pins `click>=8.3.1` and has 8.4.2 installed.
5. **`ty` — the repo's *second* type checker — flagged 14 new errors while mypy was clean.** I had
   read `mypy.ini` carefully and completely missed that `Justfile` also runs `uv run ty check`. Every
   error was the same root cause: `isinstance(x, dict)` narrows to `dict[Unknown, Unknown]`, so
   indexing with a string key is rejected. Fixed with explicit `cast(dict[str, Any], ...)` at the two
   narrowing points. Baseline had 1 pre-existing diagnostic; I ended at 0 new.
6. **codespell rejected "unparseable"** (wants "unparsable"). A linter I did not know existed until it
   ran.

Items 5 and 6 are the honest indictment of my Phase 1 archaeology: I wrote a constitution claiming to
have transcribed the repo's rules, and I still missed two of its six linters. Reading `Justfile`
*properly* — rather than skimming it — would have caught both. The constitution said "existing
conventions are law" and I still only learned half the law.

**Two real bugs found by tests I wrote from the spec, not from the code:**

- **Long values leaked in full through the `message` field.** I had carefully truncated the `value`
  field at 200 chars (FR-022a) and then embedded `{value!r}` unbounded into eleven message strings.
  A 900-character cell would have shipped whole into a report that claims to truncate. Caught by
  `test_long_values_are_truncated_in_the_report`, which exists *only* because the analyze phase
  forced me to pin a threshold and add a test task (T043b). Direct causal chain: analyze finding →
  task → test → bug caught. That is the clearest evidence in this whole run that the process paid.
- One test failure was **my test being wrong, not the code** — I asserted the string `window.pwned`
  must not appear anywhere in the HTML, but it legitimately appears as inert escaped JSON data. The
  actual guarantee (`</script>` escaped to `</script>`, exactly two `<script` tags) held.
  Worth distinguishing: one of my two "failures" was a real defect, the other was an over-strict
  assertion. Blindly "fixing code until tests pass" would have weakened a security property.

**On writing tests from acceptance scenarios:** because US1's scenarios had been *corrected* during
clarify (Q4 inverting the NULL case), I wrote `test_null_does_not_trigger_required` asserting the
counter-intuitive behaviour. Left to my own instincts I would have written the opposite assertion and
"proven" the wrong thing. The spec→scenario→test chain carried Iris's decision all the way into
executable form without me re-deciding it at 2am. That is the mechanism working as advertised.

**Final verification beyond the checklist:** I rendered the *actual generated artifact* in jsdom and
drove column filter, kind filter, search, sort and row expansion against it. Static assertions that
"no https:// appears" prove absence of a link; they do not prove the thing works. It does: 5
violations render, filtering to `status` yields 1, to `type-coercible` yields 2, search "banana"
yields 1, and expansion shows expected-vs-actual. Worth the extra step — nothing in `tasks.md` asked
for it, and "the tests pass" is not the same as "a person can open it".

---

# Final assessment

## Three-dimensional score

### 1. Thinking-clarity gain: **8/10**

Spec Kit made me think better in ways I can point at concretely, not vaguely:

- The **dependency decision (D1)** is the headline. A template field ("Primary Dependencies") plus a
  constitution clause ("justify every runtime dependency") made me actually look up `jsonschema`'s
  dependency tree instead of reaching for it. Finding `rpds-py` — a compiled Rust extension — in a
  project whose six runtime deps are *all* pure-Python `py3-none-any` wheels inverted the decision.
  And once I looked properly, the library couldn't satisfy FR-002b (it's *specified* to ignore
  unknown keywords) or FR-008b (coercible/invalid split doesn't exist in JSON Schema) anyway. The
  "obvious" choice was ~12 transitive dependencies doing 60% of a 15-keyword job.
- The **clarify taxonomy** flagged Security & Privacy as *Missing* — and it was. The feature's core
  deliverable is "email the dirtiest rows of a production table to a wider audience". I hadn't
  thought about it; the ticket doesn't raise it; a generic checklist caught it by being generic.
- The **analyze phase** caught a factual error I had propagated through four artifacts *and* used as
  an argument to the stakeholder: "CSV import stores everything as TEXT". It doesn't —
  `insert --csv` type-detects, and `id` became INTEGER. I asserted it four times without once running
  the command.

Not 10 because a large fraction of the artifact volume was transcription, and because two of the
best findings (privacy, CSV typing) came from *generic suspicion*, which a good reviewer supplies
more cheaply than seven phases do.

### 2. Process-overhead burden: **6/10** (6 = substantial but tolerable)

Roughly 12 artifacts and ~3,500 lines of process documentation for ~1,100 lines of shipped code.
Specific dead weight:

- The plan template ships three commented-out project layouts (single/web/mobile) and prompts like
  "Performance Goals: 1000 req/s", "Scale/Scope: 10k users". None fit a CLI library. Visibly written
  for greenfield web products.
- `tasks.md` at 60 items is maybe 15 real decisions and 45 lines of "write the test for the thing you
  just designed". The value was in the *dependency graph* and phase ordering, not the task bodies.
- The clarify taxonomy has 29 rows; ~22 are inapplicable to a local read-only CLI (rate limiting,
  availability, conflict resolution, observability).
- **"Tests are OPTIONAL"** in the tasks skill is actively wrong for an upstream contribution to a
  repo with 1,371 existing tests. I had to open `tasks.md` with a paragraph overriding it.
- The clarify skill mandates strictly sequential one-question-at-a-time interaction, which assumes a
  human at a terminal. With an async stakeholder and a two-round budget that had to be deviated from
  and documented.

Integration overhead was real too: Iris's Q4 answer inverted one acceptance scenario, which cascaded
into rewriting FR-003, and propagating that by hand across eight edits was ~80% mechanical. Spec Kit
tells you to keep artifacts consistent; it gives you no help doing it.

### 3. Contribution to final quality: **8/10**

Traceable, causal contributions — not "it felt more organised":

- **Zero new runtime dependencies** instead of 12 transitive + a Rust extension (D1).
- **Library-first architecture**, forced by discovering `[mypy-sqlite_utils.cli] ignore_errors = True`
  while writing the constitution. Logic in `cli.py` would have silently escaped the type checking the
  Tech Lead required. Architecture determined by a config file I only read because a phase made me.
- **FR-002b** (reject unsupported keywords) survived to implementation *because* I flagged in
  `plan.md` that it was the requirement most likely to be dropped — it's less work to ignore unknown
  keywords, and doing so is what the JSON Schema spec prescribes. It now has 8 dedicated tests.
- **A real truncation bug caught** via analyze→task→test→bug. Long values leaked whole through
  `message` while `value` was dutifully truncated.
- **NULL semantics implemented as Iris decided, not as I'd have guessed.** The corrected acceptance
  scenario carried her counter-intuitive answer into a test I would otherwise have written backwards.

Not 10 because implementation still surfaced six things no artifact predicted (setuptools layout,
Vite 8's minifier, Click 8.4's API, the `ty` checker, codespell, jsdom timing). Planning did not
eliminate discovery; it front-loaded the *decisions* and left the *integration facts* to be learned
the hard way — which is, I think, the honest ceiling for any up-front process.

## Brownfield vs greenfield — the question I was asked to track

**More useful on brownfield:**
- **constitution** — becomes archaeology rather than aspiration. Every clause is checkable against a
  file, so it's falsifiable instead of decorative. This is where I found the `mypy.ini` exclusion and
  the docs-completeness test that together shaped the architecture.
- **analyze** — dramatically more useful. On greenfield your assumptions concern code you haven't
  written (unfalsifiable, harmless). Here every assumption was checkable *right now* with one
  command, and one was wrong. Analyze is the only phase whose job is to distrust the earlier phases.
- **tasks** — specifically the phase ordering. Discovering that "Polish" contained two tasks required
  for the *pre-existing* suite to stay green is a brownfield-only insight.

**Less useful / actively obstructive on brownfield:**
- **specify's "technology-agnostic, for non-technical stakeholders" rule.** The stack was dictated in
  the ticket and half the constraints are inherited from the repo. Scrubbing them out to satisfy a
  style rule makes the spec lie about its own constraints. I spent real time on a presentational
  question with no downstream payoff.
- **plan's Project Structure section.** Three greenfield layout options, none of which describe
  "add one module to an existing package".
- **tasks' test-optionality default.** Wrong for any repo with an existing suite.
- **clarify's technical questions.** The codebase had already answered most of them (`Table.pks` for
  row identity). I had to hand-sort business questions from technical ones, because the taxonomy
  doesn't know the difference — and on brownfield that ratio shifts hard toward "already answered".

**The pattern:** Spec Kit's *divergent* phases (specify, plan structure, tasks enumeration) assume
you are inventing, and on an existing codebase you are mostly *discovering* — so they misfire. Its
*convergent* phases (constitution-as-archaeology, clarify's blind-spot taxonomy, analyze's
cross-checking) get sharper, because there is ground truth to check against. A brownfield-aware Spec
Kit would invert several defaults: tests required when a suite exists, "read the repo's linters and
CI" as an explicit constitution step, and an analyze pass that *runs* the assumptions rather than
re-reading them.

## Honest negatives

- I nearly skipped the specify-phase self-checklist as make-work. It caught two real defects,
  including the missing "schema names a column the table lacks" edge case — the worst possible
  failure mode for a validation tool. The step I most wanted to skip had the highest yield. I don't
  fully trust my own judgement about which steps are ceremony.
- I wrote a constitution asserting I'd transcribed the repo's rules, then missed two of its six
  linters (`ty`, `codespell`). The artifact projected more rigour than the work behind it had.
- Two of my five stakeholder recommendations were overridden, and **both overrides improved the
  design**. My Q1 recommendation optimised for the tool looking good on first run; Iris's optimised
  for it being honest, and her coercible/invalid split solved my own objection better than my
  proposal did. Useful calibration on the limits of "technical decisions self-decided".
- Some reflection entries were written after the fact within a phase rather than strictly during it.
  The content is accurate; the "written as I go" framing is slightly generous to me.
