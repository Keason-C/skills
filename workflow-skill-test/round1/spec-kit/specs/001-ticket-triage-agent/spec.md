# Feature Specification: TriageBot — Customer Support Ticket Triage Agent

**Feature Branch**: `001-ticket-triage-agent`

**Created**: 2026-07-31

**Status**: Draft

**Input**: User description: "TriageBot customer support ticket triage agent where an LLM proposes and deterministic rules decide. Tickets are classified into a category, priority, and sentiment, given a recommended action, and either auto-resolved or escalated to a human. Deterministic guards (amount threshold, confidence threshold with retry, refund-policy consistency, prompt-injection containment) always outrank the model's suggestion. Processing is an explicit state machine. Results are consumed downstream by a schema-validated formatter."

## Clarifications

### Session 2026-07-31

- Q: What priority levels does the support organisation use, and what rule assigns them? → A: Four
  levels P0/P1/P2/P3. Priority is **derived deterministically**, never adopted from the classifier.
  Matrix (most severe wins): injection detected → P0; amount guard fired → at least P1; any
  escalation → at least P1; sentiment is angry AND category is refund or billing → at least P1;
  category is technical or account otherwise → P2; everything else → P3. Level semantics: P0 =
  service unavailable or security event; P1 = blocks a core user action; P2 = ordinary problem;
  P3 = advice or enquiry. A P0 ticket is always escalated, regardless of confidence.
- Q: What is the escalation amount threshold, and in what currency? → A: 1000 USD, single currency.
  Strictly greater than 1000 escalates; exactly 1000 does not.
- Q: What is the confidence threshold? → A: 0.60, not tiered by category. Below 0.60 triggers one
  retry with tool context attached (maximum 2 classifier calls per ticket); still below 0.60 after
  the retry escalates to a human.
- Q: Must non-English tickets be handled in v1, and if so which languages? → A: English and Chinese.
  Keyword tables and injection-signature tables cover both. Tickets in any other language are
  categorised as "other" and their confidence is capped at 0.5, so the confidence guard routes them
  to a human naturally.
- Q: For a refund ticket outside the refund window, should the system auto-deny or escalate? → A:
  Escalate — a human says "no". General principle: the machine never *executes* a terminal
  money-moving or denial action. Such actions may be emitted as a recommendation, but any ticket
  whose recommended action is terminal-money or denial is escalated. Actions inside the window and
  consistent with policy are automated as normal.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Routine ticket is triaged without human effort (Priority: P1)

A support operations lead receives a steady stream of inbound tickets. For an ordinary
ticket — a clear question, modest or no money at stake — they want the system to read it,
decide which queue it belongs in, how urgent it is, what the customer's mood is, and what
the agent should do next, and then mark it resolved-without-human-review so nobody has to
look at it.

**Why this priority**: This is the entire economic case for the product. Without it there is
no time saved. Every other story is a safety rail around this one.

**Independent Test**: Submit a well-formed ticket with no money at stake and unambiguous
wording; confirm a complete triage result comes back with a category, priority, sentiment,
confidence, recommended action, and a not-escalated verdict, plus a written rationale.

**Acceptance Scenarios**:

1. **Given** a ticket describing a login failure with no order and no amount, **When** it is
   triaged, **Then** the result is categorised as a technical issue, is not escalated to a
   human, and carries a rationale explaining the decision.
2. **Given** a ticket that mentions an order number, **When** it is triaged, **Then** the
   order's status has been looked up and is reflected in the recommended action and rationale.
3. **Given** any triaged ticket, **When** the result is inspected, **Then** it records the
   final processing state and the full sequence of states the ticket passed through.

---

### User Story 2 - Financially significant tickets always reach a human (Priority: P2)

A finance-risk owner must guarantee that no ticket above a monetary threshold is closed by
an automated system, regardless of how confident or how routine the ticket appears.

**Why this priority**: This is the highest-consequence failure mode. An auto-resolved
high-value refund is a direct, unrecoverable loss and an audit finding.

