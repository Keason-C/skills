"""Refund policy and terminal action guards -- scenarios V12-V16 (task T048).

FR-015 (action constrained to policy), FR-016 (no policy -> escalate), FR-016a (outside the
window -> escalate, never auto-deny), FR-016b (terminal actions are never executed),
SC-003, SC-001b.
"""

from __future__ import annotations

import pytest

from triagebot import (
    ActionKind,
    Category,
    GuardRule,
    PolicyFound,
    TriageState,
    triage,
)
from triagebot.guards.refund import refund_policy_guard, terminal_action_guard
from triagebot.models import TERMINAL_ACTIONS
from triagebot.tools.orders import get_order_status
from triagebot.tools.policies import get_refund_policy

from .conftest import AS_OF, ScriptedDriver, build_context, make_proposal, make_ticket

REFUND_POLICY = get_refund_policy(Category.REFUND)


def refund_proposal(action: ActionKind, **kwargs: object) -> object:
    return make_proposal(category=Category.REFUND, suggested_action=action, **kwargs)  # type: ignore[arg-type]


def _findings(result, rule: GuardRule):  # noqa: ANN001, ANN202
    return [f for f in result.guard_findings if f.rule is rule]


# --- Terminal action guard (FR-016b) --------------------------------------------------


@pytest.mark.parametrize("action", sorted(TERMINAL_ACTIONS, key=lambda a: a.value))
def test_terminal_actions_fire(action: ActionKind) -> None:
    finding = terminal_action_guard(action)
    assert finding is not None
    assert finding.rule is GuardRule.TERMINAL_ACTION


@pytest.mark.parametrize(
    "action",
    [
        ActionKind.ANSWER_QUESTION,
        ActionKind.REQUEST_INFO,
        ActionKind.RESET_CREDENTIALS,
        ActionKind.INVESTIGATE_TECHNICAL,
        ActionKind.ROUTE_TO_HUMAN,
    ],
)
def test_non_terminal_actions_do_not_fire(action: ActionKind) -> None:
    assert terminal_action_guard(action) is None


def test_terminal_set_is_exactly_the_money_and_denial_actions() -> None:
    assert TERMINAL_ACTIONS == {
        ActionKind.APPROVE_REFUND,
        ActionKind.DENY_REFUND,
        ActionKind.ISSUE_STORE_CREDIT,
    }


# --- Policy guard in isolation --------------------------------------------------------


def test_non_refund_categories_pass_through() -> None:
    context = build_context(policy=REFUND_POLICY)
    action, findings = refund_policy_guard(
        context,
        make_proposal(suggested_action=ActionKind.INVESTIGATE_TECHNICAL),
        Category.TECHNICAL,
    )
    assert action is ActionKind.INVESTIGATE_TECHNICAL
    assert findings == []


def test_permitted_action_is_kept() -> None:
    context = build_context(
        policy=REFUND_POLICY, order=get_order_status("ORD-1006", as_of=AS_OF)
    )
    action, findings = refund_policy_guard(
        context, refund_proposal(ActionKind.REQUEST_INFO), Category.REFUND
    )
    assert action is ActionKind.REQUEST_INFO
    assert findings == []


def test_non_permitted_action_is_replaced() -> None:
    """FR-015: the model does not get to invent a remedy the policy has not authorised."""
    context = build_context(
        policy=REFUND_POLICY, order=get_order_status("ORD-1006", as_of=AS_OF)
    )
    action, findings = refund_policy_guard(
        context, refund_proposal(ActionKind.RESET_CREDENTIALS), Category.REFUND
    )
    assert isinstance(REFUND_POLICY, PolicyFound)
    assert action in REFUND_POLICY.permitted_actions
    assert action is not ActionKind.RESET_CREDENTIALS
    assert findings[0].rule is GuardRule.REFUND_POLICY
    assert findings[0].proposed == ActionKind.RESET_CREDENTIALS.value


def test_missing_policy_escalates_rather_than_guessing() -> None:
    """FR-016."""
    context = build_context(policy=get_refund_policy(Category.OTHER))
    action, findings = refund_policy_guard(
        context, refund_proposal(ActionKind.APPROVE_REFUND), Category.REFUND
    )
    assert action is ActionKind.ROUTE_TO_HUMAN
    assert any(f.field == "escalated_to_human" for f in findings)


def test_refund_without_an_order_escalates() -> None:
    """The window cannot be verified with no order, so the machine does not decide."""
    context = build_context(policy=REFUND_POLICY, order=None)
    _, findings = refund_policy_guard(
        context, refund_proposal(ActionKind.REQUEST_INFO), Category.REFUND
    )
    assert any(f.field == "escalated_to_human" for f in findings)


