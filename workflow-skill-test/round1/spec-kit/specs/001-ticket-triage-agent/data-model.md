# Phase 1 Data Model: TriageBot

**Feature**: `001-ticket-triage-agent` | **Date**: 2026-07-31

All models derive from `StrictModel` (`extra="forbid"`, `strict=True`, `frozen=True`,
`validate_assignment=True`) per research R1. "Required" means no default.

---

## Enumerations

| Enum | Members | Notes |
|------|---------|-------|
| `Category` | `BILLING`, `REFUND`, `TECHNICAL`, `ACCOUNT`, `OTHER` | FR-010 |
| `Priority` | `P0`, `P1`, `P2`, `P3` | FR-010a. Ordered; `P0` most severe |
| `Sentiment` | `ANGRY`, `FRUSTRATED`, `NEUTRAL`, `POSITIVE` | |
| `TriageState` | `NEW`, `ENRICHED`, `CLASSIFIED`, `AUTO_RESOLVED`, `ESCALATED` | FR-022 |
| `ActionKind` | `ANSWER_QUESTION`, `REQUEST_INFO`, `APPROVE_REFUND`, `DENY_REFUND`, `ISSUE_STORE_CREDIT`, `RESET_CREDENTIALS`, `INVESTIGATE_TECHNICAL`, `ROUTE_TO_HUMAN` | |
| `GuardRule` | `AMOUNT_THRESHOLD`, `LOW_CONFIDENCE`, `REFUND_POLICY`, `PROMPT_INJECTION`, `TERMINAL_ACTION`, `PRIORITY_DERIVATION` | one per deterministic rule |
| `Language` | `EN`, `ZH`, `OTHER` | FR-031, FR-032 |

**Terminal actions** (FR-016b): `APPROVE_REFUND`, `DENY_REFUND`, `ISSUE_STORE_CREDIT`. Declared as
a frozenset constant `TERMINAL_ACTIONS`, not as a scattered condition.

`Priority` carries a `severity` ordering (`P0` = 0 … `P3` = 3) so the derivation matrix can express
"at least P1" as a `min()` over severity rather than a chain of comparisons.

---

## `Ticket` — inbound request (FR-001..FR-004)

| Field | Type | Required | Validation |
|-------|------|----------|-----------|
| `id` | `str` | yes | non-blank after strip, ≤64 chars |
| `customer_id` | `str` | yes | non-blank after strip, ≤64 chars |
| `subject` | `str` | yes | non-blank after strip, ≤200 chars |
| `body` | `str` | yes | non-blank after strip, ≤`MAX_BODY_LENGTH` (8000) |
| `order_id` | `str \| None` | no (`None`) | if present: non-blank, ≤64 chars |
| `amount` | `Decimal \| None` | no (`None`) | if present: `>= 0`, ≤2 decimal places |

Blank/whitespace-only values fail `min_length=1` **after** `strip_whitespace=True`, satisfying
FR-001 without a custom validator. Over-length fails `max_length` rather than truncating (FR-002).
Unknown fields fail via `extra="forbid"` (FR-004). Negative amount fails `ge=0` (FR-003).

---

## Tool result models (FR-005..FR-007, R7)

### `OrderFound` / `OrderNotFound` — discriminated on `status`

`OrderFound`: `status: Literal["found"]`, `order_id: str`, `state: OrderState`
(`PROCESSING|SHIPPED|DELIVERED|CANCELLED`), `placed_on: date`, `delivered_on: date | None`,
`days_since_delivery: int | None`.

`OrderNotFound`: `status: Literal["not_found"]`, `order_id: str`.

`OrderLookup = Annotated[OrderFound | OrderNotFound, Field(discriminator="status")]`

### `PolicyFound` / `PolicyNotFound` — discriminated on `status`

`PolicyFound`: `status: Literal["found"]`, `category: Category`, `window_days: int` (`ge=0`),
`permitted_actions: tuple[ActionKind, ...]` (non-empty), `requires_human_approval: bool`,
`summary: str`.

`PolicyNotFound`: `status: Literal["not_found"]`, `category: Category`.

`PolicyLookup = Annotated[PolicyFound | PolicyNotFound, Field(discriminator="status")]`

---

## `ToolContext` — everything gathered before classification

| Field | Type | Notes |
|-------|------|-------|
| `order` | `OrderLookup \| None` | `None` only when the ticket cites no order |
| `policy` | `PolicyLookup \| None` | populated when a refund policy was consulted |
| `injection` | `InjectionScan` | always present; computed before any driver call |
| `language` | `Language` | coarse script detection (R4 / FR-031) |

### `InjectionScan`

`detected: bool`, `signatures: tuple[str, ...]` — signature *names*, not the matched customer text,
so the audit trail never re-embeds attacker-controlled content.

---

## `ClassificationProposal` — what the driver returns; carries no authority (FR-009)

| Field | Type | Validation |
|-------|------|-----------|
| `category` | `Category` | required |
| `priority` | `Priority` | required — **recorded for audit, never adopted** (FR-010b) |
| `sentiment` | `Sentiment` | required |
| `confidence` | `float` | `ge=0.0, le=1.0` |
| `suggested_action` | `ActionKind` | required |
| `reasoning` | `str` | non-blank, ≤1000 chars |

