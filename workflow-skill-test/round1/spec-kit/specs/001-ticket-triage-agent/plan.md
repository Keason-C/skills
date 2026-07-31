# Implementation Plan: TriageBot — Customer Support Ticket Triage Agent

**Branch**: `001-ticket-triage-agent` | **Date**: 2026-07-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-ticket-triage-agent/spec.md`

## Summary

TriageBot turns an inbound support ticket into an authoritative triage decision. A language model
reads the ticket and returns a `ClassificationProposal` that carries no authority; a layer of pure
deterministic guards then produces the `TriageResult`, overriding any proposed field it disagrees
with and recording every override. Processing is an explicit five-state machine that raises on
illegal transitions. The result's JSON Schema is generated from the pydantic models, a zod schema is
generated from that JSON Schema, and a TypeScript CLI validates and formats results without
re-implementing a single rule.

The technical approach (see [research.md](./research.md)) is built around three load-bearing
choices: models are strict and frozen so invariants are type-level rather than conventional; guards
are pure predicates with the retry orchestrated one layer up, so no guard imports a driver; and the
zod schema is generated rather than written, so the cross-language contract cannot silently drift.

## Technical Context

**Language/Version**: Python 3.11 (core) + TypeScript 5.x on Node 22 (downstream consumer)

**Primary Dependencies**: pydantic v2 (core, required); `anthropic` SDK (optional extra, never
imported by the core path); zod (TypeScript side). No LLM SDK is a runtime dependency of the core
package, per the constitution.

**Storage**: None. Tool data is read from checked-in JSON fixtures under
`src/triagebot/tools/fixtures/`. No database, queue, or persistence layer in v1.

**Testing**: pytest (Python), vitest (TypeScript), `tsc --noEmit` as a separate type gate. The whole
suite runs offline with no credentials.

**Target Platform**: Linux/macOS developer machines and CI. Library plus two local CLIs; no server.

**Project Type**: Library with CLI entry points, plus a small TypeScript consumer package.

**Performance Goals**: Not latency-driven. The binding target is SC-006 — the complete verification
suite finishes in under 60 seconds with no network access. Per-ticket cost is bounded structurally:
at most two classifier calls (SC-003a).

**Constraints**: Offline-testable (no network, no credentials in any test); deterministic
(re-running triage on the same ticket yields an identical result, SC-004); guards pure (no I/O, no
clock, no randomness); one-way layering `models → tools → drivers → guards → pipeline` with
`guards` forbidden from importing `drivers`.

**Scale/Scope**: One ticket at a time. ~10 Python modules, ~7 enums and models, 6 guard rules,
5 states, ~27 validation scenarios (V1–V27 in [quickstart.md](./quickstart.md)), 2 CLIs.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Initial check (before Phase 0) — PASS

| Principle | Gate | Verdict |
|-----------|------|---------|
| I. Deterministic Adjudication | Is every business decision made outside the LLM? | PASS — the driver's only output is `ClassificationProposal`; the pipeline never copies it to a result without passing through guards. |
| II. Validated Boundaries | Strict pydantic v2, no bare `Any`, generated cross-language schema? | PASS — `StrictModel` base (R1); schema generated, never hand-written (R3). |
| III. Explicit State Machine | Legal transitions declared as data, illegal ones raise? | PASS — `_LEGAL` mapping in `states.py` (R5). |
| IV. Offline Deterministic Tests | Suite runs with no network or credentials? | PASS — `MockDriver` everywhere; the Anthropic driver's testable surface is pure (R6). |
| V. Untrusted Input Containment | Injection detection deterministic and pre-driver? | PASS — pre-pass before any driver call; equivalence property is the test (R4). |

No violations. Phase 0 proceeded.

### Post-design re-check (after Phase 1) — PASS

| Principle | Re-check against the actual design | Verdict |
|-----------|-----------------------------------|---------|
| I | `derive_priority()` takes no proposal argument — it is *structurally* unable to adopt the classifier's priority, not merely disciplined about it. Every guard is a pure function of values. `GuardFinding` records the before/after pair, so the audit requirement is a data structure rather than a logging convention. | PASS |
| II | Every model is `extra="forbid" + strict + frozen`. `Decimal` for money removes float-comparison risk exactly at the SC-001 boundary. `TriageResult` carries six cross-field invariants as model validators, so even a hand-constructed result that bypasses the pipeline cannot violate the guards. This is stronger than the principle requires. | PASS |
| III | Five states, one frozen mapping, terminal states map to the empty set so re-entry is illegal. `state_path` on the result satisfies FR-024 at the cost of one tuple. | PASS |
| IV | No test constructs an SDK client or reads an env var. `build_messages` / `parse_response` are pure and directly asserted, shrinking the untested surface to a single SDK call. Boundary tests exist for both thresholds (V6–V10) as the principle demands. | PASS |
| V | Injection scan runs before the driver and feeds only the escalation verdict and the P0 rule — never category or action. The disjoint-vocabulary constraint between the injection signature table and the `MockDriver` keyword table (R4) is what makes V17's equivalence assertion meaningful rather than tautological. | PASS |

**Layering check**: `guards/` imports `models`, `settings`, `states` only. `pipeline.py` is the sole
module importing both `drivers` and `guards`. Verified as a design property here and asserted by an
automated import test in the task list.

No violations at either gate. Complexity Tracking is therefore empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-ticket-triage-agent/
├── plan.md              # This file
├── spec.md              # Feature specification (with Clarifications)
├── research.md          # Phase 0 output — R1..R8
├── data-model.md        # Phase 1 output — entities, invariants, state machine
├── quickstart.md        # Phase 1 output — setup + V1..V27 validation scenarios
├── contracts/
│   └── README.md        # Phase 1 output — library API, result JSON, CLI surfaces
├── checklists/
│   └── requirements.md  # Spec quality checklist (16/16)
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
src/triagebot/
├── __init__.py              # public surface: triage, Ticket, TriageResult, TriageSettings
├── settings.py              # TriageSettings — the only home for thresholds
├── models.py                # enums, Ticket, proposals, findings, TriageResult + invariants
├── states.py                # TriageState, _LEGAL, StateMachine, IllegalTransitionError
├── errors.py                # TriageError hierarchy
├── tools/
│   ├── __init__.py
│   ├── orders.py            # get_order_status -> OrderFound | OrderNotFound
│   ├── policies.py          # get_refund_policy -> PolicyFound | PolicyNotFound
│   └── fixtures/
│       ├── orders.json
│       └── refund_policies.json
├── drivers/
│   ├── __init__.py          # LLMDriver Protocol
│   ├── mock.py              # MockDriver — deterministic EN/ZH keyword rules
│   └── anthropic_driver.py  # AnthropicDriver — lazy import, pure prompt/parse helpers
├── guards/
│   ├── __init__.py          # apply_guards orchestration over pure rules
│   ├── injection.py         # scan_for_injection (pre-driver)
│   ├── language.py          # detect_language
│   ├── amount.py            # amount_guard
│   ├── confidence.py        # needs_retry, confidence_guard
│   ├── refund.py            # refund_policy_guard, terminal_action_guard
│   └── priority.py          # derive_priority
├── pipeline.py              # triage() — the only importer of drivers + guards
├── schema_export.py         # pydantic models -> schema/*.json
└── cli.py                   # python -m triagebot.cli

tests/                       # pytest — mirrors the module layout, one file per concern
├── conftest.py                  test_guard_amount.py
├── test_models_ticket.py        test_guard_confidence.py
├── test_models_result.py        test_guard_injection.py
├── test_states.py               test_guard_refund.py
├── test_tools.py                test_guard_priority.py
├── test_driver_mock.py          test_pipeline.py
├── test_driver_anthropic.py     test_layering.py
└── test_schema_export.py

ts/
├── package.json                 vitest.config.ts      tsconfig.json
├── scripts/generate-zod.mjs # JSON Schema -> zod (own generator, no codegen dep)
├── src/
│   ├── schema.generated.ts  # GENERATED — do not edit
│   ├── format.ts            # type-safe presentation
│   └── cli.ts               # validate then format
└── test/
    ├── schema.test.ts       # valid accepted / tampered rejected
    ├── generated.test.ts    # drift: regenerate and compare
    └── format.test.ts

schema/                      # GENERATED from pydantic
├── triage_result.schema.json
└── ticket.schema.json

examples/                    # sample tickets + a sample result for the TS CLI
pyproject.toml
README.md
```

