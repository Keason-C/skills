# REFLECTION.md — mattpocock/skills workflow log

Agent: `mattpocock-runner-2`. Task: internal ticket #4821 (see `TASK2.md`) — data
quality validation + interactive report for `sqlite-utils`.

Workflow under test: **mattpocock/skills ("Skills for Real Engineers") v1.2.0**.
This is a process log, appended one section per skill/phase, written as I go.

Adaptation note that applies throughout: several skills want work delegated to
background agents or sub-agents (`/research`, `/code-review`'s two parallel
reviewers, `/implement`'s per-ticket fresh sessions). I am a single serial agent,
so I run those phases **serially, in-context**, and say so at each point.

---

## Phase 0 — routing via `/ask-matt` + `/setup-matt-pocock-skills`

**What I did.** Read `skills/engineering/ask-matt/SKILL.md` and the top-level
README first, as instructed, before touching anything else.

`ask-matt` routes cleanly. Its main flow is: `grill-with-docs` → (prototype
detour?) → multi-session? → `to-spec` → `to-tickets` → `implement` (which drives
`tdd` internally and closes with `code-review`). Two explicit route decisions I
made from its text:

- **Not `/wayfinder`.** The router is unusually blunt about this: wayfinder is for
  "the idea you can't hold in one session… never a well-scoped feature". #4821 is
  large-ish (Python lib + CLI + a TS frontend) but it is *not* foggy — the
  destination is described in the ticket. Using wayfinder here would have been
  process cosplay. Good that the skill told me not to.
- **Not `/prototype`.** The branch condition is "does a question need a *runnable*
  answer". Nothing here does; the open questions are product decisions for Iris
  and technical decisions I can settle on paper.
- **`/research` — yes, but narrow.** One genuinely uncertain thing (which JSON
  Schema validator, given "be sparing with new runtime deps") is exactly what
  research is for. Run serially instead of as a background agent.

Then ran the precondition skill `/setup-matt-pocock-skills`. It is written as an
interview; the three decisions it asks about are process/technical, so per my
clarification protocol I answered them myself:

- **Issue tracker → local markdown** (`.scratch/`). The remote is the upstream
  `simonw/sqlite-utils`; I must never push, and opening issues upstream would be
  worse. Written to `docs/agents/issue-tracker.md` with that reasoning added.
- **Triage labels → defaults.** The `triage` skill is installed, so the section
  ran, but `triage` is not on my route (the router says explicitly: don't triage
  tickets that `to-tickets` produced).
- **Domain docs → single-context.** No monorepo signals.
- **`AGENTS.md` vs `CLAUDE.md`:** neither existed, and the skill refuses to pick.
  Chose `AGENTS.md` — vendor-neutral, and `.gitignore`/flake8 already exclude
  `.claude/`, i.e. this repo treats Claude-specific files as untracked local state.

**Baseline recorded before any change:** `uv run pytest -q` → **1371 passed, 19
skipped** in 22s.

**Was this step clarifying or friction?** Mixed, and the split is informative.

`ask-matt` was worth it on its own — the two *negative* routing calls (no
wayfinder, no prototype) are exactly the calls I'd have got wrong by default,
because on a ticket this size the instinct is "big feature → heavyweight
planning flow". A router that tells you to use *less* process is doing real work.

`setup-matt-pocock-skills` was the first real friction. On a greenfield repo it's
a 2-minute scaffold. On someone else's mature OSS repo it means writing
agent-workflow files (`AGENTS.md`, `docs/agents/*.md`) that the actual upstream
maintainer never asked for and would likely reject in a PR. I felt a strong
urge to skip it. I didn't, because the later skills genuinely dereference
`docs/agents/issue-tracker.md` to decide where tickets go — but I noted the
footprint problem: **this workflow assumes the repo is yours.** That assumption
is invisible in greenfield and immediately awkward in a contribution context.

**Cost/benefit so far:** ~10 minutes for setup; the routing read was ~5 minutes
and prevented a much larger detour. Net positive, but only because I overrode the
"do everything the skill says" instinct exactly once (nothing — I kept it all;
the override I *considered* was skipping setup).

---

## Phase 1 — `/research` (serial, not backgrounded)

**What I did.** One question only: *what does a runtime dependency on
`jsonschema` actually cost this project?* Answered against primary sources (PyPI
JSON metadata, the Draft 2020-12 validation vocabulary, this repo's own
`pyproject.toml`), written up with citations to
`.scratch/table-validation/research/jsonschema-dependency.md`.

**The finding that changed the design.** `jsonschema` pulls `rpds-py`, a compiled
Rust extension shipping 116 platform wheels. `sqlite-utils` currently has *zero*
compiled dependencies — every one of its seven runtime deps is a pure-Python
`any` wheel. Adding `jsonschema` would make this the first `sqlite-utils` release
that can fail to install for want of a Rust toolchain. That is a genuinely
different conversation from "one more dep", and I would not have had it if I'd
gone straight to `import jsonschema` as any sane engineer would on day one.

**Was the skill worth it?** Yes, and this is the clearest single win so far. But
notice *why*: the skill's actual instruction is barely three lines ("use primary
sources, cite them, write a file"). The value came from being made to **stop and
ask one question before coding**, not from any sophistication in the skill. On an
existing codebase this lands harder than on greenfield, because the constraint
that mattered ("this project's install story is pure-Python") is a property of
the *host repo* that a greenfield project simply doesn't have. Greenfield me
would have run `npm install`-equivalent without a second thought.

**Adaptation:** run serially. The skill wants a background agent so you keep
working; serially it's a 10-minute blocking detour. Fine at this size, and I'd
guess the background framing matters much more for a 40-minute literature review.

---

## Phase 2 — `/grill-with-docs` → `/grilling` + `/domain-modeling`, round 1

**Structure of the skill.** `grill-with-docs/SKILL.md` is one sentence: "Run a
`/grilling` session, using the `/domain-modeling` skill." That composition is
elegant on paper. In practice it meant reading three files to find out what to
do, and the operative rules live in `grilling` (interview relentlessly, one
question at a time, always give your recommended answer, **look facts up rather
than asking**, don't act until confirmed) and `domain-modeling` (challenge fuzzy
terms, write `CONTEXT.md` inline, offer ADRs only when a decision is hard to
reverse *and* surprising *and* a real trade-off).

**The rule that did the most work: "if a *fact* can be found by exploring the
environment, look it up rather than asking me."** On an existing codebase this
single line converts an enormous share of would-be questions into reading. Before
writing a single question I had already settled by reading, not asking:

- how CLI commands are shaped (`@cli.command()`, `path` as `click.Path`,
  `dbtable` argument, `@output_options`, `_register_db_for_cleanup`, errors via
  `click.ClickException`) — `sqlite_utils/cli.py`
- the closest existing analogue to "inspect a table and report", `analyze-tables`
  / `Table.analyze_column` returning a `namedtuple` — `sqlite_utils/db.py:4884`
- that `tests/test_docs.py` **mechanically fails the build** if a new CLI command
  isn't documented with a `$ sqlite-utils <command>` line in `docs/cli.rst`
- that `docs/cli-reference.rst` is cog-generated and `just lint` runs `cog --check`
- that `docs/conf.py` sets `source_suffix = ".rst"`, so the `.md` files the setup
  skill made me write in `docs/agents/` cannot break the Sphinx build
- the baseline: 1371 passed, 19 skipped

**This is where the greenfield-vs-existing difference is sharpest.** In a
greenfield project, grilling is nearly *all* questions, because there are no
facts to look up — every answer is a preference. Here, the majority of the
decision tree was already decided by the repo, and the skill's job flipped from
"extract preferences" to "find the constraints already in the building". The
skill supports that (that one line), but its centre of gravity is still the
interview: it assumes the bottleneck is the human's unstated intent. On mature
OSS the bottleneck is at least as much the *codebase's* unstated intent, and
`grilling` gives you one sentence for that half while `domain-modeling` assumes
you're inventing a language rather than inheriting one.

**Adaptation.** `grilling` insists on one question at a time and on not acting
until confirmed. My clarification protocol allows one batched round to the PM.
So: batched 9 questions, each with my recommended answer (the skill's own rule),
and stopped work rather than guessing. Strictly a downgrade from the skill's
intent — a real interview would let question 4's answer reshape question 5.

**Split I enforced, per the ticket's own rule.** Product/business → Iris.
Technical → me, recorded. Drawing that line was itself useful: it exposed that
"what should the exit codes be" *feels* like a product question (it's about their
pipeline) but is really an interface convention I should just own, whereas "does
the string `"123"` in a TEXT column satisfy `type: integer`" *feels* technical
but is a pure business call about what their data is allowed to look like.

---

## Phase 3 — `/domain-modeling` output, `/to-spec`, `/to-tickets`

**Mid-flight clarification.** After the spec was drafted, Iris sent a correction:
`NULL` is **present-as-null** (JSON `null` on a field that exists), so it never
fails `required` — it fails `type` unless the schema admits null. That single
sentence invalidated a line in the spec, a glossary entry, and the meaning of the
`--empty-null` flag, and it quietly demoted `required` to a table-level-only
check. It cost about four small edits to `CONTEXT.md` and `spec.md` and nothing
else, because **no code existed yet**. That is the strongest argument I have
personally felt for this workflow: the same correction arriving two hours later
would have been a refactor of the validator's core loop plus its tests.

**`CONTEXT.md` — genuinely useful, but the skill fights the repo.** The exercise
of naming things paid for itself: forcing myself to write "**row schema** —
_Avoid_: table schema" caught a real collision, because `Table.schema` already
means the `CREATE TABLE` SQL in this codebase. Calling my thing "the table
schema" in code and docs would have been a permanent, low-grade confusion for
every future reader. `domain-modeling`'s "_Avoid_" convention is what surfaced
it; I would not have gone looking.

The friction is that `domain-modeling` assumes you are **authoring** a language.
Here I am **inheriting** one — 9,900 lines of it — and writing a repo-root
`CONTEXT.md` whose glossary is 80% my new feature is a slightly dishonest
artifact for someone else's project. On greenfield this skill is pure upside. On
mature OSS it's a good discipline wearing an awkward costume.

**ADRs — the "all three tests" filter did real work.** I had five candidate
decisions and the filter (hard to reverse ∧ surprising ∧ a real trade-off) cut it
to three. The two it killed were "use a new module instead of growing `db.py`"
(not surprising, trivially reversible) and "value truncation at 200 chars" (not a
trade-off, just a number). Without the filter I'd have written five, and the two
weak ones would have devalued the three real ones. ADR-0002 in particular is a
decision I'd otherwise have made silently in a `class` definition — `validate`
deviating from the repo's universal "everything exits 1" convention is exactly
the kind of thing a future maintainer would "fix".

**`/to-spec` — the seams step is the good bit; the user stories are padding.**
The template demands "a LONG, numbered list of user stories" and I wrote 35. I
believe roughly 8 of them changed anything about the design. The rest are
restatements at a different grammatical angle, and writing them was the first
point in this workflow where I felt I was producing documentation for the
process rather than for the work. Meanwhile **step 2 — "sketch the seams, prefer
existing seams, use the highest seam possible, the ideal number is one"** — is
the most valuable single instruction in the whole skill set so far. It's what
made me put the logic behind `Table.validate()` (next to the existing
`analyze_column()`) instead of scattering it into `cli.py`, which is *excluded
from mypy in this repo* and would have quietly voided the "new Python code passes
mypy" acceptance criterion. A seam decision protected a typing requirement.
That's the kind of second-order effect I would not have reasoned my way to under
time pressure.

**Existing-codebase note:** the seams instruction is *more* valuable here than on
greenfield, and for an unobvious reason. Greenfield seams are chosen; here they
already exist, and the skill's "prefer existing seams to new ones" is really an
instruction to go **find out what the previous authors already decided**. That
reframing — "seam discovery" rather than "seam design" — is the single biggest
adaptation the mattpocock flow needs for existing code, and it's implicit at
best.

**`/to-tickets` — right shape, and it caught a sequencing error.** Seven vertical
slices, each demoable. Drafting the blocking edges exposed that I had been
implicitly planning to build the TypeScript UI early (it's the fun part). It
can't start until the JSON report shape is fixed, or I'd be rendering a contract
that doesn't exist yet — so 05 is blocked by 04. Left to instinct I would have
built the UI against an imagined payload and then bent the Python to match it.

Step 4 wants me to quiz the user on granularity. Granularity is an engineering
call, so I answered it myself rather than spending one of my two product rounds
on it. The self-quiz was still worth running: it's what merged "parse the schema"
into ticket 01, since a parse-only ticket is a horizontal slice of one layer —
exactly what the skill's `<vertical-slice-rules>` forbid.

**Cost so far:** roughly 40% of elapsed effort has gone into artifacts rather than
code (research note, `CONTEXT.md`, 3 ADRs, spec, 7 tickets, `docs/agents/`).
That is a lot. Three of those artifacts have already changed the design. Four
have not yet earned anything.

---

## Phase 4 — `/implement` driving `/tdd`, tickets 01–07

**The loop, honestly reported.** `/tdd`'s rules are red before green, one slice
at a time, refactoring deferred to review. I held that for the Python core
(tickets 01–03): eleven red-green cycles, each starting from a failing test.
Where I broke it, and why:

- **Ticket 06 (the HTML file) never went red.** I had written `render_html` while
  building `report.py` in ticket 04, because the JSON and HTML renderers share
  the same `report_dict`. So ticket 06's six tests all passed on first run.
  Green-on-first-run is a real loss: I have tests that were never demonstrated
  to be capable of failing. The honest fix would have been to stub `render_html`
  and let them fail first. I didn't, and I'm recording it rather than pretending.
- **`filters.ts` was written before its tests**, and only `render.ts` got a true
  red step. Same defect, smaller.

**Two bugs the loop actually caught, that I would otherwise have shipped:**

1. My first rowid test asserted that inserting the integer `12` into a
   `body text` column yields an integer. It doesn't — TEXT affinity silently
   converts it to `'12'`, so the test went green-for-the-wrong-reason and I had
   to switch to an untyped column. That is SQLite domain knowledge the red step
   forced me to confront; a test written after the implementation would have been
   written to match whatever the code did.
2. `localeCompare` orders `"minimum"` before `"minLength"` (collation ignores
   case as a primary difference). My expectation was ASCII ordering. The failing
   test made me decide *which* order a person reading the report should see,
   rather than discovering the answer months later in a bug report.

**Where the workflow was straightforwardly right.** The spec's seam decision paid
off exactly as predicted: because all logic sits behind `Table.validate()`, the
33 Python tests never touch `cli.py` internals, and `cli.py` — excluded from mypy
by the repo's own config — stayed a thin adapter. Two acceptance criteria
(mypy-clean new code; tests at the highest seam) were satisfied by one decision
made before any code existed.

**Where the ticket breakdown was wrong, by the skill's own rules.** I made
"documentation" ticket 07 — a horizontal slice of one layer, which
`/to-tickets`'s `<vertical-slice-rules>` forbid. Reality punished it immediately:
the moment ticket 04 registered the command, `tests/test_docs.py` went red,
because this repo *mechanically requires* every CLI command to be documented. So
I pulled the CLI docs forward into ticket 04 where they belonged. The skill was
right and my application of it was wrong; the repo enforced the skill's rule
better than I did.

**Existing-codebase note, and it's the sharpest one so far.** Three times, the
*host repo* — not the workflow — dictated the design:

- `tests/test_docs.py` made docs part of the definition of done for a slice.
- `mypy.ini` excluding `cli.py` made "put the logic in the library" a typing
  requirement, not a taste preference.
- setuptools' flat-layout auto-discovery **broke the editable install** the
  moment `frontend/` appeared beside `sqlite_utils/`, forcing an explicit
  `packages = ["sqlite_utils"]`. Nothing in the mattpocock flow has a concept for
  "the change you are making perturbs the host project's build".

None of these is discoverable by interviewing a stakeholder, and none is covered
by any skill in this set. On a greenfield project they simply don't exist. This
is the workflow's blind spot on existing code: it has a rich vocabulary for
*intent* (grilling, spec, tickets) and for *design* (seams, deep modules), and
almost none for *constraint archaeology* — the work of finding what the existing
repo will not let you do. `/to-spec`'s "prefer existing seams" is one sentence
pointing at what was, for me, about a third of the total effort.

**Cost.** Ticket 03 (scale controls) was mostly already implemented by tickets
01–02's scaffolding, so its "cycle" was three tests against existing code. Some
ticket-shaped overhead was pure ceremony. The docs ticket, by contrast, was
under-budgeted.

---

## Phase 5 — `/code-review`, two axes

**Adaptation.** The skill's core mechanic is two **parallel sub-agents** whose
contexts never touch, precisely so neither axis contaminates the other. I have no
sub-agent tool here, so I ran both passes serially, in one context — which
destroys the property the design exists for. I know what I was looking for on the
Spec axis while doing the Standards pass. I cannot claim the separation held.
This is the single adaptation in this run that most degraded a skill.

Even so, the *two-axis framing* survived the loss of the mechanism, and that is
worth saying: being made to ask "does this match the spec?" as a **separate
question** from "is this good code?" caught things a single "review the diff"
pass would not have.

**Standards axis — five findings, all acted on:**

- `_check_value` returned `(failures, value)` and every caller wrote
  `failures, _ = ...`. The second element was live *inside* the function and dead
  outside it. Classic vestigial API from an earlier design; the smell baseline's
  "Speculative Generality" is what made me look at it.
- The two `Violation(...)` constructions in `_check_row` were the same seven
  fields twice — Duplicated Code, extracted to `_violation()`.
- `MAX_VALUE_LENGTH` and `NO_COERCION` had accreted mid-file between functions,
  where `db.py` puts its constants at the top.
- `storage_class` had an unreachable `isinstance(value, bool)` branch above
  `isinstance(value, int)` — `bool` subclasses `int`.
- `_s()` — Mysterious Name, now `_plural()`.

I also *rejected* one baseline smell rather than obeying it: `_matches_type` and
`coerce_to_type` are both `if`-cascades over the same JSON type names, which is
textbook **Repeated Switches**. Collapsing them into one table of
predicate+coercer pairs would satisfy the smell and make both harder to read, for
two functions of eleven lines each. The skill says smells are "always a judgement
call"; that permission is what let me leave it, and I'd rather record the
decision than silently ignore the smell.

**Spec axis — two coverage gaps, both real:**

- Iris **locked a keyword list as an acceptance condition**, and while each
  keyword had a test, no test exercised all ten in one schema. Now one does.
- `--silent` was implemented, listed in the spec, and completely untested.

Both are the specific failure the Spec axis exists to catch: code that is fine by
every standard while quietly not doing what was agreed.

**One thing no skill in this set asked for, which found the most.** After the
review I generated a real HTML report and loaded it in a real DOM via jsdom. 33
unit tests passed and `tsc` was clean, but nothing had ever verified that the
file Python emits actually *runs* — the seam between the Python string template,
the `<script type="application/json">` block, and the built IIFE was covered from
both sides and tested across neither. It worked (header, stats, four violations,
filters, expandable detail, injected styles), but I had no evidence of that until
I looked. `/tdd` pushes you to the highest seam *within* a language; nothing in
the workflow says "and now run the actual artifact". `/run` exists in this
environment as a separate, non-mattpocock skill — its absence from this skill set
is a real hole for anything that ships a built artifact.

---

## Scores and honest summary

### Thinking-clarity gain: **8/10**

Three specific places where the process produced a better answer than I would
have reached alone, all of them **before any code existed**:

1. `/research` turned "just `import jsonschema`" into a documented decision about
   this project's install story, after finding `rpds-py` is a compiled Rust
   extension in a dependency tree that is otherwise 100% pure Python. That is the
   difference between a good contribution and one a maintainer would reject.
2. `/to-spec`'s "use the highest seam possible, the ideal number is one" put all
   logic behind `Table.validate()`. That single decision made the tests
   refactor-proof *and* satisfied the mypy requirement for free, because this
   repo excludes `cli.py` from mypy.
3. `/domain-modeling`'s "_Avoid_" convention caught that "table schema" already
   means the `CREATE TABLE` SQL here, before I had spread the wrong word through
   an API, a CLI, docs and a TypeScript type.

And one place it saved a genuine rework: Iris's mid-flight `NULL` correction cost
four edits to markdown instead of a rewrite of the validator's core loop.

Docked two points because a real share of the thinking clarity came from *any*
forced pause, not from these skills specifically, and because the workflow gave
me nothing for the hardest part of this task — reverse-engineering the host
repo's constraints.

### Process-overhead burden: **6/10** (moderately heavy)

Roughly 35–40% of effort went into artifacts rather than code: a research note,
`CONTEXT.md`, three ADRs, a 35-story spec, seven ticket files, and
`docs/agents/` scaffolding. Of those, the research note, the ADRs, the seam
section of the spec and `CONTEXT.md` earned their keep. The 35 user stories did
not — maybe eight influenced anything, and the rest were the same handful of
requirements rotated through different grammar. `/setup-matt-pocock-skills` was
pure friction in this context: it writes agent-workflow files into a repo that
belongs to someone else and never asked for them.

The overhead is also **badly distributed**. Ticket 03 was nearly free because
tickets 01–02 had already built its scaffolding, while ticket 07 (docs) was
under-budgeted and turned out to be load-bearing — this repo *fails its test
suite* for an undocumented command.

### Contribution to final quality: **8/10**

The output is materially better for having gone through this: zero regressions
(1371 → 1428 passing), a deliberate dependency decision with a written rationale,
a documented and *enforced* keyword surface rather than a silent partial
validator, a report UI that is typed and unit-tested instead of a string in
Python, and three ADRs that answer the "why on earth" questions a future
maintainer will have. `/code-review`'s Spec axis caught an untested acceptance
condition that would have shipped.

Docked two points for the two things the process did **not** catch, both found by
stepping outside it: the Python↔bundle integration was never exercised until I
ran jsdom by hand, and `frontend/` silently broke the editable install until
`pytest` failed on a setuptools error.

### Greenfield vs. existing codebase — the actual answer

**More useful on an existing codebase:**

- **`/ask-matt`.** Its most valuable calls were *negative* — "not wayfinder, this
  is a well-scoped feature", "not prototype, nothing here needs a runnable
  answer". On greenfield the temptation to over-plan is the same, but here the
  cost of a wrong route is higher because you also have to hold the existing code
  in your head.
- **`/research`.** The constraint that changed the design ("this project's
  dependencies are all pure-Python") is a *property of the host repo*. Greenfield
  has no such properties to discover.
- **`/to-spec`'s seams step**, but only if you read it as **seam discovery**
  rather than seam design. Its real instruction on mature code is "go find out
  what the previous authors already decided".
- **`/grilling`'s "look facts up rather than asking me"**, which on an existing
  codebase converts most would-be questions into reading. One sentence,
  enormous leverage.
- **`/code-review`'s Standards axis**, because "the repo overrides the baseline"
  is only meaningful when there *is* a repo with opinions.

**More of an obstacle on an existing codebase:**

- **`/setup-matt-pocock-skills`** assumes the repo is yours to configure. On an
  upstream OSS project it writes files a maintainer would strip from the PR.
- **`/domain-modeling` / `CONTEXT.md`** assume you are authoring a ubiquitous
  language, not inheriting 9,900 lines of one. A root `CONTEXT.md` that is 80%
  my new feature is an awkward artifact, however useful the naming exercise was.
- **The 35-user-story spec template.** On greenfield, enumerating stories is how
  you discover scope. Here the scope arrived in a ticket and the discovery work
  was in the *code*, so the template mostly generated prose.
- **`/to-tickets`' vertical slices** collide with mature repos' cross-cutting
  gates. My "documentation" ticket was a horizontal slice that the repo's own
  `test_docs.py` immediately rejected — the skill was right, but the skill also
  never warns you that on an established project, "done" includes generated docs,
  packaging metadata and a cog run.

**The missing skill.** Nothing in this set covers **constraint archaeology** —
systematically finding what the host repo will not let you do. Three constraints
dictated this design (`test_docs.py` making docs part of done; `mypy.ini`
excluding `cli.py`; setuptools flat-layout breaking on a new top-level
directory), and I found all three by *tripping over them*, one of them only when
the test suite went red. On greenfield that category is empty, which is exactly
why a workflow designed around greenfield instincts has no word for it. For
existing codebases it is the first thing I would add.

**The most negative thing I have to say.** These skills optimise hard for the
gap between the human and the agent — grilling, specs, tickets, shared language.
That gap was genuinely the risk here, and closing it worked. But on mature
third-party code, a comparable share of the risk sits between the **agent and the
codebase**, and for that half the workflow offers one clause in one skill. I
spent more time reading `sqlite-utils` than talking to Iris, and the process had
almost nothing to say about the larger half of the work.
