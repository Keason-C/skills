"""Amount threshold guard -- scenarios V6/V7 (task T038).

FR-012, SC-001, SC-008. The threshold is 1000 USD and the rule triggers on *exceeding*, not
on reaching, so the interesting values are 999.99 / 1000.00 / 1000.01.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from triagebot import GuardRule, Priority, TriageSettings, TriageState, triage
from triagebot.guards.amount import amount_guard

from .conftest import AS_OF, make_ticket


def _finding(result, rule: GuardRule):  # noqa: ANN001, ANN202
    return next((f for f in result.guard_findings if f.rule is rule), None)


# --- The guard in isolation -----------------------------------------------------------


def test_no_amount_does_not_fire(settings: TriageSettings) -> None:
    assert amount_guard(make_ticket(amount=None), settings) is None


@pytest.mark.parametrize("amount", ["0", "0.01", "999.99", "1000.00"])
def test_at_or_below_threshold_does_not_fire(amount: str, settings: TriageSettings) -> None:
    assert amount_guard(make_ticket(amount=Decimal(amount)), settings) is None


@pytest.mark.parametrize("amount", ["1000.01", "1001", "50000"])
def test_above_threshold_fires(amount: str, settings: TriageSettings) -> None:
    finding = amount_guard(make_ticket(amount=Decimal(amount)), settings)
    assert finding is not None
    assert finding.rule is GuardRule.AMOUNT_THRESHOLD


def test_exact_threshold_is_the_boundary(settings: TriageSettings) -> None:
    """The single most consequential off-by-one in the system (SC-001)."""
    assert amount_guard(make_ticket(amount=Decimal("1000.00")), settings) is None
    assert amount_guard(make_ticket(amount=Decimal("1000.01")), settings) is not None


def test_threshold_is_configurable(settings: TriageSettings) -> None:
    strict = TriageSettings(amount_escalation_threshold=Decimal("100"))
    ticket = make_ticket(amount=Decimal("500"))
    assert amount_guard(ticket, settings) is None
    assert amount_guard(ticket, strict) is not None


def test_decimal_comparison_is_exact() -> None:
    """Why Decimal, not float: this is precisely where binary floats misbehave."""
    settings = TriageSettings(amount_escalation_threshold=Decimal("0.30"))
    assert amount_guard(make_ticket(amount=Decimal("0.10") + Decimal("0.20")), settings) is None


# --- End to end through the pipeline --------------------------------------------------


@pytest.mark.parametrize(
    ("amount", "should_escalate"),
    [("999.99", False), ("1000.00", False), ("1000.01", True)],
)
def test_boundary_triple_end_to_end(amount: str, should_escalate: bool) -> None:
    ticket = make_ticket(
        subject="Refund for a damaged item",
        body="The item arrived broken and I want a refund for the full amount.",
        amount=Decimal(amount),
    )
    result = triage(ticket, as_of=AS_OF)
    fired = _finding(result, GuardRule.AMOUNT_THRESHOLD) is not None
    assert fired is should_escalate
    if should_escalate:
        assert result.escalated_to_human
        assert result.state is TriageState.ESCALATED


def test_high_amount_escalates_even_when_confident_and_benign() -> None:
    """FR-012: 'irrespective of the proposal' is the whole point of the rule."""
    ticket = make_ticket(
        subject="Question about my invoice",
        body="My invoice shows a billing overcharge and a double charge this month.",
        amount=Decimal("5000.00"),
    )
    result = triage(ticket, as_of=AS_OF)
    assert result.confidence >= 0.60, "precondition: the classification is confident"
    assert result.escalated_to_human


def test_amount_escalation_records_what_was_proposed() -> None:
    result = triage(make_ticket(amount=Decimal("2500")), as_of=AS_OF)
    finding = _finding(result, GuardRule.AMOUNT_THRESHOLD)
    assert finding is not None
    assert finding.proposed == "False"
    assert finding.final == "True"
    assert "2500" in finding.detail


def test_amount_escalation_yields_p1_not_p0() -> None:
    """A large amount is not a service outage: the product owner drew this line explicitly."""
    result = triage(make_ticket(amount=Decimal("9999")), as_of=AS_OF)
    assert result.priority is Priority.P1
