# Quickstart & Validation Guide: TriageBot

**Feature**: `001-ticket-triage-agent`

How to set the project up and prove, from the outside, that it meets the spec. Every command below
runs offline after the one-time dependency install.

---

## Prerequisites

- Python 3.11+ with `uv`
- Node 22+ with `npm`
- Network access **once**, for dependency installation only

---

## Setup

```bash
cd <repo root>

# Python
uv venv
uv pip install -e ".[dev]"

# TypeScript
cd ts && npm install && cd ..
```

---

## Run the suites

```bash
# Python — must pass with no network
.venv/bin/pytest -q

# TypeScript
cd ts && npm test && npm run typecheck
```

Expected: both suites green. The Python suite must complete in well under 60 seconds (SC-006).

To prove the offline requirement rather than assume it, run the Python suite with networking
disabled in whatever way the host supports (e.g. `unshare -rn` on Linux); it must still pass.

---

## End-to-end walkthrough

```bash
# 1. Triage a sample ticket
.venv/bin/python -m triagebot.cli --ticket examples/ticket_technical.json --pretty

# 2. Regenerate the JSON Schema from the pydantic models
.venv/bin/python -m triagebot.schema_export --out schema/

# 3. Regenerate the zod schema from that JSON Schema
cd ts && node scripts/generate-zod.mjs && cd ..

# 4. Validate and format a produced result
.venv/bin/python -m triagebot.cli --ticket examples/ticket_technical.json --out /tmp/result.json
cd ts && npm run cli -- /tmp/result.json
```

Steps 2 and 3 must produce no diff on a clean tree — a diff means the committed artifacts are stale
and the drift test will fail.

---

## Validation scenarios

Each maps to a spec requirement and is verifiable by running the named test. See
[`spec.md`](./spec.md) for the requirement text and [`data-model.md`](./data-model.md) for field
definitions.

| # | Scenario | Expected outcome | Requirement |
|---|----------|------------------|-------------|
| V1 | Technical ticket, no amount, clear wording | auto-resolved, not escalated, rationale present | FR-008, US1 |
| V2 | Blank / whitespace-only body | rejected at intake, field named, no driver call | FR-001, SC-005 |
| V3 | Body longer than 8000 chars | rejected, not truncated | FR-002 |
| V4 | Unknown field in ticket JSON | rejected | FR-004 |
| V5 | Negative amount | rejected | FR-003 |
| V6 | `amount = 1000.00` | **not** escalated on amount grounds | FR-012, SC-001 |
| V7 | `amount = 1000.01` | escalated, `AMOUNT_THRESHOLD` finding, priority ≥ P1 | FR-012, SC-001 |
| V8 | First proposal confidence `0.60` | no retry, `llm_calls == 1` | FR-014 |
| V9 | First proposal `0.55`, retry `0.80` | `retried`, `llm_calls == 2`, auto-resolved | FR-013 |
| V10 | Both proposals `0.55` | escalated, `LOW_CONFIDENCE` finding, `llm_calls == 2` | FR-014 |
| V11 | Unknown `order_id` | `not_found` in context, triage continues, visible in rationale | FR-006 |
| V12 | Refund inside window | action ∈ policy `permitted_actions` | FR-015, SC-003 |
| V13 | Refund, classifier suggests a non-permitted action | action replaced, `REFUND_POLICY` finding | FR-015 |
| V14 | Refund with no policy record | escalated, not guessed | FR-016 |
| V15 | Refund outside window | escalated, **no** automated denial | FR-016a |
| V16 | Recommended action is terminal | escalated regardless of everything else | FR-016b |
| V17 | Ticket + injection suffix vs. same ticket without | category, priority, action identical; only flag and escalation differ | FR-018, SC-002 |
| V18 | Injection detected | `injection_detected`, priority `P0`, escalated | FR-017, FR-019, FR-010c |
| V19 | Chinese-language ticket | classified normally, not forced to `OTHER` | FR-031 |
| V20 | Japanese-language ticket | `OTHER`, confidence ≤ 0.5, escalated via the confidence guard | FR-032, SC-003b |
| V21 | `NEW → CLASSIFIED` attempted directly | `IllegalTransitionError` | FR-023 |
| V22 | Same ticket triaged twice | identical results | FR-021, SC-004 |
| V23 | Two guards fire at once | both findings present, escalated once | FR-020 |
| V24 | Valid result JSON → TS CLI | accepted, formatted | FR-026, US6 |
| V25 | `confidence` edited to `1.5` | rejected, field named, nothing rendered | FR-027, SC-007 |
| V26 | Unknown category value / missing field | rejected | FR-027 |
| V27 | Committed `schema.generated.ts` vs. freshly generated | byte-identical | FR-025 |

---

## What "done" looks like

- `pytest` green offline
- `npm test` green, `npm run typecheck` clean
- Steps 2 and 3 produce no diff
- Every row in the table above has a corresponding named test
