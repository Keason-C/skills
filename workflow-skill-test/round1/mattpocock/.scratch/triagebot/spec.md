# Spec — TriageBot

**Status:** ready-for-agent

## Problem Statement

Inbound support Tickets arrive faster than the support team can read them, and the obvious fix —
hand them to an LLM — moves the problem rather than solving it. A model that classifies *and*
decides will, on some fraction of Tickets, confidently authorise a refund that policy forbids,
downgrade an angry customer with a four-figure dispute, or do whatever a customer wrote in the
body of the Ticket if that customer knows how to phrase it. The team cannot audit those failures
after the fact, because nothing recorded *why* a decision was made or what the model was allowed
to change.

What the team needs is triage they can defend line by line: every Ticket gets a Category, a
Priority, a Sentiment and a single recommended Action; every consequential decision traces to a
rule someone wrote down; and no Ticket can talk its way past the rules.

## Solution

TriageBot separates understanding from deciding.

A **Driver** (the LLM) reads a Ticket and returns a **Suggestion** — an opinion, in a type that is
deliberately *not* the output type. The Suggestion then runs through a fixed chain of pure
deterministic **Guards** that may overrule any field on it, and only the Guard chain can produce a
**Verdict**. There is no code path that turns a Suggestion into a Verdict without the Guards,
because there is no other constructor for one.

Each Ticket walks an explicit **Triage Stage** machine — `NEW → ENRICHED → CLASSIFIED →
AUTO_RESOLVED | ESCALATED` — where illegal transitions are rejected rather than corrected.
Facts the Guards need (order status, refund Policy Entries) are gathered once, at enrichment,
from local fixtures via functions whose arguments come only from validated Ticket fields.

A companion TypeScript CLI reads a Verdict JSON file, validates it with zod against a schema
exported from the pydantic models, and prints it — so a mismatch between what Python emits and
what a consumer expects is a test failure, not a production surprise.

## User Stories

1. As a support lead, I want every Ticket to come back with a Category, so that it lands in the right queue.
2. As a support lead, I want a Priority on every Ticket, so that my team works the urgent ones first.
3. As a support lead, I want the Priority decided by rules rather than by the model, so that the ladder means the same thing every day.
4. As a support lead, I want a Sentiment on every Ticket, so that I can get to angry customers sooner.
5. As a support lead, I want a single recommended Action from a fixed vocabulary, so that the output plugs into our routing without a human interpreting prose.
6. As a support lead, I want a rationale on every Verdict, so that I can explain a decision to a customer or an auditor.
7. As a finance controller, I want any Ticket disputing more than 1000.00 USD to reach a human, whatever the model concluded, so that large sums are never machine-decided.
8. As a finance controller, I want a dispute of exactly 1000.00 USD to triage normally, so that the threshold is an unambiguous line rather than a fuzzy one.
9. As a finance controller, I want no refund ever executed automatically at any amount, so that money only moves when a person says so.
10. As a support lead, I want a Ticket the model was unsure about to be retried with the facts we hold, so that we spend a second model call before we spend a person.
11. As a support lead, I want a Ticket that is still low-confidence after that retry to go to a human, so that guesses never reach customers.
12. As a refund specialist, I want the Action on a REFUND Ticket to come from the refund policy rather than from the model, so that the model cannot invent terms we do not offer.
13. As a security engineer, I want text in a Ticket that addresses the triage system to be flagged as an Injection Attempt, so that we can see attacks in our data.
14. As a security engineer, I want a flagged Ticket to be triaged exactly as if the injected text were ordinary complaint text, so that an attacker gains no control over the outcome.
15. As a security engineer, I want an Injection Attempt to be Priority P0, so that a security event is treated as one.
16. As a security engineer, I want tool arguments to come only from validated Ticket fields, so that injected text can never become a lookup we perform.
17. As a support agent, I want a Ticket quoting an order we cannot find to say so in the rationale, so that I know to ask the customer rather than doubt the system.
18. As a support agent, I want REFUND and BILLING Tickets with an unknown order to reach me, so that I can chase the missing evidence.
19. As an ops engineer, I want a malformed Ticket rejected at the boundary, so that bad data never reaches the Guards.
20. As an ops engineer, I want an empty or whitespace-only body rejected, so that we never triage a Ticket with nothing in it.
21. As an ops engineer, I want a body over 20 000 characters and a subject over 200 characters rejected rather than truncated, so that we never silently drop the sentence that mattered.
22. As an ops engineer, I want illegal Triage Stage transitions to raise, so that a partially-processed Ticket cannot be presented as a finished one.
23. As a Chinese-speaking customer, I want my Ticket understood in Chinese, so that I get the same triage quality as an English speaker.
24. As a support lead, I want a Ticket in a language we do not support to be Category OTHER with capped confidence, so that it reaches a human by the ordinary Guard path instead of a special case.
25. As a support lead, I want Category OTHER never auto-resolved, so that "we don't know" always reaches someone who does.
26. As a support agent, I want a Verdict JSON file rendered readably in my terminal, so that I can inspect one without reading raw JSON.
27. As a support agent, I want escalation and injection shown prominently in that output, so that I cannot miss them at a glance.
28. As an integrator, I want a machine-readable `--json` mode with a non-zero exit on invalid input, so that I can pipe TriageBot into a script safely.
29. As an integrator, I want the TypeScript types generated from the same schema the Python emits, so that the two sides cannot drift apart unnoticed.
30. As a developer, I want the whole test suite to run offline, so that CI never depends on a model provider being up.

