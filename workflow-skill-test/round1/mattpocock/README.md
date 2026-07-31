# TriageBot

Customer-support ticket triage where **the LLM understands and deterministic rules decide**.

A model reads the ticket and returns a *Suggestion* — an opinion, in a type that is deliberately
not the output type. A fixed chain of pure rules then reviews that opinion and produces the
*Verdict*. There is no code path from a Suggestion to a Verdict that skips the rules, because
there is no other constructor for one.

```
                    ┌──────────────────────────────────────────────────┐
   Ticket ─────────▶│  triage_ticket(ticket, driver, tools)            │────▶ Verdict
   (strict pydantic)│  the one function callers learn                  │      (TriageResult)
                    └──────────────────────────────────────────────────┘
                          │            │              │
              NEW → ENRICHED      CLASSIFIED    → AUTO_RESOLVED | ESCALATED
                          │            │              │
                    ┌─────▼─────┐ ┌────▼─────┐  ┌─────▼──────────────────────┐
                    │  Tools    │ │  Driver  │  │  Guard chain (pure, no I/O)│
                    │ fixtures  │ │ seam     │  │ injection                  │
                    │ order +   │ │ Mock /   │  │ amount                     │
                    │ policy    │ │ Anthropic│  │ refund-policy              │
                    └───────────┘ └──────────┘  │ unknown-order              │
                                                │ refund-execution           │
                          injection scan        │ confidence                 │
                          redacts the text      │ escalation-consistency     │
                          the Driver sees       │ auto-resolution            │
                                                └────────────────────────────┘
                                                        │
                                          Priority computed by rules only
```

The Verdict is exported as JSON Schema and consumed by a small TypeScript CLI that validates it
with zod before printing it — so a change on the Python side that breaks a consumer fails a test
rather than a person.

## Layers

| Layer | Module | Responsibility |
| --- | --- | --- |
| Boundary | `models.py` | Strict pydantic types. Malformed input is rejected here, not later. |
| Lifecycle | `stages.py` | `NEW → ENRICHED → CLASSIFIED → AUTO_RESOLVED \| ESCALATED` as a transition table; illegal moves raise. |
| Facts | `tools.py` | `get_order_status`, `get_refund_policy` over local JSON. `not-found` is a value. |
| Understanding | `drivers/` | The `LLMDriver` seam: `MockDriver` (deterministic, bilingual) and `AnthropicDriver` (Claude). |
| Defence | `injection.py` | Deterministic marker table; redacts instruction-like text *before* any Driver sees it. |
| Decision | `guards.py` | Eight pure Guards plus the Priority matrix. The only place a Verdict is constructed. |
| Composition | `pipeline.py` | `triage_ticket()` — the seam every behavioural test crosses. |
| Contract | `schema_export.py`, `ts/` | JSON Schema out of pydantic; zod validation and display in. |

### Why the LLM only suggests

Three concrete consequences, each enforced rather than documented:

1. **`Suggestion` and `TriageResult` are different types** (ADR-0001). You cannot hand a caller a
   Verdict without having run the Guards.
2. **The Driver never chooses a tool call** (ADR-0003). `get_order_status` receives
   `Ticket.order_id`; `get_refund_policy` receives a `Category` enum. No string from the ticket
   body ever becomes a lookup argument, which removes the injection path rather than filtering it.
3. **Injected text is redacted before classification**, so the Driver forms its opinion without
   ever seeing the attack. A flagged ticket and its clean twin produce the same Category,
   Sentiment and Action — only the security flag, the escalation and the Priority differ.

## Running it

```bash
uv venv && uv pip install "pydantic>=2.7" "pytest>=8" anthropic
.venv/bin/python -m pytest                 # 127 tests, offline
.venv/bin/python scripts/export_schema.py  # regenerate schema/
.venv/bin/python scripts/triage_demo.py    # triage examples/tickets.json → examples/verdicts/

cd ts && npm install
npx vitest run                             # 20 tests, offline
npx tsc --noEmit                           # typecheck
npx tsx src/bin.ts ../examples/verdicts/TCK-2004.json
npx tsx src/bin.ts ../examples/verdicts/TCK-2001.json --json
```

Every test in both suites runs with no network. The Anthropic adapter is covered by tests that
stub the SDK client at the boundary; no test constructs a real client or issues a request.

## Decisions

### Product decisions (made by the product owner, recorded in `.scratch/triagebot/grilling-notes.md`)

