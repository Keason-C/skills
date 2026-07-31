"""Shared test scaffolding.

The only test double in this suite is `ScriptedDriver`: an adapter at the `LLMDriver` seam that
returns Suggestions we chose in advance. It exists so Guard behaviour can be tested against *any*
model opinion — including opinions the shipped `MockDriver` would never form — without patching
anything internal. Nothing else in the codebase is ever mocked.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from triagebot.models import Action, Category, Priority, Sentiment, Suggestion, Ticket
from triagebot.tools import ToolContext


class ScriptedDriver:
    """An `LLMDriver` that replays prepared Suggestions, one per call."""

    def __init__(self, *suggestions: Suggestion) -> None:
        if not suggestions:
            raise ValueError("ScriptedDriver needs at least one Suggestion")
        self._suggestions = list(suggestions)
        self.calls: list[tuple[Ticket, ToolContext | None]] = []

    def suggest(self, ticket: Ticket, context: ToolContext | None) -> Suggestion:
        self.calls.append((ticket, context))
        index = min(len(self.calls) - 1, len(self._suggestions) - 1)
        return self._suggestions[index]

    @property
    def call_count(self) -> int:
        return len(self.calls)


def suggestion(
    *,
    category: Category = Category.TECHNICAL,
    priority: Priority = Priority.P2_NORMAL,
    sentiment: Sentiment = Sentiment.NEUTRAL,
    confidence: float = 0.9,
    action: Action = Action.ROUTE_TO_TECH_SUPPORT,
    rationale: str = "scripted",
) -> Suggestion:
    return Suggestion(
        category=category,
        priority=priority,
        sentiment=sentiment,
        confidence=confidence,
        action=action,
        rationale=rationale,
    )


def ticket(
    *,
    id: str = "TCK-1",
    customer_id: str = "CUST-1",
    subject: str = "App crashes on launch",
    body: str = "The app crashes every time I open it.",
    order_id: str | None = None,
    amount: Decimal | None = None,
) -> Ticket:
    return Ticket(
        id=id,
        customer_id=customer_id,
        subject=subject,
        body=body,
        order_id=order_id,
        amount=amount,
    )


@pytest.fixture
def scripted() -> type[ScriptedDriver]:
    return ScriptedDriver