**Structure Decision**: Single Python package `src/triagebot/` (src-layout, so tests import the
installed package rather than the working directory) plus a sibling `ts/` package for the downstream
consumer. This is the plan template's "single project" option extended with one consumer package —
not a web front/back split, because `ts/` shares no runtime with the core and communicates only
through result JSON files. The subpackage boundaries (`tools/`, `drivers/`, `guards/`) are the
enforcement points for the constitution's one-way layering: they exist so that "does `guards`
import `drivers`?" is answerable by an automated test rather than by reading code.

## Complexity Tracking

> Fill ONLY if Constitution Check has violations that must be justified.

No violations at either gate. This section is intentionally empty.

## Phase Status

| Phase | Output | Status |
|-------|--------|--------|
| Constitution check (initial) | gates above | PASS |
| Phase 0 — Research | [research.md](./research.md) | Complete, R1–R8, no unknowns remain |
| Phase 1 — Data model | [data-model.md](./data-model.md) | Complete |
| Phase 1 — Contracts | [contracts/README.md](./contracts/README.md) | Complete |
| Phase 1 — Quickstart | [quickstart.md](./quickstart.md) | Complete, V1–V27 |
| Constitution check (post-design) | gates above | PASS |
| Phase 2 — Tasks | `tasks.md` | Not started — `/speckit-tasks` |