| # | Decision |
| --- | --- |
| P1 | Four Priority tiers. `P0_URGENT` = outage or security event; `P1_HIGH` = a core action is blocked; `P2_NORMAL` = ordinary; `P3_LOW` = a question. |
| P2 | Amount threshold **1000.00 USD**; strictly greater escalates, exactly 1000.00 does not. |
| P3 | Confidence threshold **0.6**; exactly one retry, then a human. |
| P4 | Seven-value closed Action enum; never free text. |
| P5 | An Injection Attempt is flagged **and** escalated; injected text must never reach a tool argument. The "one injection line buys a human" abuse surface is accepted. |
| P6 | **No automatic refund at any amount.** `AUTO_REFUND` may be recommended; executing it is always a person's job. |
| P7 | Sentiment is `ANGRY / FRUSTRATED / NEUTRAL / SATISFIED`. |
| P8 | An unknown cited order forbids every refund Action and escalates REFUND and BILLING tickets. |
| P9 | v1 is bilingual (English + Chinese); other languages become `OTHER` with confidence capped at 0.5. |
| P10 | CLI: positional path, readable by default, `--json` for machines, non-zero exit on invalid input. |
| P11 | Rules own Priority. Injection → P0; any escalation (including the amount Guard) floors at P1; angry REFUND/BILLING → P1; TECHNICAL/ACCOUNT → P2; everything else → P3. |
| P12 | Empty/whitespace body rejected; body > 20 000 chars rejected; subject > 200 chars rejected. Never silently truncated. |

### Engineering decisions (mine)

| # | Decision |
| --- | --- |
| E1 | `Suggestion` and `TriageResult` are separate types; only the Guard chain constructs a Verdict. (ADR-0001) |
| E2 | Guards are pure — no Guard performs I/O — which is what keeps the retry path explicit instead of hidden. |
| E3 | Guard order is fixed and total; escalation is monotonic. Order matters because the policy Guard rewrites the Action that later Guards read. |
| E4 | Enrichment is eager, but the **first** Driver pass is deliberately context-free, so the low-confidence retry is a genuinely better-informed call rather than the same call twice. (ADR-0002) |
| E5 | Exactly one retry — two Driver calls maximum per Ticket. |
| E6 | The stage machine is a transition table with a typed rejection; there is no setter that writes a stage. |
| E7 | Tool arguments come only from validated Ticket fields; the Driver cannot request a tool call. (ADR-0003) |
| E8 | `AnthropicDriver` asks Claude for a *structured* Suggestion, so an invented Category fails validation at the boundary. It requires an API key at construction, never at request time. |
| E9 | Schema export is a script; a test regenerates and compares, so drift fails offline. |
| E10 | Money is `Decimal`, single currency. No float arithmetic anywhere near the threshold. |
| E11 | Injection detection is a deterministic pattern table — a model asked whether it is being attacked is itself attackable. |
| E12 | Redaction is line-based. A single-line body containing an injection marker is redacted **whole**; that ticket then reads as uncategorisable and reaches a human. Blunt, and deliberately biased toward safety. |
| E13 | Language detection is script-based (CJK vs Latin). Japanese and Korean text containing kanji will be treated as Chinese — an accepted v1 limitation, not an oversight. |
| E14 | Tests observe behaviour at `triage_ticket()`; the only test double is a scripted adapter at the `LLMDriver` seam. Nothing internal is ever monkeypatched. |

### Two tensions in the requirements, surfaced rather than silently resolved

1. `P1_HIGH` is defined as "a core user action is blocked (e.g. payment failure)", but the binding
   Priority matrix sends a calm BILLING ticket to `P3_LOW`. The explicit matrix is the more
   specific instruction, so the code follows it. Changing this is one line and one test.
2. `P0_URGENT` covers "service unavailable **or** a security event", but no deterministic outage
   signal was specified — so in v1 `P0_URGENT` is reachable only via an Injection Attempt.
   Inventing an outage detector would be scope nobody asked for.

## Project artifacts

- `CONTEXT.md` — the glossary. Ticket, Verdict, Suggestion, Guard, Escalation and the rest, each
  with the words to avoid.
- `docs/adr/` — three decisions worth explaining to a future reader.
- `.scratch/triagebot/spec.md` — the spec, plus the twelve tickets under `issues/`.
- `REFLECTION.md` — a process log of running this workflow, written step by step.