**Independent Test**: Submit two otherwise identical tickets, one at the threshold and one a
cent above it; confirm the above-threshold one is escalated even when the underlying
classification is confident and benign.

**Acceptance Scenarios**:

1. **Given** a ticket whose disputed amount is above the escalation threshold, **When** it is
   triaged, **Then** it is escalated to a human even if the classification is high-confidence
   and the category is a routine one.
2. **Given** a ticket whose amount is exactly equal to the threshold, **When** it is triaged,
   **Then** it is NOT escalated on amount grounds alone.
3. **Given** an escalation caused by the amount rule, **When** the rationale is read, **Then**
   it names the amount rule as the cause and shows what the automated classification had
   proposed before the override.

---

### User Story 3 - Uncertain classifications get a second look, then a human (Priority: P3)

A support operations lead does not want confidently-wrong routing, and equally does not want
every borderline ticket dumped on a person. When the system is unsure, it should try once
more with the extra context it has gathered, and only hand off to a human if it is still unsure.

**Why this priority**: Uncertain-but-auto-resolved tickets are the main source of misrouting
and customer re-contacts. The retry keeps the human queue from filling with cases that one
extra look would have settled.

**Independent Test**: Submit a ticket that the classifier reports low confidence on; confirm
exactly one retry occurs with enriched context, and confirm the two outcomes (retry succeeds
→ auto-resolved; retry still uncertain → escalated) both happen as specified.

**Acceptance Scenarios**:

1. **Given** an initial classification below the confidence threshold, **When** triage
   proceeds, **Then** the classification is attempted a second time with the gathered order
   and policy context attached.
2. **Given** the second attempt is at or above the confidence threshold, **When** triage
   completes, **Then** the ticket is auto-resolved and the result records that a retry occurred.
3. **Given** the second attempt is still below the confidence threshold, **When** triage
   completes, **Then** the ticket is escalated to a human and the rationale names low
   confidence as the cause.
4. **Given** a classification exactly at the confidence threshold, **When** triage proceeds,
   **Then** no retry is performed.

---

### User Story 4 - Refund answers always match published policy (Priority: P4)

A policy owner must be able to state that the system has never told a customer something
about refunds that is not in the published policy.

**Why this priority**: An invented refund promise is a commitment the business must either
honour at a loss or retract at reputational cost.

**Independent Test**: Submit a refund ticket; confirm the recommended action was taken from
the policy record for that category, and confirm that a classification proposing an action
that contradicts the policy is corrected rather than passed through.

**Acceptance Scenarios**:

1. **Given** a ticket classified as a refund request, **When** triage completes, **Then** the
   refund policy for that category has been retrieved and the recommended action is one of the
   actions that policy permits.
2. **Given** a classification proposing a refund action that the policy does not permit,
   **When** triage completes, **Then** the recommended action is replaced with a
   policy-permitted one and the rationale records the correction.
3. **Given** a refund ticket for which no policy record exists, **When** triage completes,
   **Then** the ticket is escalated to a human rather than answered from the model's own
   knowledge.

---

### User Story 5 - Hostile ticket content cannot steer the system (Priority: P5)

A security owner must be able to demonstrate that text written by a customer is treated as
evidence about the customer's problem and never as an instruction to the system.

**Why this priority**: The adversary here is a self-selecting subset of customers who will
find this quickly. A single successful "approve my refund" injection is both a loss and a
publishable exploit.

**Independent Test**: Take a benign ticket, append injection text instructing the system to
approve a refund and skip review, and confirm the routing outcome is identical to the benign
ticket except for the injection flag and the forced human review.

**Acceptance Scenarios**:

1. **Given** a ticket whose body contains text attempting to override the system's
   instructions, **When** it is triaged, **Then** the result is flagged as containing a
   suspected injection and is escalated to a human.
2. **Given** two tickets that are identical except that one has injection text appended,
   **When** both are triaged, **Then** their category, priority, and recommended action are
   the same — the injected text changes only the injection flag and the escalation verdict.
