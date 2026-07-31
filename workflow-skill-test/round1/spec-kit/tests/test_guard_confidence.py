"""Confidence guard and the retry path -- scenarios V8/V9/V10 (task T043).

FR-013 (one retry with context), FR-014 (escalate if still short), SC-003a (never more than
two classifier calls), SC-008 (boundary coverage).

`ScriptedDriver` is used rather than `MockDriver` because pinning behaviour at exactly 0.60
requires being able to say 0.60.
"""

from __future__ import annotations

import pytest

from triagebot import GuardRule, TriageSettings, TriageState, triage
from triagebot.guards.confidence import confidence_guard, needs_retry

from .conftest import AS_OF, ScriptedDriver, make_proposal, make_ticket


# --- Predicates in isolation ----------------------------------------------------------


@pytest.mark.parametrize("confidence", [0.0, 0.3, 0.59, 0.599])
def test_below_threshold_needs_retry(confidence: float, settings: TriageSettings) -> None:
    assert needs_retry(make_proposal(confidence=confidence), settings) is True


@pytest.mark.parametrize("confidence", [0.60, 0.61, 0.9, 1.0])
def test_at_or_above_threshold_needs_no_retry(
    confidence: float, settings: TriageSettings
) -> None:
    """Exactly at the threshold is sufficient (spec.md -> Edge Cases)."""
    assert needs_retry(make_proposal(confidence=confidence), settings) is False


def test_guard_stays_silent_before_the_retry(settings: TriageSettings) -> None:
    """Low confidence pre-retry is not yet an escalation: the pipeline retries first."""
    assert confidence_guard(make_proposal(confidence=0.4), settings, retried=False) is None


def test_guard_fires_when_still_low_after_retry(settings: TriageSettings) -> None:
    finding = confidence_guard(make_proposal(confidence=0.4), settings, retried=True)
    assert finding is not None
    assert finding.rule is GuardRule.LOW_CONFIDENCE


def test_guard_silent_when_confident_after_retry(settings: TriageSettings) -> None:
    assert confidence_guard(make_proposal(confidence=0.8), settings, retried=True) is None


def test_guard_is_pure() -> None:
    """Guards must not call a driver; a stray call would show up as a signature change."""
    settings = TriageSettings()
    proposal = make_proposal(confidence=0.4)
    assert confidence_guard(proposal, settings, retried=True) == confidence_guard(
        proposal, settings, retried=True
    )


# --- V8: exactly at the threshold, no retry -------------------------------------------


def test_confidence_at_threshold_does_not_retry() -> None:
    driver = ScriptedDriver(make_proposal(confidence=0.60))
    result = triage(make_ticket(), driver, as_of=AS_OF)  # type: ignore[arg-type]
    assert driver.calls == 1
    assert result.llm_calls == 1
    assert result.retried is False
    assert result.state is TriageState.AUTO_RESOLVED


# --- V9: retry succeeds ---------------------------------------------------------------


def test_retry_lifts_a_low_confidence_ticket() -> None:
    driver = ScriptedDriver(make_proposal(confidence=0.55), make_proposal(confidence=0.80))
    result = triage(make_ticket(), driver, as_of=AS_OF)  # type: ignore[arg-type]
    assert driver.calls == 2
    assert result.retried is True
    assert result.llm_calls == 2
    assert result.escalated_to_human is False
    assert result.confidence == pytest.approx(0.80)


def test_retry_receives_the_gathered_context() -> None:
    """FR-013: the retry only means something if the second call knows more."""
    driver = ScriptedDriver(make_proposal(confidence=0.55), make_proposal(confidence=0.80))
    triage(make_ticket(order_id="ORD-1001"), driver, as_of=AS_OF)  # type: ignore[arg-type]
    assert driver.contexts[0] is None
    assert driver.contexts[1] is not None
    assert driver.contexts[1].order is not None


# --- V10: retry fails, escalate -------------------------------------------------------


def test_still_low_after_retry_escalates() -> None:
    driver = ScriptedDriver(make_proposal(confidence=0.55), make_proposal(confidence=0.55))
    result = triage(make_ticket(), driver, as_of=AS_OF)  # type: ignore[arg-type]
    assert driver.calls == 2
    assert result.escalated_to_human is True
    assert result.state is TriageState.ESCALATED
    assert any(f.rule is GuardRule.LOW_CONFIDENCE for f in result.guard_findings)


def test_never_more_than_two_calls_even_at_zero_confidence() -> None:
    """SC-003a: the budget is a hard ceiling, not a target."""
    driver = ScriptedDriver(make_proposal(confidence=0.0))
    result = triage(make_ticket(), driver, as_of=AS_OF)  # type: ignore[arg-type]
    assert driver.calls == 2
    assert result.llm_calls == 2


def test_low_confidence_rationale_names_the_cause() -> None:
    driver = ScriptedDriver(make_proposal(confidence=0.1))
    result = triage(make_ticket(), driver, as_of=AS_OF)  # type: ignore[arg-type]
    assert "confidence" in result.rationale.lower()


def test_threshold_is_configurable() -> None:
    lenient = TriageSettings(confidence_threshold=0.5)
    driver = ScriptedDriver(make_proposal(confidence=0.55))
    result = triage(make_ticket(), driver, lenient, as_of=AS_OF)  # type: ignore[arg-type]
    assert driver.calls == 1
    assert result.escalated_to_human is False
