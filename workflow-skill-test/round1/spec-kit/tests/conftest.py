"""Shared fixtures (task T022).

Nothing here touches the network or reads a credential; that is a hard requirement of the
constitution (Principle IV), not a stylistic preference.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from triagebot import (
    ActionKind,
    Category,
    ClassificationProposal,
    InjectionScan,
    Language,
    Priority,
    Sentiment,
    Ticket,
    ToolContext,
    TriageSettings,
)
from triagebot.drivers.mock import MockDriver

#: Fixed reference date so refund-window arithmetic never depends on when the suite runs.
AS_OF = date(2026, 7, 31)


@pytest.fixture
def settings() -> TriageSettings:
    return TriageSettings()


@pytest.fixture
def driver() -> MockDriver:
    return MockDriver()


def make_ticket(
    *,
    id: str = "T-1",
    customer_id: str = "C-1",
    subject: str = "Cannot log in to my account",
    body: str = "My password reset link does nothing and I cannot sign in.",
    order_id: str | None = None,
    amount: Decimal | None = None,
) -> Ticket:
    """Build a valid ticket with sensible defaults, overriding only what a test cares about."""
    return Ticket(
        id=id,
        customer_id=customer_id,
        subject=subject,
        body=body,
        order_id=order_id,
        amount=amount,
    )


def build_context(
    *,
    order: object | None = None,
    policy: object | None = None,
    injection_detected: bool = False,
    signatures: tuple[str, ...] = (),
    language: Language = Language.EN,
) -> ToolContext:
    """Build a ToolContext directly, for guards tested in isolation from the pipeline."""
    return ToolContext(
        order=order,  # type: ignore[arg-type]
        policy=policy,  # type: ignore[arg-type]
        injection=InjectionScan(detected=injection_detected, signatures=signatures),
        language=language,
    )


@pytest.fixture
def make_context():  # noqa: ANN201
    """Fixture wrapper around :func:`build_context`."""
    return build_context


def make_proposal(
    *,
    category: Category = Category.TECHNICAL,
    priority: Priority = Priority.P2,
    sentiment: Sentiment = Sentiment.NEUTRAL,
    confidence: float = 0.9,
    suggested_action: ActionKind = ActionKind.INVESTIGATE_TECHNICAL,
    reasoning: str = "scripted proposal",
) -> ClassificationProposal:
    return ClassificationProposal(
        category=category,
        priority=priority,
        sentiment=sentiment,
        confidence=confidence,
        suggested_action=suggested_action,
        reasoning=reasoning,
    )


class ScriptedDriver:
    """Returns a fixed sequence of proposals and counts its calls (task T042).

    Needed for the confidence boundary tests: `MockDriver` produces realistic confidences,
    but pinning behaviour at exactly 0.60 requires saying so.
    """

    name = "scripted"

    def __init__(self, *proposals: ClassificationProposal) -> None:
        if not proposals:
            raise ValueError("ScriptedDriver needs at least one proposal")
        self._proposals = list(proposals)
        self.calls = 0
        self.contexts: list[ToolContext | None] = []
        self.tickets: list[Ticket] = []

    def classify(
        self,
        ticket: Ticket,
        context: ToolContext | None = None,
    ) -> ClassificationProposal:
        index = min(self.calls, len(self._proposals) - 1)
        self.calls += 1
        self.contexts.append(context)
        self.tickets.append(ticket)
        return self._proposals[index]