3. **Given** injection text that names a category or demands an action, **When** triage
   completes, **Then** that named category and demanded action have not been adopted.

---

### User Story 6 - Downstream consumers can trust the result format (Priority: P6)

An engineer on a neighbouring team wants to display triage results in their own tool without
re-deriving the rules, and wants a loud failure — not a silent misread — if the shape of a
result ever changes or a file is tampered with.

**Why this priority**: It protects the integrity of everything upstream, but delivers no
triage value on its own, so it comes last.

**Independent Test**: Feed a genuine triage result file to the downstream formatter and see a
readable summary; feed a hand-edited file with an out-of-range confidence or an unknown
category and see it rejected with a precise reason.

**Acceptance Scenarios**:

1. **Given** a result file produced by the triage system, **When** the downstream formatter
   reads it, **Then** it is accepted and rendered as a human-readable summary.
2. **Given** a result file whose confidence has been edited to a value outside the permitted
   range, **When** the formatter reads it, **Then** it is rejected with a message identifying
   the offending field.
3. **Given** a result file with an unrecognised category value or a missing required field,
   **When** the formatter reads it, **Then** it is rejected rather than partially displayed.

---

### Edge Cases

- **Empty body**: A ticket whose body is blank or whitespace-only is rejected at intake as
  invalid input; it never reaches classification.
- **Oversized body**: A ticket body beyond the accepted length limit is rejected at intake
  rather than silently truncated, so no one can hide instructions past a truncation point.
- **Unknown order reference**: A ticket citing an order that does not exist produces an
  explicit "not found" context entry; triage continues and the missing order is visible in
  the rationale.
- **Amount exactly at threshold**: 1000 USD is treated as below the escalation line (the rule
  triggers on *exceeding*, not on reaching); 1000.01 USD escalates.
- **Confidence exactly at threshold**: 0.60 is treated as sufficient; no retry.
- **Refund category with no matching policy record**: Escalated rather than guessed.
- **Refund outside the policy window**: Escalated to a human, never auto-denied.
- **Terminal recommended action** (moves money or denies a request): Emitted as a recommendation
  but always escalated; the machine never executes it.
- **Ticket in a third language** (neither English nor Chinese): Categorised as "other" with
  confidence capped at 0.5, which puts it below the confidence threshold even after the retry, so
  it reaches a human through the ordinary confidence guard rather than a bespoke rule.
- **Two guards firing at once** (e.g. high amount *and* injection): The result is escalated
  once, and the rationale lists every rule that fired, not just the first.
- **Illegal state transition** (e.g. attempting to classify a ticket whose context was never
  gathered): Rejected outright as a programming error, never silently repaired.
- **Zero or absent amount**: Absence of an amount is not treated as zero risk by itself; other
  guards still apply.

## Requirements *(mandatory)*

### Functional Requirements

**Intake and validation**

- **FR-001**: System MUST reject a ticket at intake if any required field is missing, blank, or
  whitespace-only, and MUST report which field failed.
- **FR-002**: System MUST reject a ticket whose body exceeds the maximum accepted length rather
  than truncating it.
- **FR-003**: System MUST reject a ticket carrying a negative disputed amount.
- **FR-004**: System MUST reject unrecognised fields on incoming tickets rather than ignoring them.

**Context gathering**

- **FR-005**: System MUST look up the status of a referenced order before classifying, when the
  ticket cites an order.
- **FR-006**: System MUST represent "order not found" as an explicit, inspectable outcome rather
  than an error or an empty value.
- **FR-007**: System MUST retrieve the applicable refund policy record before finalising any
  ticket classified as a refund request.

**Classification**

- **FR-008**: System MUST produce, for every accepted ticket, a category, a priority, a
  sentiment, a confidence value between 0 and 1 inclusive, a recommended action, a human-review
  verdict, and a written rationale.
- **FR-009**: System MUST treat the classifier's output as a proposal with no authority; every
  field it proposes MUST be replaceable by the deterministic rules below.
