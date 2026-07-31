# Grilling notes — TriageBot

Working notes from the `/grill-with-docs` session. Two piles: decisions I settled myself as the
engineer (technical), and decisions that belong to the product owner (asked, answers recorded
under "Answers from the product owner").

## Technical decisions — settled by the engineer

**T1. Verdict is a distinct type from Suggestion.** See ADR-0001. `Suggestion` is what a Driver
returns; `TriageResult` (the Verdict) can only be produced by the Guard chain.

**T2. The Guard chain is pure.** No Guard performs I/O. Everything a Guard needs is either on the
Ticket, on the Suggestion, or in the Tool Context gathered at enrichment. This is what makes the
Guards trivially testable and the retry path explicit rather than hidden inside a Guard.

**T3. Guard order is fixed and total.** `injection → amount → refund-policy → confidence`, then a
final consistency pass. Escalation is monotonic: once any Guard escalates, no later Guard can
clear the flag. Ordering matters because the refund-policy Guard may rewrite the Action, and the
consistency pass must see the rewritten value.

**T4. Enrichment is eager; the first Driver pass is context-free.** See ADR-0002.

**T5. Retry count is exactly one.** Two Driver calls maximum per Ticket. More retries buy
diminishing information (the second retry would be identical to the first retry) and make the
cost per Ticket unbounded.

**T6. The state machine is enforced by a transition table, not by convention.** `TriageStage`
advance is a function that rejects illegal transitions with a typed error; there is no setter
that lets a caller write a stage directly.

**T7. Tool fixtures are local JSON, loaded through a small tool module.** `get_order_status` and
`get_refund_policy` are ordinary functions over fixture data — no network, ever, in the test
path. `not-found` is a *value*, not an exception: unknown orders are an expected business case.

**T8. `AnthropicDriver` is written but never exercised by tests.** It builds a request and parses
a structured response; construction requires an API key, so tests only assert that it cannot be
built without one and never issue a call.

**T9. Schema export is a script, not a build step.** `scripts/export_schema.py` writes pydantic
JSON Schema into `schema/`, and the committed `schema/*.json` is checked by a test that
regenerates and compares, so drift fails the suite offline.

**T10. Python package layout.** `src/triagebot/` with `models.py`, `stages.py`, `tools.py`,
`drivers/`, `guards.py`, `pipeline.py`. One deep module at the top (`triage_ticket`) is the
seam every behavioural test crosses.

**T11. Money is `Decimal`, single currency.** No float arithmetic on `amount`; comparisons at the
threshold boundary must be exact.

**T12. Injection detection is a deterministic pattern list**, not a model call — a model asked to
detect injection is itself injectable.

## Questions for the product owner

Asked in round 1, each with the recommendation the code will use if the answer is "as proposed":

1. Priority ladder — `P0_URGENT / P1_HIGH / P2_NORMAL / P3_LOW`.
2. Amount threshold — 500.00, single currency (USD), strictly-greater-than escalates.
3. Confidence threshold — 0.70, exactly one retry.
4. Action vocabulary — a closed enum of 7 Actions.
5. Injection Attempt policy — flag *and* force Escalation.
6. Auto-resolution eligibility — allowed only when no Guard fired, confidence ≥ threshold, and
   the Action is a non-money-moving one.
7. Sentiment values — `ANGRY / FRUSTRATED / NEUTRAL / POSITIVE`.
8. Unknown / mismatched `order_id` — blocks any refund Action, escalates only for REFUND.
9. Language scope — English-only detection in v1, but non-English input must not crash.
10. TS CLI shape — `triagebot-view <path.json>`, human-readable table by default.
11. Priority matrix — rules own priority; the LLM's suggested priority is advisory only.
12. Body length limits — reject empty; reject over 20 000 characters at the boundary.

Answers land below.

## Answers from the product owner

Received in round 1. Six of the twelve overruled my recommendation — recorded verbatim in intent,
with the resulting binding rule.

**P1. Priority ladder.** Four tiers. Semantics are the product's, the naming suffix is mine:
`P0_URGENT` = service unavailable **or a security event**; `P1_HIGH` = blocks a core user action
(e.g. payment failure); `P2_NORMAL` = ordinary problem; `P3_LOW` = question or suggestion.

**P2. Amount threshold — OVERRULED.** **1000.00 USD**, not 500. Strictly greater escalates;
exactly 1000.00 does not.

**P3. Confidence threshold — OVERRULED.** **0.6**, not 0.70. One retry; still below 0.6 after the
retry → forced Escalation.

**P4. Action vocabulary.** The 7-value closed enum as proposed, nothing added or removed, no free
text.

**P5. Injection Attempt policy.** Flag + forced Escalation, as proposed. **Added hard
requirement: injected text must never reach any tool-call argument.** The abuse surface (one
injection line buys a human) is accepted.

**P6. Auto-resolution eligibility — TIGHTENED.** All four must hold: no Guard fired; confidence
≥ 0.6; Priority ∈ {P1, P2, P3} (P0 is always human); Category ≠ OTHER. **No automatic refund at
any amount** — `AUTO_REFUND` may be emitted as the recommended Action, but executing it is always
a human's job, so it always escalates.

**P7. Sentiment — OVERRULED.** Fourth value is **SATISFIED**, not POSITIVE:
`ANGRY / FRUSTRATED / NEUTRAL / SATISFIED`.

**P8. Unknown `order_id` — WIDENED.** The not-found fact goes into the rationale; every refund
Action is forbidden; Escalation for Category ∈ {REFUND, **BILLING**} (BILLING added by the
product owner — evidence is missing either way). Other categories triage normally.

**P9. Language scope — OVERRULED.** v1 ships **English *and* Chinese**: keyword table and
injection-marker table both bilingual. Any other language → Category `OTHER` with confidence
capped at **0.5**, which falls below the 0.6 threshold and routes to a human by the ordinary
Guard path — no special case.

**P10. TS CLI.** As proposed: positional path argument, human-readable output with prominent
markers by default, `--json` for normalised output, non-zero exit on validation failure.

**P11. Priority matrix — REVISED.** Rules own Priority; the Driver's suggested priority is
advisory and always overridable. Binding matrix, first match wins after floors:
Injection Attempt → `P0_URGENT` (security event); **amount Guard fired → at least `P1_HIGH`**
(explicitly *not* P0 — a large sum is not an outage); any Escalation → at least `P1_HIGH`;
`ANGRY` and Category ∈ {REFUND, BILLING} → `P1_HIGH`; Category ∈ {TECHNICAL, ACCOUNT} →
`P2_NORMAL`; everything else → `P3_LOW`.

**P12. Body limits — EXTENDED.** Empty/whitespace-only body rejected at the boundary; body over
20 000 characters rejected, never silently truncated. **Added: subject capped at 200 characters,
over-length rejected the same way.**

### Tension surfaced, not silently resolved

P1 defines `P1_HIGH` as "blocks a core user action (e.g. payment failure)", but the binding
matrix in P11 sends an ordinary, calm BILLING Ticket to `P3_LOW` (BILLING is not in the P2 list,
and no floor applies). The explicit matrix is the more specific instruction, so the code follows
the matrix. Flagged in the spec's Further Notes rather than quietly "fixed".

Likewise, the "service unavailable" half of `P0_URGENT` is unreachable by rules in v1 — no
deterministic outage signal was specified, and inventing one would be scope the product owner did
not ask for. In v1, `P0_URGENT` is reached only by an Injection Attempt. Also flagged, not fixed.
