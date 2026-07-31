from decimal import Decimal

from triagebot.guards import (
    amount_guard,
    confidence_guard,
    decide_final_state,
    derive_priority,
    language_guard,
    order_evidence_guard,
    refund_policy_guard,
)
from triagebot.models import Category, GuardCode, Language, Priority, Sentiment
from triagebot.states import TriageState
from triagebot.tools import ToolBox

# --- amount boundary ---------------------------------------------------------


def test_amount_just_below_threshold_does_not_escalate():
    assert amount_guard(Decimal("999.99")) is None


def test_amount_exactly_at_threshold_does_not_escalate():
    assert amount_guard(Decimal("1000.00")) is None


def test_amount_just_over_threshold_escalates():
    assert amount_guard(Decimal("1000.01")) is GuardCode.AMOUNT_THRESHOLD


def test_absent_amount_does_not_escalate():
    assert amount_guard(None) is None


# --- confidence boundary -----------------------------------------------------


def test_confidence_below_threshold_trips_the_guard():
    assert confidence_guard(0.59) is GuardCode.LOW_CONFIDENCE


def test_confidence_exactly_at_threshold_passes():
    assert confidence_guard(0.60) is None


def test_confidence_above_threshold_passes():
    assert confidence_guard(0.95) is None


# --- language ----------------------------------------------------------------


def test_unsupported_language_forces_other_and_caps_confidence():
    category, confidence, guard = language_guard(Language.OTHER, Category.REFUND, 0.95)
    assert category is Category.OTHER
    assert confidence == 0.5
    assert guard is GuardCode.UNSUPPORTED_LANGUAGE


def test_unsupported_language_never_raises_a_lower_confidence():
    _category, confidence, _guard = language_guard(Language.OTHER, Category.REFUND, 0.2)
    assert confidence == 0.2


def test_supported_language_leaves_suggestion_untouched():
    assert language_guard(Language.ZH, Category.REFUND, 0.9) == (Category.REFUND, 0.9, None)


# --- refund policy -----------------------------------------------------------


def test_refund_action_is_overridden_by_policy():
    policy = ToolBox().get_refund_policy(Category.REFUND)
    action, guard = refund_policy_guard(Category.REFUND, "just give them store credit", policy)
    assert action == policy.canonical_action
    assert guard is GuardCode.REFUND_POLICY_OVERRIDE


def test_refund_action_matching_policy_needs_no_override():
    policy = ToolBox().get_refund_policy(Category.REFUND)
    action, guard = refund_policy_guard(Category.REFUND, policy.canonical_action, policy)
    assert action == policy.canonical_action
    assert guard is None


def test_missing_refund_policy_escalates():
    _action, guard = refund_policy_guard(Category.REFUND, "anything", None)
    assert guard is GuardCode.REFUND_POLICY_MISSING


def test_non_refund_category_is_not_touched_by_the_policy_guard():
    policy = ToolBox().get_refund_policy(Category.BILLING)
    action, guard = refund_policy_guard(Category.BILLING, "check the invoice", policy)
    assert action == "check the invoice"
    assert guard is None


# --- order evidence ----------------------------------------------------------


def test_unknown_order_on_refund_escalates():
    assert order_evidence_guard(Category.REFUND, True, False) is GuardCode.MISSING_ORDER_EVIDENCE


def test_unknown_order_on_billing_escalates():
    assert order_evidence_guard(Category.BILLING, True, False) is GuardCode.MISSING_ORDER_EVIDENCE


def test_unknown_order_on_technical_does_not_escalate():
    assert order_evidence_guard(Category.TECHNICAL, True, False) is None


def test_no_lookup_attempted_is_not_missing_evidence():
    assert order_evidence_guard(Category.REFUND, False, False) is None


def test_found_order_is_not_missing_evidence():
    assert order_evidence_guard(Category.REFUND, True, True) is None


# --- priority ----------------------------------------------------------------


def test_injection_is_a_p0_security_event():
    assert derive_priority(Category.BILLING, None, Sentiment.NEUTRAL, True, "whatever") is Priority.P0


def test_technical_outage_is_p0():
    assert (
        derive_priority(Category.TECHNICAL, None, Sentiment.NEUTRAL, False, "the service is down")
        is Priority.P0
    )


def test_chinese_outage_wording_is_p0():
    assert (
        derive_priority(Category.TECHNICAL, None, Sentiment.NEUTRAL, False, "系统宕机了")
        is Priority.P0
    )


def test_outage_wording_on_a_billing_ticket_is_not_p0():
    assert (
        derive_priority(Category.BILLING, None, Sentiment.NEUTRAL, False, "the service is down")
        is not Priority.P0
    )


def test_payment_failure_blocks_core_operation_and_is_p1():
    assert (
        derive_priority(Category.BILLING, None, Sentiment.NEUTRAL, False, "my payment failed")
        is Priority.P1
    )


def test_account_lockout_is_p1():
    assert (
        derive_priority(Category.ACCOUNT, None, Sentiment.NEUTRAL, False, "I am locked out")
        is Priority.P1
    )


def test_large_amount_is_at_least_p1():
    assert (
        derive_priority(Category.REFUND, Decimal("2000.00"), Sentiment.NEUTRAL, False, "refund")
        is Priority.P1
    )


def test_ordinary_issue_is_p2():
    assert (
        derive_priority(Category.REFUND, Decimal("10.00"), Sentiment.NEUTRAL, False, "refund please")
        is Priority.P2
    )


def test_inquiry_is_p3():
    assert (
        derive_priority(Category.ACCOUNT, None, Sentiment.NEUTRAL, False, "how do I change my email")
        is Priority.P3
    )


def test_other_category_is_p3():
    assert derive_priority(Category.OTHER, None, Sentiment.NEUTRAL, False, "hello") is Priority.P3


def test_anger_bumps_p2_to_p1():
    assert (
        derive_priority(Category.REFUND, None, Sentiment.ANGRY, False, "refund please") is Priority.P1
    )


def test_anger_bumps_p3_to_p2():
    assert derive_priority(Category.OTHER, None, Sentiment.ANGRY, False, "hello") is Priority.P2


def test_anger_never_downgrades_a_p0():
    assert (
        derive_priority(Category.TECHNICAL, None, Sentiment.ANGRY, False, "the service is down")
        is Priority.P0
    )


def test_frustration_does_not_bump_priority():
    assert (
        derive_priority(Category.REFUND, None, Sentiment.FRUSTRATED, False, "refund please")
        is Priority.P2
    )


# --- final state -------------------------------------------------------------


def test_clean_ticket_auto_resolves():
    assert decide_final_state((), 0.9, Priority.P2, Category.REFUND) is TriageState.AUTO_RESOLVED


def test_p0_never_auto_resolves():
    assert decide_final_state((), 0.9, Priority.P0, Category.TECHNICAL) is TriageState.ESCALATED


def test_other_category_never_auto_resolves():
    assert decide_final_state((), 0.9, Priority.P2, Category.OTHER) is TriageState.ESCALATED


def test_low_confidence_never_auto_resolves():
    assert decide_final_state((), 0.55, Priority.P2, Category.REFUND) is TriageState.ESCALATED


def test_escalating_guard_forces_escalation():
    assert (
        decide_final_state((GuardCode.AMOUNT_THRESHOLD,), 0.9, Priority.P2, Category.REFUND)
        is TriageState.ESCALATED
    )


def test_non_escalating_guard_still_allows_auto_resolution():
    assert (
        decide_final_state((GuardCode.REFUND_POLICY_OVERRIDE,), 0.9, Priority.P2, Category.REFUND)
        is TriageState.AUTO_RESOLVED
    )