- **FR-010**: Category MUST be one of: billing, refund, technical, account, other.
- **FR-010a**: Priority MUST be one of four levels — P0 (service unavailable or security event),
  P1 (blocks a core user action), P2 (ordinary problem), P3 (advice or enquiry).
- **FR-010b**: Priority MUST be derived deterministically and MUST NOT be adopted from the
  classifier's proposal. The derivation applies the following, most severe winning: injection
  detected → P0; amount guard fired → at least P1; the ticket is escalated for any reason → at
  least P1; sentiment is angry and category is refund or billing → at least P1; category is
  technical or account and nothing above applied → P2; otherwise → P3.
- **FR-010c**: A ticket at P0 MUST be escalated to a human regardless of confidence.
- **FR-010d**: When the derived priority differs from the classifier's proposed priority, the
  system MUST record the override, retaining the proposed value for audit.
- **FR-011**: System MUST record which rules overrode the proposal, so that the proposed and
  final values can be compared after the fact.

**Deterministic guards (each outranks the classifier)**

- **FR-012**: System MUST escalate to a human any ticket whose disputed amount is strictly greater
  than 1000 USD, irrespective of the proposal. An amount of exactly 1000 USD MUST NOT escalate on
  amount grounds. All amounts are in a single currency (USD); no conversion is performed.
- **FR-013**: System MUST re-attempt classification exactly once, with gathered context
  attached, when the first proposal's confidence is below 0.60. No ticket may cause more than two
  classifier calls. The threshold is global and MUST NOT be tiered by category.
- **FR-014**: System MUST escalate to a human when the confidence is still below 0.60 after the
  single retry. A confidence of exactly 0.60 is sufficient and MUST NOT trigger a retry.
- **FR-015**: System MUST constrain the recommended action for refund tickets to actions
  permitted by the retrieved policy record, replacing any non-permitted proposal.
- **FR-016**: System MUST escalate to a human any refund ticket for which no policy record can
  be retrieved.
- **FR-016a**: System MUST escalate to a human any refund ticket falling outside the refund window
  defined by the policy record, rather than issuing an automated denial.
- **FR-016b**: System MUST NOT auto-resolve a ticket whose recommended action is terminal — that
  is, an action that moves money or denies a customer request. Such an action may be emitted as a
  recommendation, but the ticket MUST be escalated for a human to execute it.
- **FR-017**: System MUST detect ticket text that attempts to override system behaviour and
  MUST flag the result accordingly.
- **FR-018**: System MUST guarantee that flagged text cannot alter the category, priority, or
  recommended action relative to the same ticket without that text.
- **FR-019**: System MUST escalate to a human every ticket flagged as containing such text.
- **FR-020**: System MUST apply all guards and report every one that fired, not stop at the first.
- **FR-021**: Guard outcomes MUST be reproducible: the same ticket and the same gathered context
  MUST always produce the same final result.

**Process model**

- **FR-022**: System MUST model ticket handling as the explicit states: received, context
  gathered, classified, and one of auto-resolved or escalated.
- **FR-023**: System MUST reject any attempt to move a ticket between states in an order the
  model does not permit.
- **FR-024**: System MUST record on the result the state path the ticket actually took.

**Downstream consumption**

- **FR-025**: System MUST publish a machine-readable description of the result format, generated
  from the same definitions the triage system itself validates against, not maintained separately.
- **FR-026**: The downstream formatter MUST validate a result file against that published
  description before displaying any part of it.
- **FR-027**: The downstream formatter MUST reject and explain — never partially render — a
  result that fails validation.
- **FR-028**: The downstream formatter MUST NOT re-implement or second-guess any triage rule.

**Operation**

- **FR-029**: The system MUST be operable and fully testable without network access, using a
  deterministic stand-in for the language model.
- **FR-030**: A real language-model-backed classifier MUST be provided as an alternative that can
  be selected without changing any rule logic.
- **FR-031**: System MUST handle tickets written in English and in Chinese; keyword tables and
  injection-signature tables MUST cover both languages.
