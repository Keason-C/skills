"""Slice 02 — the facts TriageBot holds about a Ticket."""

from __future__ import annotations

import pytest

from triagebot.models import Action, Category
from triagebot.pipeline import triage_ticket
from triagebot.tools import FixtureTools, OrderState, ToolContext, gather_context

from .conftest import ScriptedDriver, suggestion, ticket


@pytest.fixture
def tools() -> FixtureTools:
    return FixtureTools()


def test_a_known_order_comes_back_with_its_state(tools: FixtureTools) -> None:
    lookup = tools.get_order_status("ORD-1001")

    assert lookup.found is True
    assert lookup.record is not None
    assert lookup.record.state is OrderState.DELIVERED


def test_an_unknown_order_is_an_answer_not_a_crash(tools: FixtureTools) -> None:
    lookup = tools.get_order_status("ORD-DOES-NOT-EXIST")

    assert lookup.found is False
    assert lookup.record is None


def test_the_refund_policy_prescribes_an_action_per_category(tools: FixtureTools) -> None:
    refund_policy = tools.get_refund_policy(Category.REFUND)

    assert refund_policy.category is Category.REFUND
    assert refund_policy.prescribed_action is Action.AUTO_REFUND
    assert refund_policy.summary


def test_every_category_has_a_policy_entry(tools: FixtureTools) -> None:
    for category in Category:
        assert tools.get_refund_policy(category).category is category


def test_a_ticket_citing_an_order_gathers_that_order(tools: FixtureTools) -> None:
    context = gather_context(ticket(order_id="ORD-1001"), tools)

    assert context.order is not None
    assert context.order.found is True


def test_a_ticket_citing_no_order_gathers_no_order_facts(tools: FixtureTools) -> None:
    context = gather_context(ticket(order_id=None), tools)

    assert context.order is None


def test_gathered_context_carries_every_policy(tools: FixtureTools) -> None:
    context = gather_context(ticket(), tools)

    assert context.policy_for(Category.REFUND).prescribed_action is Action.AUTO_REFUND
    assert context.policy_for(Category.TECHNICAL).refundable is False


def test_gathered_context_is_read_only(tools: FixtureTools) -> None:
    context = gather_context(ticket(), tools)

    with pytest.raises(Exception):
        context.order = None  # type: ignore[misc]


class _RefusingTools:
    """A Tools adapter that refuses order lookups, to prove we only look up what we need."""

    def __init__(self, inner: FixtureTools) -> None:
        self._inner = inner

    def get_order_status(self, order_id: str):  # noqa: ANN201 - protocol shape
        raise AssertionError(f"no order lookup should have happened, got {order_id!r}")

    def get_refund_policy(self, category: Category):  # noqa: ANN201 - protocol shape
        return self._inner.get_refund_policy(category)


def test_a_ticket_with_no_order_never_triggers_an_order_lookup(tools: FixtureTools) -> None:
    verdict = triage_ticket(
        ticket(order_id=None), ScriptedDriver(suggestion()), tools=_RefusingTools(tools)
    )

    assert verdict.ticket_id == "TCK-1"


def test_the_pipeline_accepts_a_tools_adapter_and_still_returns_a_verdict(
    tools: FixtureTools,
) -> None:
    verdict = triage_ticket(ticket(order_id="ORD-1001"), ScriptedDriver(suggestion()), tools=tools)

    assert isinstance(verdict.category, Category)


def test_context_is_a_tool_context(tools: FixtureTools) -> None:
    assert isinstance(gather_context(ticket(), tools), ToolContext)
