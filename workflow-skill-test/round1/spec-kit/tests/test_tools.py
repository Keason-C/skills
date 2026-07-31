"""Tool lookups -- scenario V11 (task T026).

FR-005 (order looked up), FR-006 (not-found is an explicit value), FR-007 (policy retrieved).
"""

from __future__ import annotations

from datetime import date

from triagebot import Category, OrderFound, OrderNotFound, OrderState, PolicyFound, PolicyNotFound
from triagebot.tools.orders import get_order_status
from triagebot.tools.policies import get_refund_policy

from .conftest import AS_OF


def test_known_order_returns_found_with_state() -> None:
    order = get_order_status("ORD-1001", as_of=AS_OF)
    assert isinstance(order, OrderFound)
    assert order.state is OrderState.DELIVERED
    assert order.delivered_on == date(2026, 7, 8)


def test_unknown_order_returns_explicit_not_found() -> None:
    """FR-006: an absence, not an exception and not None."""
    order = get_order_status("ORD-DOES-NOT-EXIST", as_of=AS_OF)
    assert isinstance(order, OrderNotFound)
    assert order.order_id == "ORD-DOES-NOT-EXIST"
    assert order.status == "not_found"


def test_days_since_delivery_measured_against_as_of() -> None:
    order = get_order_status("ORD-1001", as_of=AS_OF)
    assert isinstance(order, OrderFound)
    assert order.days_since_delivery == (AS_OF - date(2026, 7, 8)).days


def test_lookup_is_clock_free() -> None:
    """Different reference dates give different answers; the same one always agrees."""
    early = get_order_status("ORD-1001", as_of=date(2026, 7, 9))
    late = get_order_status("ORD-1001", as_of=date(2026, 9, 9))
    assert isinstance(early, OrderFound) and isinstance(late, OrderFound)
    assert early.days_since_delivery == 1
    assert late.days_since_delivery == 63
    assert get_order_status("ORD-1001", as_of=AS_OF) == get_order_status("ORD-1001", as_of=AS_OF)


def test_undelivered_order_has_no_delivery_age() -> None:
    order = get_order_status("ORD-1003", as_of=AS_OF)
    assert isinstance(order, OrderFound)
    assert order.state is OrderState.SHIPPED
    assert order.delivered_on is None
    assert order.days_since_delivery is None


def test_fixture_covers_every_order_state() -> None:
    """Boundary coverage depends on the fixture spanning the whole lifecycle."""
    states = {
        get_order_status(oid, as_of=AS_OF).state  # type: ignore[union-attr]
        for oid in ("ORD-1001", "ORD-1003", "ORD-1004", "ORD-1005")
    }
    assert states == set(OrderState)


def test_known_category_returns_policy() -> None:
    policy = get_refund_policy(Category.REFUND)
    assert isinstance(policy, PolicyFound)
    assert policy.window_days == 30
    assert len(policy.permitted_actions) >= 1


def test_missing_category_returns_explicit_not_found() -> None:
    """OTHER is deliberately absent from the fixture so FR-016's path stays reachable."""
    policy = get_refund_policy(Category.OTHER)
    assert isinstance(policy, PolicyNotFound)
    assert policy.category is Category.OTHER


def test_policy_lookup_is_deterministic() -> None:
    assert get_refund_policy(Category.REFUND) == get_refund_policy(Category.REFUND)
