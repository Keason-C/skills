<!--
SYNC IMPACT REPORT
==================
Version change: TEMPLATE (unversioned) → 1.0.0
Rationale: Initial ratification. All placeholder tokens replaced with concrete,
testable governance for the TriageBot project. MAJOR version 1 because this is
the first binding definition of the project's principles.

Modified principles (template placeholder → concrete):
  - [PRINCIPLE_1_NAME] → I. Deterministic Adjudication (NON-NEGOTIABLE)
  - [PRINCIPLE_2_NAME] → II. Validated Boundaries
  - [PRINCIPLE_3_NAME] → III. Explicit State Machine
  - [PRINCIPLE_4_NAME] → IV. Offline Deterministic Tests (NON-NEGOTIABLE)
  - [PRINCIPLE_5_NAME] → V. Untrusted Input Containment

Added sections:
  - Technology & Architecture Constraints (was [SECTION_2_NAME])
  - Development Workflow & Quality Gates (was [SECTION_3_NAME])

Removed sections: none

Follow-up TODOs: none — no placeholders deferred.
-->

# TriageBot Constitution

## Core Principles

### I. Deterministic Adjudication (NON-NEGOTIABLE)

The LLM understands; deterministic code decides. Every LLM output MUST enter the system
as a *suggestion* object that carries no authority. A separate, pure, side-effect-free
guard layer MUST convert suggestions into the final `TriageResult`, and MUST be able to
override any field the LLM proposed.

Rules:

- No business decision (escalation, recommended action, final category on a guarded path)
  may be taken directly from LLM output without passing through a guard function.
- Guard functions MUST be pure: same inputs → same outputs, no I/O, no clock, no randomness.
- Every guard override MUST be recorded in the result's rationale/audit trail so the
  difference between "what the model said" and "what the system did" is always inspectable.

Rationale: An LLM is a probabilistic component. Correctness claims can only be made about
the deterministic code around it, so all safety-relevant behaviour is placed there.

### II. Validated Boundaries

All data crossing a system boundary MUST be validated by a strict schema before use.

Rules:

- Python models MUST be pydantic v2 with `extra="forbid"` and `strict` semantics where the
  type allows it. Bare `Any` is forbidden in model fields and public function signatures.
- Invalid input MUST be rejected at the boundary with a validation error, never silently
  coerced, defaulted, or truncated into a "best guess".
- The Python↔TypeScript contract MUST be a generated JSON Schema, not a hand-copied
  interface. Hand-written duplicates of the schema are forbidden.

Rationale: Type systems are the cheapest available proof. Pushing validation to the edge
means the core never has to defend against malformed data.

### III. Explicit State Machine

Ticket processing MUST be modelled as an explicit, enumerated state machine:
`NEW → ENRICHED → CLASSIFIED → AUTO_RESOLVED | ESCALATED`.

Rules:

- The set of legal transitions MUST be declared as data, in one place.
- An illegal transition MUST raise; it MUST NOT be logged-and-ignored or silently repaired.
- State MUST be carried in a validated model, not inferred from the presence or absence of
  optional fields.

Rationale: Implicit pipelines drift. An explicit machine makes "can this happen?" a
question answerable by reading one table, and makes illegal paths testable.

### IV. Offline Deterministic Tests (NON-NEGOTIABLE)

The full test suite MUST pass with no network access and no credentials.

Rules:

- Tests MUST use the deterministic `MockDriver`. No test may construct a live API client
  or read an API key.
- Network-capable code paths (the Anthropic driver) MUST be structured so they can be
  imported and unit-tested for construction/prompt-shaping without performing I/O.
- Every guard rule MUST have at least one boundary test (at-threshold and just-over).

Rationale: A test suite that needs the internet is a test suite that fails for reasons
unrelated to the code. Determinism is what makes a red test informative.

### V. Untrusted Input Containment

Ticket content is data, never instruction.

Rules:

- Ticket `body`/`subject` MUST be passed to any model as clearly delimited, labelled
  untrusted content.
- Prompt-injection detection MUST be a deterministic pre-pass that runs before and
  independently of the driver, and its result MUST be attached to the ticket context.
- A ticket flagged as containing injection MUST produce the same routing outcome as the
  same ticket with the injection text removed, except for the injection flag itself and
  a forced human-escalation. Injected text MUST NOT be able to change category, priority,
  or recommended action.

Rationale: The threat model for a triage agent is a hostile customer. Containment must be
structural, not a matter of prompt wording.

## Technology & Architecture Constraints

- **Python core**: Python 3.11+, pydantic v2. The core package MUST have no runtime
  dependency on any LLM SDK; the Anthropic SDK is an optional extra imported lazily.
- **Layering**: `models` → `tools` → `drivers` → `guards` → `pipeline`. Dependencies point
  one way only. `guards` MUST NOT import `drivers`.
- **TypeScript side**: a thin consumer. It validates with zod against schemas generated
  from the pydantic models and formats output. It MUST NOT re-implement triage logic.
- **Fixtures**: tool data comes from local JSON fixtures checked into the repo. Tools MUST
  model the not-found case explicitly rather than raising or returning `None` bare.
- **No hidden config**: thresholds (amount, confidence) MUST live in one typed settings
  object, be injectable in tests, and never be read from module-level mutable globals.

## Development Workflow & Quality Gates

- Spec-driven order is binding: constitution → specify → clarify → plan → tasks →
  analyze → implement. Implementation code MUST NOT be written before `tasks.md` exists.
- Product-shaped ambiguity (thresholds' business meaning, priority tiers, language
  support, CLI surface) MUST be raised as a clarification question, not guessed.
  Technical-shaped ambiguity MUST be decided by the implementer and recorded in the
  README decision log.
- Definition of done for any task touching the core: `pytest` green offline, and for
  schema-affecting changes, regenerated JSON Schema plus green TypeScript tests.
- Each guard rule in the spec MUST map to at least one identifiable test. A guard without
  a boundary test is an incomplete guard.

## Governance

This constitution supersedes ad-hoc practice. Where a template, tool default, or
convenience conflicts with a principle here, the principle wins.

- **Amendments** require: a written diff of the affected principle, a version bump per the
  policy below, and an updated Sync Impact Report at the top of this file.
- **Versioning policy**: MAJOR for removing or redefining a principle in a
  backward-incompatible way; MINOR for adding a principle or materially expanding
  guidance; PATCH for clarifications and wording.
- **Compliance review**: the `speckit-analyze` gate MUST check plan and tasks against these
  principles before implementation begins. Any deviation MUST be recorded as an explicit,
  justified entry in the plan's Complexity Tracking section — an undocumented deviation is
  a defect.
- Runtime development guidance for agents lives in the generated plan and `README.md`;
  those documents are subordinate to this constitution.

**Version**: 1.0.0 | **Ratified**: 2026-07-31 | **Last Amended**: 2026-07-31
