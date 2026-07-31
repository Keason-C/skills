"""Slice 01 — the spine: a Ticket goes in at the top seam, a Verdict comes out."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from triagebot.models import Action, Category, Priority, Sentiment, TriageResult
from triagebot.pipeline import triage_ticket
from triagebot.stages import TriageStage

from .conftest import ScriptedDriver, suggestion, ticket


def test_a_ticket_produces_a_verdict() -> None:
    verdict = triage_ticket(ticket(), ScriptedDriver(suggestion()))

    assert isinstance(verdict, TriageResult)
    assert verdict.ticket_id == "TCK-1"
    assert verdict.category is Category.TECHNICAL
    assert verdict.sentiment is Sentiment.NEUTRAL
    assert verdict.recommended_action is Action.ROUTE_TO_TECH_SUPPORT
    assert verdict.rationale


def test_a_verdict_always_ends_in_a_terminal_stage() -> None:
    verdict = triage_ticket(ticket(), ScriptedDriver(suggestion()))

    assert verdict.stage in {TriageStage.AUTO_RESOLVED, TriageStage.ESCALATED}


def test_a_verdict_cannot_be_built_in_a_non_terminal_stage() -> None:
    with pytest.raises(ValidationError):
        TriageResult(
            ticket_id="TCK-1",
            category=Category.TECHNICAL,
            priority=Priority.P2_NORMAL,
            sentiment=Sentiment.NEUTRAL,
            confidence=0.9,
            recommended_action=Action.ROUTE_TO_TECH_SUPPORT,
            escalated_to_human=False,
            injection_detected=False,
            stage=TriageStage.CLASSIFIED,
            rationale="halfway through",
            guards_fired=(),
        )


def test_a_verdict_out_of_range_confidence_is_refused() -> None:
    with pytest.raises(ValidationError):
        TriageResult(
            ticket_id="TCK-1",
            category=Category.TECHNICAL,
            priority=Priority.P2_NORMAL,
            sentiment=Sentiment.NEUTRAL,
            confidence=1.4,
            recommended_action=Action.ROUTE_TO_TECH_SUPPORT,
            escalated_to_human=False,
            injection_detected=False,
            stage=TriageStage.AUTO_RESOLVED,
            rationale="over-confident",
            guards_fired=(),
        )


def test_a_confident_uncontroversial_ticket_is_auto_resolved() -> None:
    verdict = triage_ticket(ticket(), ScriptedDriver(suggestion(confidence=0.9)))

    assert verdict.escalated_to_human is False
    assert verdict.stage is TriageStage.AUTO_RESOLVED
