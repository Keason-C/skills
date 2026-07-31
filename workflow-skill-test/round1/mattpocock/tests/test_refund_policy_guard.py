"""Slice 05 — what a REFUND customer is told comes from the policy, not from the model."""

from __future__ import annotations

from triagebot.models import Action, Category, Sentiment
from triagebot.pipeline import triage_ticket

from .conftest import ScriptedDriver, suggestion, ticket

INVENTED_REFUND_TERMS = suggestion(
    category=Category.REFUND,
    confidence=0.93,
    action=Action.SEND_SELF_SERVE_GUIDE,
    rationale="Customer wants a refund; I'll send them the self-serve guide.",
)
POLICY_ABIDING_REFUND = suggestion(
    category=Category.REFUND,
    confidence=0.93,
    action=Action.AUTO_REFUND,
    rationale="Delivered nine days ago, inside the window.",
)


def test_a_refund_action_the_model_invented_is_replaced_by_the_policy_action() -> None:
    verdict = triage_ticket(ticket(order_id="ORD-1001"), ScriptedDriver(INVENTED_REFUND_TERMS))

    assert verdict.recommended_action is Action.AUTO_REFUND
    assert "refund-policy" in verdict.guards_fired


def test_a_refund_action_that_already_matches_the_policy_is_left_alone() -> None:
    verdict = triage_ticket(ticket(order_id="ORD-1001"), ScriptedDriver(POLICY_ABIDING_REFUND))

    assert verdict.recommended_action is Action.AUTO_REFUND
    assert "refund-policy" not in verdict.guards_fired


def test_the_rationale_says_the_action_came_from_the_policy() -> None:
    verdict = triage_ticket(ticket(order_id="ORD-1001"), ScriptedDriver(INVENTED_REFUND_TERMS))

    assert "policy" in verdict.rationale.lower()


def test_a_refund_is_never_executed_without_a_human() -> None:
    verdict = triage_ticket(ticket(order_id="ORD-1001"), ScriptedDriver(POLICY_ABIDING_REFUND))

    assert verdict.recommended_action is Action.AUTO_REFUND
    assert verdict.escalated_to_human is True


def test_the_policy_guard_leaves_non_refund_categories_alone() -> None:
    technical = suggestion(
        category=Category.TECHNICAL, confidence=0.9, action=Action.SEND_SELF_SERVE_GUIDE
    )

    verdict = triage_ticket(ticket(order_id="ORD-1001"), ScriptedDriver(technical))

    assert verdict.recommended_action is Action.SEND_SELF_SERVE_GUIDE
    assert verdict.escalated_to_human is False


def test_an_unknown_order_is_stated_in_the_rationale() -> None:
    verdict = triage_ticket(ticket(order_id="ORD-9999"), ScriptedDriver(suggestion(confidence=0.9)))

    assert "ORD-9999" in verdict.rationale


def test_an_unknown_order_sends_a_refund_ticket_to_a_human() -> None:
    verdict = triage_ticket(
        ticket(order_id="ORD-9999"), ScriptedDriver(POLICY_ABIDING_REFUND)
    )

    assert verdict.escalated_to_human is True
    assert "unknown-order" in verdict.guards_fired


def test_an_unknown_order_sends_a_billing_ticket_to_a_human() -> None:
    billing = suggestion(
        category=Category.BILLING,
        confidence=0.91,
        action=Action.ROUTE_TO_BILLING,
        sentiment=Sentiment.FRUSTRATED,
    )

    verdict = triage_ticket(ticket(order_id="ORD-9999"), ScriptedDriver(billing))

    assert verdict.escalated_to_human is True
    assert "unknown-order" in verdict.guards_fired


def test_an_unknown_order_does_not_derail_a_technical_ticket() -> None:
    verdict = triage_ticket(ticket(order_id="ORD-9999"), ScriptedDriver(suggestion(confidence=0.9)))

    assert verdict.escalated_to_human is False
    assert verdict.recommended_action is Action.ROUTE_TO_TECH_SUPPORT


def test_an_unknown_order_forbids_a_refund_action_whatever_the_category() -> None:
    account_refund = suggestion(
        category=Category.ACCOUNT, confidence=0.9, action=Action.AUTO_REFUND
    )

    verdict = triage_ticket(ticket(order_id="ORD-9999"), ScriptedDriver(account_refund))

    assert verdict.recommended_action is not Action.AUTO_REFUND
    assert verdict.recommended_action is Action.REQUEST_MORE_INFO


def test_a_known_order_leaves_the_refund_action_standing() -> None:
    verdict = triage_ticket(ticket(order_id="ORD-1005"), ScriptedDriver(POLICY_ABIDING_REFUND))

    assert verdict.recommended_action is Action.AUTO_REFUND