## Implementation Decisions

**Two types, one direction.** `Suggestion` (Driver output) and `TriageResult` (the Verdict) are
distinct pydantic models. See ADR-0001. A Suggestion carries a suggested category, priority,
sentiment, action, confidence and rationale; every one of those may be overruled.

**The Guard chain is pure and ordered.** Eight Guards, in this order:
`injection → amount → refund-policy → unknown-order → refund-execution → confidence →
escalation-consistency → auto-resolution`, then Priority computation. Guards perform no I/O.
Escalation is monotonic — once set, no later Guard clears it.

Two of those were not in the first draft of this spec and are recorded here after the fact
(found by `/code-review`, Spec axis): **refund-execution** enforces "no automatic refund at any
amount" by escalating whenever the approved Action moves money, and **escalation-consistency**
enforces that an Action of `ESCALATE_TO_HUMAN` and the escalation flag never disagree. Both
implement behaviour the product owner asked for; the original six-Guard list simply did not
name them.

**Auto-resolution, as implemented.** The product owner's four conditions are: no Guard fired,
confidence ≥ threshold, Priority not the top tier, Category ≠ OTHER. Taken literally, "no Guard
fired" contradicts answer P8, which says an unknown order on a TECHNICAL Ticket should triage
normally — yet the unknown-order Guard *does* fire there, purely to annotate the rationale. The
code therefore reads condition one as "no Guard **overruled or escalated**": the eligibility
Guard checks escalation (which subsumes the confidence and Priority conditions, since both
escalate earlier in the chain) plus Category ≠ OTHER. A Guard that only annotates does not block
auto-resolution.

**Enrichment is eager; the first Driver pass is context-free.** See ADR-0002. Tool Context is
fetched at `NEW → ENRICHED`; the first Driver call omits it so that the low-confidence retry is a
genuinely better-informed call rather than the same call twice.

**Tool arguments never come from body text.** See ADR-0003. `get_order_status` takes
`Ticket.order_id`; `get_refund_policy` takes a `Category`. The Driver cannot request a tool call.

**Modules.** A Python package with: a models module (all pydantic types and enums); a stages
module (the Triage Stage machine, as a transition table with a typed rejection); a tools module
(fixture-backed lookups, `not-found` as a value not an exception); a drivers module (the
`LLMDriver` interface plus `MockDriver` and `AnthropicDriver` adapters); a guards module (pure
functions over Ticket + Suggestion + Tool Context); an injection module (deterministic detection
and redaction); a pipeline module exposing the single entry point that composes them; and a
schema-export module rendering the public models as JSON Schema for the TypeScript side.

**The entry point is one deep module.** `triage_ticket(ticket, driver, tools) -> TriageResult`.
Callers learn one function; behind it sit two Driver calls, eight Guards, a stage machine and the
tool layer. Dependencies are accepted, not constructed, so tests substitute adapters without
patching.

**Bilingual matching, table-driven.** Category keywords, sentiment markers and injection markers
are bilingual (English + Chinese) lookup tables in the Mock Driver and the injection detector
respectively. Text outside those two languages yields Category OTHER with confidence capped at
0.5 — below the 0.6 threshold, so the confidence Guard escalates it with no special case.

