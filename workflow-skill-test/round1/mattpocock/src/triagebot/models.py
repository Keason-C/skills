"""The types TriageBot speaks in.

Two of them carry the project's central distinction (ADR-0001):

- `Suggestion` — what a Driver returns. An opinion. Every field may be overruled.
- `TriageResult` — the Verdict. Only the Guard chain can produce one, and it can only exist in a
  terminal Triage Stage, so a half-adjudicated Ticket is not representable.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator

from triagebot.stages import TriageStage

# Boundary limits. Set by the product owner; see .scratch/triagebot/grilling-notes.md P12.
MAX_SUBJECT_CHARS = 200
MAX_BODY_CHARS = 20_000


class Category(str, Enum):
    """What kind of problem a Ticket is about."""

    BILLING = "BILLING"
    REFUND = "REFUND"
    TECHNICAL = "TECHNICAL"
    ACCOUNT = "ACCOUNT"
    OTHER = "OTHER"


class Priority(str, Enum):
    """How urgently a human should get to a Ticket. Always computed by Guards."""

    P0_URGENT = "P0_URGENT"
    """Service unavailable, or a security event."""
    P1_HIGH = "P1_HIGH"
    """A core user action is blocked."""
    P2_NORMAL = "P2_NORMAL"
    """An ordinary problem."""
    P3_LOW = "P3_LOW"
    """A question or a suggestion."""


class Sentiment(str, Enum):
    """How the customer sounds."""

    ANGRY = "ANGRY"
    FRUSTRATED = "FRUSTRATED"
    NEUTRAL = "NEUTRAL"
    SATISFIED = "SATISFIED"


class Action(str, Enum):
    """The single next step a Verdict recommends. A closed set — never free text."""

    AUTO_REFUND = "AUTO_REFUND"
    REQUEST_MORE_INFO = "REQUEST_MORE_INFO"
    ROUTE_TO_BILLING = "ROUTE_TO_BILLING"
    ROUTE_TO_TECH_SUPPORT = "ROUTE_TO_TECH_SUPPORT"
    ROUTE_TO_ACCOUNT_TEAM = "ROUTE_TO_ACCOUNT_TEAM"
    SEND_SELF_SERVE_GUIDE = "SEND_SELF_SERVE_GUIDE"
    ESCALATE_TO_HUMAN = "ESCALATE_TO_HUMAN"


MONEY_MOVING_ACTIONS = frozenset({Action.AUTO_REFUND})
"""Actions that move money. Never executed without a human (product decision P6)."""

Confidence = Annotated[float, Field(ge=0.0, le=1.0)]
Money = Annotated[
    Decimal,
    Field(ge=Decimal("0"), max_digits=12, decimal_places=2, allow_inf_nan=False),
]

STRICT_MODEL = ConfigDict(extra="forbid", frozen=True, validate_assignment=True)
"""Every model in this project is strict, frozen, and rejects unknown fields."""


def _reject_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


class Ticket(BaseModel):
    """One inbound customer-support request, as received. Immutable once accepted."""

    model_config = STRICT_MODEL

    id: str = Field(min_length=1, max_length=64)
    customer_id: str = Field(min_length=1, max_length=64)
    subject: str = Field(min_length=1, max_length=MAX_SUBJECT_CHARS)
    body: str = Field(min_length=1, max_length=MAX_BODY_CHARS)
    order_id: str | None = Field(default=None, min_length=1, max_length=64)
    amount: Money | None = None

    @field_validator("subject", "body")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        return _reject_blank(value)


class Suggestion(BaseModel):
    """A Driver's unapproved opinion about a Ticket. Never authoritative."""

    model_config = STRICT_MODEL

    category: Category
    priority: Priority
    """Advisory only. Guards compute the Priority that reaches the Verdict."""
    sentiment: Sentiment
    confidence: Confidence
    action: Action
    rationale: str = Field(min_length=1, max_length=2_000)


class TriageResult(BaseModel):
    """The Verdict: the rules-approved decision about a Ticket."""

    model_config = STRICT_MODEL

    ticket_id: str = Field(min_length=1, max_length=64)
    category: Category
    priority: Priority
    sentiment: Sentiment
    confidence: Confidence
    recommended_action: Action
    escalated_to_human: bool
    injection_detected: bool
    stage: TriageStage
    rationale: str = Field(min_length=1, max_length=4_000)
    guards_fired: tuple[str, ...] = ()

    @field_validator("stage")
    @classmethod
    def _must_be_terminal(cls, stage: TriageStage) -> TriageStage:
        if not stage.is_terminal:
            raise ValueError(
                f"a Verdict only exists in a terminal Triage Stage, got {stage.value}"
            )
        return stage
