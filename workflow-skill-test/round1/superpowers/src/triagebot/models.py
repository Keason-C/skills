"""Domain models.

Design rule: the LLM's output is called a *suggestion* and can never become a
``TriageResult`` field without passing through deterministic logic. The strict
validation here is the outer boundary — garbage never gets into the system, and
a self-contradictory conclusion can never get out of it.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from triagebot.states import TERMINAL_STATES, TriageState

MAX_BODY_LENGTH = 20_000
MAX_SUBJECT_LENGTH = 200
ORDER_ID_PATTERN = r"^[A-Za-z0-9-]{1,32}$"


class Category(str, Enum):
    BILLING = "BILLING"
    REFUND = "REFUND"
    TECHNICAL = "TECHNICAL"
    ACCOUNT = "ACCOUNT"
    OTHER = "OTHER"


class Priority(str, Enum):
    """P0 = outage or security event. P1 = blocks a core user operation.
    P2 = ordinary issue. P3 = enquiry or suggestion."""

    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class Sentiment(str, Enum):
    ANGRY = "ANGRY"
    FRUSTRATED = "FRUSTRATED"
    NEUTRAL = "NEUTRAL"
    SATISFIED = "SATISFIED"


class Language(str, Enum):
    EN = "en"
    ZH = "zh"
    OTHER = "other"


class GuardCode(str, Enum):
    """Every deterministic rule that fired while triaging a ticket."""

    AMOUNT_THRESHOLD = "AMOUNT_THRESHOLD"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    PROMPT_INJECTION = "PROMPT_INJECTION"
    P0_ALWAYS_HUMAN = "P0_ALWAYS_HUMAN"
    MISSING_ORDER_EVIDENCE = "MISSING_ORDER_EVIDENCE"
    UNSUPPORTED_LANGUAGE = "UNSUPPORTED_LANGUAGE"
    REFUND_POLICY_OVERRIDE = "REFUND_POLICY_OVERRIDE"
    REFUND_POLICY_MISSING = "REFUND_POLICY_MISSING"


ShortId = Annotated[str, StringConstraints(min_length=1, max_length=64)]
OrderId = Annotated[str, StringConstraints(pattern=ORDER_ID_PATTERN)]
Money = Annotated[Decimal, Field(ge=0, max_digits=12, decimal_places=2)]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]


class StrictModel(BaseModel):
    """Base for every model: no unknown fields, no mutation after construction."""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _reject_blank(value: str) -> str:
    if not value.strip():
        raise ValueError("must not be blank")
    return value


class Ticket(StrictModel):
    """An incoming support ticket, validated at the system boundary."""

    id: ShortId
    customer_id: ShortId
    subject: Annotated[str, StringConstraints(min_length=1, max_length=MAX_SUBJECT_LENGTH)]
    body: Annotated[str, StringConstraints(min_length=1, max_length=MAX_BODY_LENGTH)]
    order_id: OrderId | None = None
    amount: Money | None = None

    _no_blanks = field_validator("id", "customer_id", "subject", "body")(_reject_blank)


class TicketView(StrictModel):
    """The redacted, read-only projection an LLM driver is allowed to see.

    Drivers never receive a ``Ticket``: the raw body cannot reach them by type.
    """

    ticket_id: ShortId
    subject: str
    redacted_body: str
    language: Language
    amount: Money | None = None
    order_id: OrderId | None = None


class LLMSuggestion(StrictModel):
    """What a driver proposes. Never authoritative — always subject to guards."""

    category: Category
    sentiment: Sentiment
    confidence: Confidence
    suggested_priority: Priority
    suggested_action: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    rationale: Annotated[str, StringConstraints(min_length=1, max_length=2000)]

    _no_blanks = field_validator("suggested_action", "rationale")(_reject_blank)


class TriageResult(StrictModel):
    """The final, deterministic conclusion for a ticket."""

    ticket_id: ShortId
    category: Category
    priority: Priority
    sentiment: Sentiment
    confidence: Confidence
    recommended_action: Annotated[str, StringConstraints(min_length=1, max_length=500)]
    escalated_to_human: bool
    rationale: Annotated[str, StringConstraints(min_length=1, max_length=4000)]
    final_state: TriageState
    guards_triggered: tuple[GuardCode, ...] = ()
    injection_detected: bool = False
    language: Language = Language.EN

    @model_validator(mode="after")
    def _check_terminal_and_consistent(self) -> "TriageResult":
        if self.final_state not in TERMINAL_STATES:
            raise ValueError(
                f"final_state must be a terminal state, got {self.final_state.value}"
            )
        expected = self.final_state is TriageState.ESCALATED
        if self.escalated_to_human is not expected:
            raise ValueError(
                "escalated_to_human must agree with final_state "
                f"(final_state={self.final_state.value}, escalated_to_human={self.escalated_to_human})"
            )
        return self