**Injection detection is deterministic**, a pattern table rather than a model call: a model asked
whether it is being attacked is itself attackable.

**Boundary validation.** All models are strict pydantic v2 (`extra="forbid"`, no bare `Any`).
`subject` 1–200 chars, `body` 1–20 000 chars, both rejected when whitespace-only. `amount` is
`Decimal` with `allow_inf_nan=False`, non-negative; float arithmetic is never used near the
threshold. `confidence` is a float in [0, 1].

**Thresholds are named constants in one place**, not literals sprinkled through the Guards:
amount 1000.00 USD (strictly greater escalates), confidence 0.6, one retry, subject 200, body
20 000.

**Anthropic adapter.** `AnthropicDriver` builds a request and parses a structured response.
It requires an explicit API key at construction and is never invoked by tests.

**Schema export.** A script writes JSON Schema for the public models into `schema/`. The
committed schema files are regenerated and compared inside the test suite, so drift fails
offline.

**TypeScript side.** A zod schema mirroring the Verdict, a parse function, a formatter, and a
thin CLI over them. The CLI is the shell; the parse and format functions hold the behaviour and
are what tests call.

## Testing Decisions

**What a good test is here.** Tests state a capability of the system in their name and assert on
values a support lead would recognise — "a dispute over the threshold escalates however confident
the model was". They never reach inside a Guard, never assert on call ordering, and never
recompute the expected value the way the code does; thresholds appear in tests as literals
(`1000.00`, `0.6`) so that a change to a constant fails a test rather than silently agreeing
with it.

**Seams under test** (highest-first, and these are the only ones):

1. `triage_ticket(...)` — the primary seam. Every Guard behaviour, the retry path, the stage
   walk and the injection defence are observed here, by feeding a Ticket and a Driver and
   inspecting the Verdict.
2. The `LLMDriver` interface — tests supply a scripted adapter returning canned Suggestions, so
   Guard behaviour can be exercised against any model opinion without depending on Mock Driver
   keyword tables. `MockDriver` itself is tested at this same seam as the shipped adapter.
3. The pydantic model constructors — the rejection tests for empty/oversized/malformed input.
4. The Triage Stage transition function — illegal-transition rejection.
5. The tools module — order not-found and policy lookup.
6. TypeScript: the parse function (valid Verdict accepted, tampered Verdict rejected) and the
   formatter (escalation and injection are visible in the output).

**Prior art.** None — greenfield. These seams set the precedent: behaviour through
`triage_ticket`, adapters substituted at the Driver interface, no monkeypatching anywhere.

**Coverage the suite must include** (from the acceptance criteria): empty body; over-long body;
over-long subject; injection text in several shapes and in both languages; amount exactly at and
just over the threshold; confidence just under and at the threshold plus the retry path; unknown
`order_id`; REFUND Action agreeing with the Policy Entry; illegal stage transitions; Chinese
input; unsupported-language input; and the Python↔zod round trip both ways.

## Out of Scope

- Any live model call in tests, or any network access at all in the test path.
- Automatic execution of refunds at any amount (explicitly ruled out by the product owner).
- Model-chosen tool calls / a general agent loop (ADR-0003).
- Persistence, queueing, a web API, authentication, or multi-tenancy.
- Languages beyond English and Chinese.
- Deterministic outage detection (see Further Notes).
- A Python-side interactive CLI beyond a small script that produces a Verdict JSON file for the
  TypeScript CLI to read.

## Further Notes

**Two tensions in the answers, followed rather than fixed.**

1. The product owner defines `P1_HIGH` as "blocks a core user action (e.g. payment failure)", but
   the binding Priority matrix puts a calm BILLING Ticket at `P3_LOW` — BILLING is not in the P2
   list and no floor applies. The explicit matrix is the more specific instruction, so the code
   follows the matrix. If the intent was that BILLING should floor at P2 or P1, that is a
   one-line change to the matrix and a test update.
2. `P0_URGENT` is defined as "service unavailable **or** a security event", but no deterministic
   outage signal was specified, so in v1 only the security half is reachable: `P0_URGENT` occurs
   exactly when an Injection Attempt is detected. Inventing an outage-keyword detector would be
   scope nobody asked for; flagging it is the honest move.

**Deliberate abuse surface, accepted by the product owner.** Because an Injection Attempt forces
Escalation, an attacker can guarantee themselves a human by including one line of injection text.
This was raised and accepted: safety before efficiency.
