"""Slice 04 — an unsure model gets one more look, this time with the facts. Then a human.

The Driver is an external boundary (a paid model call), so how many times we cross it, and what
we send when we do, are behaviours the product owner specified — not implementation details.
"""

from __future__ import annotations

import pytest

from triagebot.models import Action, Category, Sentiment
from triagebot.pipeline import triage_ticket
from triagebot.stages import TriageStage
from triagebot.tools import Category as _Category  # noqa: F401 - keeps import list honest
from triagebot.tools import FixtureTools

from .conftest import ScriptedDriver, suggestion, ticket

UNSURE = suggestion(confidence=0.41, rationale="Not sure what this is about.")
SURE = suggestion(confidence=0.88, category=Category.ACCOUNT, action=Action.ROUTE_TO_ACCOUNT_TEAM)


def test_an_unsure_suggestion_is_asked_again() -> None:
    driver = ScriptedDriver(UNSURE, SURE)

    triage_ticket(ticket(), driver)

    assert driver.call_count == 2


def test_the_second_look_gets_the_facts_the_first_one_did_not() -> None:
    driver = ScriptedDriver(UNSURE, SURE)

    triage_ticket(ticket(order_id="ORD-1001"), driver)

    first_context = driver.calls[0][1]
    second_context = driver.calls[1][1]
    assert first_context is None
    assert second_context is not None
    assert second_context.order is not None
    assert second_context.order.found is True


def test_a_second_look_that_clears_the_threshold_is_the_one_that_counts() -> None:
    verdict = triage_ticket(ticket(), ScriptedDriver(UNSURE, SURE))

    assert verdict.category is Category.ACCOUNT
    assert verdict.confidence == 0.88
    assert verdict.escalated_to_human is False


def test_a_second_look_that_is_still_unsure_reaches_a_human() -> None:
    verdict = triage_ticket(ticket(), ScriptedDriver(UNSURE, UNSURE))

    assert verdict.escalated_to_human is True
    assert verdict.stage is TriageStage.ESCALATED
    assert "confidence" in verdict.guards_fired


def test_there_is_never_a_third_look() -> None:
    driver = ScriptedDriver(UNSURE, UNSURE)

    triage_ticket(ticket(), driver)

    assert driver.call_count == 2


def test_confidence_exactly_at_the_threshold_is_good_enough() -> None:
    driver = ScriptedDriver(suggestion(confidence=0.6))

    verdict = triage_ticket(ticket(), driver)

    assert driver.call_count == 1
    assert verdict.escalated_to_human is False


def test_confidence_a_hair_below_the_threshold_triggers_the_retry() -> None:
    driver = ScriptedDriver(suggestion(confidence=0.59), SURE)

    triage_ticket(ticket(), driver)

    assert driver.call_count == 2


def test_a_confident_first_look_is_the_only_look() -> None:
    driver = ScriptedDriver(suggestion(confidence=0.95))

    triage_ticket(ticket(), driver)

    assert driver.call_count == 1


def test_the_rationale_records_that_confidence_was_the_reason() -> None:
    verdict = triage_ticket(ticket(), ScriptedDriver(UNSURE, UNSURE))

    assert "0.6" in verdict.rationale


class _SingleUseTools:
    """A Tools adapter that refuses a second lookup of the same order."""

    def __init__(self) -> None:
        self._inner = FixtureTools()
        self._seen: set[str] = set()

    def get_order_status(self, order_id: str):  # noqa: ANN201 - protocol shape
        if order_id in self._seen:
            raise AssertionError("the same order was looked up twice for one Ticket")
        self._seen.add(order_id)
        return self._inner.get_order_status(order_id)

    def get_refund_policy(self, category):  # noqa: ANN001, ANN201 - protocol shape
        return self._inner.get_refund_policy(category)


def test_the_retry_reuses_the_facts_rather_than_fetching_them_again() -> None:
    verdict = triage_ticket(
        ticket(order_id="ORD-1003"), ScriptedDriver(UNSURE, SURE), tools=_SingleUseTools()
    )

    assert verdict.confidence == 0.88


@pytest.mark.parametrize("confidence", [0.0, 0.3, 0.5999])
def test_any_confidence_below_the_threshold_leads_to_a_human_when_it_does_not_improve(
    confidence: float,
) -> None:
    low = suggestion(confidence=confidence, sentiment=Sentiment.NEUTRAL)

    verdict = triage_ticket(ticket(), ScriptedDriver(low, low))

    assert verdict.escalated_to_human is True
