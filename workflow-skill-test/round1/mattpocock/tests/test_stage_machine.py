"""Slice 01 — a Ticket's walk through the Triage Stage machine is real, not decorative."""

from __future__ import annotations

import pytest

from triagebot.stages import IllegalStageTransition, TriageStage, advance


def test_a_new_ticket_can_be_enriched() -> None:
    assert advance(TriageStage.NEW, TriageStage.ENRICHED) is TriageStage.ENRICHED


def test_an_enriched_ticket_can_be_classified() -> None:
    assert advance(TriageStage.ENRICHED, TriageStage.CLASSIFIED) is TriageStage.CLASSIFIED


def test_a_classified_ticket_can_be_auto_resolved_or_escalated() -> None:
    assert advance(TriageStage.CLASSIFIED, TriageStage.AUTO_RESOLVED) is TriageStage.AUTO_RESOLVED
    assert advance(TriageStage.CLASSIFIED, TriageStage.ESCALATED) is TriageStage.ESCALATED


def test_classification_cannot_skip_enrichment() -> None:
    with pytest.raises(IllegalStageTransition):
        advance(TriageStage.NEW, TriageStage.CLASSIFIED)


def test_a_ticket_cannot_be_resolved_before_it_is_classified() -> None:
    with pytest.raises(IllegalStageTransition):
        advance(TriageStage.ENRICHED, TriageStage.AUTO_RESOLVED)


def test_a_terminal_stage_is_terminal() -> None:
    with pytest.raises(IllegalStageTransition):
        advance(TriageStage.ESCALATED, TriageStage.AUTO_RESOLVED)

    with pytest.raises(IllegalStageTransition):
        advance(TriageStage.AUTO_RESOLVED, TriageStage.CLASSIFIED)


def test_a_stage_cannot_advance_to_itself() -> None:
    with pytest.raises(IllegalStageTransition):
        advance(TriageStage.ENRICHED, TriageStage.ENRICHED)


def test_the_rejection_names_both_stages() -> None:
    with pytest.raises(IllegalStageTransition) as raised:
        advance(TriageStage.NEW, TriageStage.ESCALATED)

    assert "NEW" in str(raised.value)
    assert "ESCALATED" in str(raised.value)