def test_unknown_order_on_a_refund_escalates() -> None:
    context = build_context(
        policy=REFUND_POLICY, order=get_order_status("ORD-NOPE", as_of=AS_OF)
    )
    _, findings = refund_policy_guard(
        context, refund_proposal(ActionKind.REQUEST_INFO), Category.REFUND
    )
    assert any(f.field == "escalated_to_human" for f in findings)


def test_inside_window_does_not_escalate() -> None:
    context = build_context(
        policy=REFUND_POLICY, order=get_order_status("ORD-1006", as_of=AS_OF)
    )
    _, findings = refund_policy_guard(
        context, refund_proposal(ActionKind.REQUEST_INFO), Category.REFUND
    )
    assert findings == []


def test_outside_window_escalates_and_never_auto_denies() -> None:
    """FR-016a: a human says no. The system must not emit an automated denial."""
    context = build_context(
        policy=REFUND_POLICY, order=get_order_status("ORD-1002", as_of=AS_OF)
    )
    action, findings = refund_policy_guard(
        context, refund_proposal(ActionKind.REQUEST_INFO), Category.REFUND
    )
    assert any(f.field == "escalated_to_human" for f in findings)
    assert action is not ActionKind.DENY_REFUND
    assert "never issues an automated denial" in " ".join(f.detail for f in findings)


def test_undelivered_order_is_inside_the_window() -> None:
    """A refund window that has not started cannot have been missed."""
    context = build_context(
        policy=REFUND_POLICY, order=get_order_status("ORD-1004", as_of=AS_OF)
    )
    _, findings = refund_policy_guard(
        context, refund_proposal(ActionKind.REQUEST_INFO), Category.REFUND
    )
    assert findings == []


# --- End to end -----------------------------------------------------------------------


def test_in_window_non_terminal_action_auto_resolves() -> None:
    """V12."""
    driver = ScriptedDriver(refund_proposal(ActionKind.REQUEST_INFO, confidence=0.9))  # type: ignore[arg-type]
    result = triage(
        make_ticket(subject="Refund question", body="I would like a refund.", order_id="ORD-1006"),
        driver,  # type: ignore[arg-type]
        as_of=AS_OF,
    )
    assert result.state is TriageState.AUTO_RESOLVED
    assert isinstance(REFUND_POLICY, PolicyFound)
    assert result.recommended_action in REFUND_POLICY.permitted_actions


def test_approve_refund_is_recommended_but_never_executed() -> None:
    """V16 / SC-001b: the machine may suggest paying, but a human pays."""
    driver = ScriptedDriver(refund_proposal(ActionKind.APPROVE_REFUND, confidence=0.95))  # type: ignore[arg-type]
    result = triage(
        make_ticket(subject="Refund", body="Please refund me.", order_id="ORD-1006"),
        driver,  # type: ignore[arg-type]
        as_of=AS_OF,
    )
    assert result.recommended_action is ActionKind.APPROVE_REFUND
    assert result.escalated_to_human is True
    assert _findings(result, GuardRule.TERMINAL_ACTION)


def test_out_of_window_refund_escalates_end_to_end() -> None:
    """V15."""
    driver = ScriptedDriver(refund_proposal(ActionKind.REQUEST_INFO, confidence=0.9))  # type: ignore[arg-type]
    result = triage(
        make_ticket(subject="Refund", body="I want a refund.", order_id="ORD-1002"),
        driver,  # type: ignore[arg-type]
        as_of=AS_OF,
    )
    assert result.escalated_to_human is True
    assert result.recommended_action is not ActionKind.DENY_REFUND


def test_no_recommendation_ever_originates_from_the_model_alone() -> None:
    """SC-003: for every refund outcome, the action is policy-permitted or ROUTE_TO_HUMAN."""
    assert isinstance(REFUND_POLICY, PolicyFound)
    allowed = set(REFUND_POLICY.permitted_actions) | {ActionKind.ROUTE_TO_HUMAN}
    for action in ActionKind:
        driver = ScriptedDriver(refund_proposal(action, confidence=0.9))  # type: ignore[arg-type]
        result = triage(
            make_ticket(subject="Refund", body="Refund please.", order_id="ORD-1006"),
            driver,  # type: ignore[arg-type]
            as_of=AS_OF,
        )
        assert result.recommended_action in allowed, f"leaked action for suggestion {action}"
