"""TriageResult cross-field invariants (task T024).

These are the last line of defence. The guards produce correct results; these validators
make an *incorrect* result unconstructible, so a future refactor that bypasses a guard fails
loudly instead of shipping. Requirements: FR-008, FR-010c, FR-016b, FR-024, SC-003a.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from triagebot import (
    ActionKind,
    Category,
    Language,
    Priority,
    Sentiment,
    TriageResult,
    TriageState,
)

_HAPPY_PATH = (TriageState.NEW, TriageState.ENRICHED, TriageState.CLASSIFIED)


def build_result(**overrides: object) -> TriageResult:
    """A valid auto-resolved result, with fields overridable one at a time."""
    base: dict[str, object] = {
        "ticket_id": "T-1",
        "category": Category.TECHNICAL,
        "priority": Priority.P2,
        "sentiment": Sentiment.NEUTRAL,
        "confidence": 0.8,
        "recommended_action": ActionKind.INVESTIGATE_TECHNICAL,
        "escalated_to_human": False,
        "rationale": "because",
        "injection_detected": False,
        "language": Language.EN,
        "state": TriageState.AUTO_RESOLVED,
        "state_path": (*_HAPPY_PATH, TriageState.AUTO_RESOLVED),
        "guard_findings": (),
        "retried": False,
        "llm_calls": 1,
    }
    base.update(overrides)
    return TriageResult(**base)  # type: ignore[arg-type]


def test_baseline_result_is_valid() -> None:
    assert build_result().state is TriageState.AUTO_RESOLVED


# --- Invariant 1: escalation and terminal state agree ---------------------------------


def test_escalated_flag_must_match_state() -> None:
    with pytest.raises(ValidationError, match="contradicts escalated_to_human"):
        build_result(escalated_to_human=True)


def test_escalated_state_must_match_flag() -> None:
    with pytest.raises(ValidationError, match="contradicts escalated_to_human"):
        build_result(
            state=TriageState.ESCALATED,
            state_path=(*_HAPPY_PATH, TriageState.ESCALATED),
        )


# --- Invariant 2: P0 always escalates (FR-010c) ---------------------------------------


def test_p0_without_escalation_rejected() -> None:
    with pytest.raises(ValidationError, match="P0 requires escalated_to_human"):
        build_result(priority=Priority.P0)


# --- Invariant 3: terminal actions are never executed (FR-016b) -----------------------


@pytest.mark.parametrize(
    "action",
    [ActionKind.APPROVE_REFUND, ActionKind.DENY_REFUND, ActionKind.ISSUE_STORE_CREDIT],
)
def test_terminal_action_without_escalation_rejected(action: ActionKind) -> None:
    with pytest.raises(ValidationError, match="terminal"):
        build_result(recommended_action=action)


def test_terminal_action_with_escalation_accepted() -> None:
    result = build_result(
        recommended_action=ActionKind.APPROVE_REFUND,
        escalated_to_human=True,
        priority=Priority.P1,
        state=TriageState.ESCALATED,
        state_path=(*_HAPPY_PATH, TriageState.ESCALATED),
    )
    assert result.recommended_action is ActionKind.APPROVE_REFUND


# --- Invariant 4: injection implies P0 + escalation -----------------------------------


def test_injection_without_p0_rejected() -> None:
    with pytest.raises(ValidationError, match="injection_detected requires"):
        build_result(
            injection_detected=True,
            escalated_to_human=True,
            priority=Priority.P1,
            state=TriageState.ESCALATED,
            state_path=(*_HAPPY_PATH, TriageState.ESCALATED),
        )


def test_injection_without_escalation_rejected() -> None:
    with pytest.raises(ValidationError):
        build_result(injection_detected=True, priority=Priority.P0)


# --- Invariant 5: retry bookkeeping (SC-003a) -----------------------------------------


def test_retried_must_match_call_count() -> None:
    with pytest.raises(ValidationError, match="contradicts llm_calls"):
        build_result(retried=True, llm_calls=1)


def test_three_llm_calls_rejected() -> None:
    """The 'at most two calls' budget is enforced by the type, not only by the pipeline."""
    with pytest.raises(ValidationError):
        build_result(retried=True, llm_calls=3)


# --- Invariant 6: the state path is honest (FR-024) -----------------------------------


def test_state_path_must_start_at_new() -> None:
    with pytest.raises(ValidationError, match="start at NEW"):
        build_result(
            state_path=(
                TriageState.ENRICHED,
                TriageState.CLASSIFIED,
                TriageState.AUTO_RESOLVED,
                TriageState.AUTO_RESOLVED,
            )
        )


def test_state_path_must_end_at_final_state() -> None:
    with pytest.raises(ValidationError, match="end at the final state"):
        build_result(state_path=(*_HAPPY_PATH, TriageState.ESCALATED))


def test_state_path_too_short_rejected() -> None:
    with pytest.raises(ValidationError):
        build_result(state_path=(TriageState.NEW, TriageState.AUTO_RESOLVED))


# --- Field-level bounds ---------------------------------------------------------------


@pytest.mark.parametrize("confidence", [-0.01, 1.01])
def test_confidence_outside_unit_interval_rejected(confidence: float) -> None:
    with pytest.raises(ValidationError):
        build_result(confidence=confidence)


def test_result_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        build_result(surprise="!")