This model is the *entire* interface between the probabilistic and deterministic halves of the
system. Nothing else crosses.

---

## `GuardFinding` — one deterministic rule fired (FR-011, FR-020)

| Field | Type | Notes |
|-------|------|-------|
| `rule` | `GuardRule` | which rule |
| `field` | `str` | which result field it changed, or `"escalated_to_human"` |
| `proposed` | `str \| None` | the classifier's value, stringified, for audit |
| `final` | `str` | the value the rule imposed |
| `detail` | `str` | human-readable justification |

Findings are accumulated in a list; every rule that fires appends one (FR-020 — no short-circuit).

---

## `TriageResult` — the authoritative decision

| Field | Type | Validation / Notes |
|-------|------|-------------------|
| `ticket_id` | `str` | echoes `Ticket.id` |
| `category` | `Category` | final |
| `priority` | `Priority` | derived, never adopted (FR-010b) |
| `sentiment` | `Sentiment` | final |
| `confidence` | `float` | `ge=0.0, le=1.0` — the last proposal's value |
| `recommended_action` | `ActionKind` | final, policy-constrained for refunds |
| `escalated_to_human` | `bool` | final verdict |
| `rationale` | `str` | non-blank |
| `injection_detected` | `bool` | FR-017 |
| `language` | `Language` | |
| `state` | `TriageState` | `AUTO_RESOLVED` or `ESCALATED` |
| `state_path` | `tuple[TriageState, ...]` | FR-024, min length 4 |
| `guard_findings` | `tuple[GuardFinding, ...]` | may be empty |
| `retried` | `bool` | whether the confidence retry ran (FR-013) |
| `llm_calls` | `int` | `ge=1, le=2` — makes SC-003a checkable from the result alone |

**Cross-field invariants** (model validators, so they hold for any construction path):

1. `escalated_to_human is True` ⟺ `state is ESCALATED`.
2. `priority is P0` ⟹ `escalated_to_human is True` (FR-010c).
3. `recommended_action in TERMINAL_ACTIONS` ⟹ `escalated_to_human is True` (FR-016b).
4. `injection_detected is True` ⟹ `priority is P0` and `escalated_to_human is True`.
5. `retried is True` ⟺ `llm_calls == 2`.
6. `state_path[0] is NEW` and `state_path[-1] is state`.

These are the reason the guards cannot be quietly bypassed: even a hand-constructed `TriageResult`
that violates a rule fails validation.

---

## State machine (FR-022..FR-024, R5)

```text
NEW ──────► ENRICHED ──────► CLASSIFIED ──┬──► AUTO_RESOLVED   (terminal)
                                          └──► ESCALATED       (terminal)
```

Legal transitions, declared once as data:

| From | Allowed to |
|------|-----------|
| `NEW` | `ENRICHED` |
| `ENRICHED` | `CLASSIFIED` |
| `CLASSIFIED` | `AUTO_RESOLVED`, `ESCALATED` |
| `AUTO_RESOLVED` | — (none) |
| `ESCALATED` | — (none) |

Anything else raises `IllegalTransitionError`. Notably illegal: `NEW → CLASSIFIED` (skipping
enrichment), `CLASSIFIED → ENRICHED` (backwards), `ESCALATED → AUTO_RESOLVED` (re-deciding),
`AUTO_RESOLVED → AUTO_RESOLVED` (re-entry).

---

## `TriageSettings` — the only place thresholds live

| Field | Type | Default | Requirement |
|-------|------|---------|-------------|
| `amount_escalation_threshold` | `Decimal` | `1000` | FR-012 |
| `confidence_threshold` | `float` | `0.60` | FR-013/014 |
| `max_llm_calls` | `int` | `2` | FR-013 |
| `unsupported_language_confidence_cap` | `float` | `0.5` | FR-032 |
| `max_body_length` | `int` | `8000` | FR-002 |

Injectable into the pipeline; never read from a module-level mutable global (constitution,
Technology & Architecture Constraints).

---

## Priority derivation (FR-010b) — pure function of already-final values

```text
derive_priority(category, sentiment, injection_detected, amount_guard_fired, escalated) -> Priority

  if injection_detected                                    -> P0
  severity = P3
  if category in {TECHNICAL, ACCOUNT}                      -> severity = min(severity, P2)
  if sentiment is ANGRY and category in {REFUND, BILLING}   -> severity = min(severity, P1)
  if amount_guard_fired                                    -> severity = min(severity, P1)
  if escalated                                             -> severity = min(severity, P1)
  return severity
```

`min` is over severity rank, so "at least P1" composes without ordering bugs. The function takes no
proposal argument — it is structurally incapable of adopting the classifier's priority.

---

## Module ownership

| Module | Owns |
|--------|------|
| `models.py` | every model and enum above, `TERMINAL_ACTIONS` |
| `states.py` | `TriageState`, `_LEGAL`, `StateMachine`, `IllegalTransitionError` |
| `settings.py` | `TriageSettings` |
| `tools/` | fixtures, `get_order_status`, `get_refund_policy` |
| `drivers/` | `LLMDriver` protocol, `MockDriver`, `AnthropicDriver` |
| `guards/` | pure guard functions incl. `derive_priority` |
| `pipeline.py` | orchestration, the only importer of both `drivers` and `guards` |
