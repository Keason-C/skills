"""Data models for TriageBot (tasks T007-T011).

Every model derives from :class:`StrictModel`, so across the whole system:

* unknown fields are rejected rather than ignored (FR-004);
* values are **not** coerced -- ``"1000"`` is not silently accepted where a number is
  required (research R1);
* instances are frozen, which is what makes "same input -> identical result" (SC-004) a
  property of the type rather than a convention.

Note the consequence of strict mode: constructing a model **from Python** requires exact
types (``Decimal("1000")``, ``Category.REFUND``). Constructing **from JSON** via
``model_validate_json`` accepts the natural JSON encodings. The CLI therefore parses JSON
rather than dict-splatting.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

# Single source of truth for the body limit. ``TriageSettings.max_body_length`` defaults to
# this same constant: a pydantic field constraint cannot read a settings instance at
# validation time, so without one shared constant the limit would exist twice (analyze F4).
MAX_BODY_LENGTH = 8000

ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
SubjectText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
BodyText = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=MAX_BODY_LENGTH)
]
Reason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]


class StrictModel(BaseModel):
    """Base for every model: no extra fields, no coercion, immutable."""

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        validate_assignment=True,
        use_enum_values=False,
    )


# --------------------------------------------------------------------------------------
# Enumerations
# --------------------------------------------------------------------------------------


class Category(str, Enum):
    """Triage category (FR-010)."""

    BILLING = "BILLING"
    REFUND = "REFUND"
    TECHNICAL = "TECHNICAL"
    ACCOUNT = "ACCOUNT"
    OTHER = "OTHER"


class Priority(str, Enum):
    """Priority band (FR-010a).

    P0 = service unavailable or security event; P1 = blocks a core user action;
    P2 = ordinary problem; P3 = advice or enquiry.
    """

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"

    @property
    def severity(self) -> int:
        """Lower is more severe, so "at least P1" is expressible as ``min``."""
        return int(self.value[1])


def most_severe(left: Priority, right: Priority) -> Priority:
    """Return whichever priority is more severe. Used to compose "at least Pn" rules."""
    return left if left.severity <= right.severity else right


class Sentiment(str, Enum):
    ANGRY = "ANGRY"
    FRUSTRATED = "FRUSTRATED"
    NEUTRAL = "NEUTRAL"
    POSITIVE = "POSITIVE"


class ActionKind(str, Enum):
    ANSWER_QUESTION = "ANSWER_QUESTION"
    REQUEST_INFO = "REQUEST_INFO"
    APPROVE_REFUND = "APPROVE_REFUND"
    DENY_REFUND = "DENY_REFUND"
    ISSUE_STORE_CREDIT = "ISSUE_STORE_CREDIT"
    RESET_CREDENTIALS = "RESET_CREDENTIALS"
    INVESTIGATE_TECHNICAL = "INVESTIGATE_TECHNICAL"
    ROUTE_TO_HUMAN = "ROUTE_TO_HUMAN"


#: Actions that move money or deny a customer request. The machine may *recommend* one but
#: never executes it: any ticket carrying one is escalated (FR-016b).
TERMINAL_ACTIONS: frozenset[ActionKind] = frozenset(
    {
        ActionKind.APPROVE_REFUND,
        ActionKind.DENY_REFUND,
        ActionKind.ISSUE_STORE_CREDIT,
    }
)


class GuardRule(str, Enum):
    """Identifies which deterministic rule produced a finding."""

    AMOUNT_THRESHOLD = "AMOUNT_THRESHOLD"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    REFUND_POLICY = "REFUND_POLICY"
    PROMPT_INJECTION = "PROMPT_INJECTION"
    TERMINAL_ACTION = "TERMINAL_ACTION"
    PRIORITY_DERIVATION = "PRIORITY_DERIVATION"
    UNSUPPORTED_LANGUAGE = "UNSUPPORTED_LANGUAGE"


class Language(str, Enum):
    EN = "EN"
    ZH = "ZH"
    OTHER = "OTHER"


class OrderState(str, Enum):
    PROCESSING = "PROCESSING"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class TriageState(str, Enum):
    """Explicit processing states (FR-022). Transitions live in ``states.py``."""

    NEW = "NEW"
    ENRICHED = "ENRICHED"
    CLASSIFIED = "CLASSIFIED"
    AUTO_RESOLVED = "AUTO_RESOLVED"
    ESCALATED = "ESCALATED"


TERMINAL_STATES: frozenset[TriageState] = frozenset(
    {TriageState.AUTO_RESOLVED, TriageState.ESCALATED}
)


# --------------------------------------------------------------------------------------
# Inbound ticket
# --------------------------------------------------------------------------------------


class Ticket(StrictModel):
    """An inbound customer request (FR-001..FR-004).

    Blank and whitespace-only values fail ``min_length`` *after* stripping, so FR-001 needs
    no custom validator. Over-length bodies are rejected rather than truncated (FR-002) so
    that nothing can be hidden past a truncation point.
    """

    id: ShortText
    customer_id: ShortText
    subject: SubjectText
    body: BodyText
    order_id: ShortText | None = None
    amount: Annotated[Decimal, Field(ge=0, decimal_places=2)] | None = None

    def with_text(self, *, subject: str, body: str) -> "Ticket":
        """Return a copy carrying different text, leaving this instance untouched.

        Used to hand the driver a neutralised copy while the original -- exactly what the
        customer wrote -- remains the audit record.
        """
        return Ticket(
            id=self.id,
            customer_id=self.customer_id,
            subject=subject,
            body=body,
            order_id=self.order_id,
            amount=self.amount,
        )


# --------------------------------------------------------------------------------------
# Tool results -- discriminated unions so "not found" is a value, not an absence (FR-006)
# --------------------------------------------------------------------------------------


class OrderFound(StrictModel):
    status: Literal["found"] = "found"
    order_id: ShortText
    state: OrderState
    placed_on: date
    delivered_on: date | None = None
    days_since_delivery: int | None = None


class OrderNotFound(StrictModel):
    status: Literal["not_found"] = "not_found"
    order_id: ShortText


OrderLookup = Annotated[OrderFound | OrderNotFound, Field(discriminator="status")]


class PolicyFound(StrictModel):
    status: Literal["found"] = "found"
    category: Category
    window_days: Annotated[int, Field(ge=0)]
    permitted_actions: Annotated[tuple[ActionKind, ...], Field(min_length=1)]
    requires_human_approval: bool
    summary: Reason


class PolicyNotFound(StrictModel):
    status: Literal["not_found"] = "not_found"
    category: Category


PolicyLookup = Annotated[PolicyFound | PolicyNotFound, Field(discriminator="status")]


# --------------------------------------------------------------------------------------
# Context gathered before classification
# --------------------------------------------------------------------------------------


class InjectionScan(StrictModel):
    """Outcome of the deterministic pre-driver injection scan (FR-017).

    ``signatures`` holds signature *names*, never the matched customer text, so the audit
    trail never re-embeds attacker-controlled content.
    """

    detected: bool
    signatures: tuple[str, ...] = ()


class ToolContext(StrictModel):
    """Everything gathered before the ticket is classified."""

    order: OrderLookup | None = None
    policy: PolicyLookup | None = None
    injection: InjectionScan
    language: Language


# --------------------------------------------------------------------------------------
# The LLM boundary
# --------------------------------------------------------------------------------------


class ClassificationProposal(StrictModel):
    """What a driver suggests. Carries no authority whatsoever (FR-009).

    This is the *entire* interface between the probabilistic and deterministic halves of
    the system; nothing else crosses.
    """

    category: Category
    priority: Priority
    sentiment: Sentiment
    confidence: Confidence
    suggested_action: ActionKind
    reasoning: Reason


class GuardFinding(StrictModel):
    """A record that one deterministic rule fired (FR-011, FR-020)."""

    rule: GuardRule
    field: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    proposed: str | None = None
    final: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]
    detail: Reason


# --------------------------------------------------------------------------------------
# The authoritative decision
# --------------------------------------------------------------------------------------


class TriageResult(StrictModel):
    """The final decision for a ticket.

    The cross-field validators below are what stop the guards being quietly bypassed: even
    a hand-constructed ``TriageResult`` that violates a rule fails validation.
    """

    ticket_id: ShortText
    category: Category
    priority: Priority
    sentiment: Sentiment
    confidence: Confidence
    recommended_action: ActionKind
    escalated_to_human: bool
    rationale: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)
    ]
    injection_detected: bool
    language: Language
    state: TriageState
    state_path: Annotated[tuple[TriageState, ...], Field(min_length=4)]
    guard_findings: tuple[GuardFinding, ...] = ()
    retried: bool
    llm_calls: Annotated[int, Field(ge=1, le=2)]

    @model_validator(mode="after")
    def _check_invariants(self) -> "TriageResult":
        # 1. escalation and terminal state agree
        expected_state = TriageState.ESCALATED if self.escalated_to_human else TriageState.AUTO_RESOLVED
        if self.state is not expected_state:
            raise ValueError(
                f"state {self.state.value} contradicts escalated_to_human={self.escalated_to_human}"
            )
        # 2. P0 always escalates (FR-010c)
        if self.priority is Priority.P0 and not self.escalated_to_human:
            raise ValueError("priority P0 requires escalated_to_human=True")
        # 3. terminal actions are never executed by the machine (FR-016b)
        if self.recommended_action in TERMINAL_ACTIONS and not self.escalated_to_human:
            raise ValueError(
                f"terminal action {self.recommended_action.value} requires escalation"
            )
        # 4. injection implies P0 and escalation (FR-017, FR-019, FR-010c)
        if self.injection_detected and (
            self.priority is not Priority.P0 or not self.escalated_to_human
        ):
            raise ValueError("injection_detected requires priority P0 and escalation")
        # 5. retry bookkeeping is consistent (SC-003a)
        if self.retried != (self.llm_calls == 2):
            raise ValueError(f"retried={self.retried} contradicts llm_calls={self.llm_calls}")
        # 6. the state path actually starts at NEW and ends where we claim (FR-024)
        if self.state_path[0] is not TriageState.NEW:
            raise ValueError("state_path must start at NEW")
        if self.state_path[-1] is not self.state:
            raise ValueError("state_path must end at the final state")
        return self