- **FR-032**: System MUST categorise a ticket written in any language other than English or
  Chinese as "other" and MUST cap its confidence at 0.5, so that the confidence guard routes it to
  a human without a special-case rule.

### Key Entities

- **Ticket**: An inbound customer request. Identity, the customer it belongs to, a subject line,
  a body, and optionally a referenced order and a disputed monetary amount.
- **Order Status**: What the business knows about a referenced order — whether it exists, its
  fulfilment state, and dates relevant to refund eligibility.
- **Refund Policy Record**: For a given category, the window in which refunds are allowed, the
  set of actions an agent may recommend, and whether a human must approve.
- **Classification Proposal**: What the language model suggests — category, priority, sentiment,
  confidence, and a suggested action. Carries no authority.
- **Guard Finding**: A record that one deterministic rule fired: which rule, what it changed,
  and why.
- **Triage Result**: The final, authoritative decision for a ticket — category, priority,
  sentiment, confidence, recommended action, human-review verdict, rationale, injection flag,
  final state, state path, and the guard findings.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100% of tickets whose disputed amount is strictly above 1000 USD are routed to a
  human, and 0% of tickets at exactly 1000 USD are escalated on amount grounds — measured across
  the full boundary test set (999.99 / 1000.00 / 1000.01).
- **SC-001a**: 100% of triage results carry a priority that matches the derivation matrix applied
  to their own category, sentiment, and fired guards — verified independently of what the
  classifier proposed, including at least one case where the two disagree.
- **SC-001b**: 0% of tickets whose recommended action is terminal (money-moving or denial) are
  auto-resolved.
- **SC-002**: 0% of tickets containing override-attempt text produce a different category,
  priority, or recommended action than the same ticket with that text removed.
- **SC-003**: 100% of refund recommendations correspond to an action permitted by the retrieved
  policy record; zero recommendations originate from the model alone. 100% of out-of-window refund
  tickets reach a human; 0% receive an automated denial.
- **SC-003a**: No ticket causes more than two classifier calls, measured by call count across the
  whole test set including the retry path.
- **SC-003b**: 100% of tickets written in a language other than English or Chinese are categorised
  "other", carry confidence at or below 0.5, and reach a human.
- **SC-004**: Re-running triage on the same ticket produces a byte-identical result 100% of the
  time.
- **SC-005**: Every rejected input is rejected before classification is attempted, and names the
  offending field — verified for blank body, oversized body, negative amount, and unknown field.
- **SC-006**: The complete verification suite runs to completion with no network access and no
  credentials in under 60 seconds.
- **SC-007**: A tampered result file is rejected by the downstream formatter 100% of the time,
  with the offending field named, for every field of the result format.
- **SC-008**: Every deterministic rule has at least one at-boundary and one just-past-boundary
  check; no rule ships without both.

## Assumptions

- Tickets arrive one at a time; batch and streaming intake are out of scope for v1.
- Order and policy data are read from a fixed local dataset; live integration with order
  management and policy systems is out of scope for v1.
- The escalation threshold (1000 USD) and the confidence threshold (0.60) are single global
  values, not per-category or per-customer-tier values, in v1 — confirmed in clarification.
- All monetary amounts are already denominated in USD when they reach the system; no currency
  field and no conversion exist in v1.
- Language detection is script-based and coarse: it distinguishes "contains Chinese characters",
  "plausibly English", and "neither". It is not a general-purpose language identifier, and that is
  sufficient because the "neither" branch is routed to a human by the confidence guard.
- Exactly one retry is the right amount of retrying; unbounded or configurable retry counts are
  out of scope for v1.
- There is no persistence layer, queue, or web service in v1 — the system is a library plus
  local entry points.
- Human reviewers are a single undifferentiated pool; routing to specific teams or skill groups
  is out of scope for v1.
- "Confidence" is a value the classifier reports about itself; the system does not attempt to
  calibrate or second-guess it beyond the threshold rule.
- The downstream formatter runs on the same machine against files on disk; no transport or
  authentication concerns apply in v1.
