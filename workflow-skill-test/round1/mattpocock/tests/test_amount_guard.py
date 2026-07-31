"""Slice 03 — large sums always reach a human, whatever the model thought."""

from __future__ import annotations

from decimal import Decimal

from triagebot.models import Action, Category, Sentiment
from triagebot.pipeline import triage_ticket
from triagebot.stages import TriageStage

from .conftest import ScriptedDriver, suggestion, ticket

RELAXED = suggestion(
    category=Category.BILLING,
    sentiment=Sentiment.NEUTRAL,
    confidence=0.98,
    action=Action.SEND_SELF_SERVE_GUIDE,
    rationale="Looks like a routine question about a charge.",
)


def test_a_dispute_above_the_threshold_escalates_however_confident_the_model_was() -> None:
    verdict = triage_ticket(ticket(amount=Decimal("5000.00")), ScriptedDriver(RELAXED))

    assert verdict.escalated_to_human is True
    assert verdict.stage is TriageStage.ESCALATED


def test_a_dispute_one_cent_over_the_threshold_escalates() -> None:
    verdict = triage_ticket(ticket(amount=Decimal("1000.01")), ScriptedDriver(RELAXED))

    assert verdict.escalated_to_human is True


def test_a_dispute_exactly_at_the_threshold_does_not_escalate() -> None:
    verdict = triage_ticket(ticket(amount=Decimal("1000.00")), ScriptedDriver(RELAXED))

    assert verdict.escalated_to_human is False
    assert verdict.stage is TriageStage.AUTO_RESOLVED


def test_a_ticket_with_no_amount_is_unaffected_by_the_amount_guard() -> None:
    verdict = triage_ticket(ticket(amount=None), ScriptedDriver(RELAXED))

    assert verdict.escalated_to_human is False


def test_the_rationale_explains_why_a_large_dispute_escalated() -> None:
    verdict = triage_ticket(ticket(amount=Decimal("2500.00")), ScriptedDriver(RELAXED))

    assert "1000.00" in verdict.rationale
    assert "2500.00" in verdict.rationale


def test_the_amount_guard_is_named_on_the_verdict() -> None:
    verdict = triage_ticket(ticket(amount=Decimal("2500.00")), ScriptedDriver(RELAXED))

    assert "amount" in verdict.guards_fired
