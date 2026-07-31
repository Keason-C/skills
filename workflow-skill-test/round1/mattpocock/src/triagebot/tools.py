"""Tool Context — the facts TriageBot gathers about a Ticket before anything classifies it.

Two lookups, both backed by local JSON fixtures, both taking their arguments from validated
Ticket fields only (ADR-0003). An order we cannot find is an ordinary answer, not an exception:
customers cite wrong order numbers every day.
"""

from __future__ import annotations

import json
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel, Field, TypeAdapter

from triagebot.models import STRICT_MODEL, Action, Category, Money, Ticket

_FIXTURES = Path(__file__).parent / "fixtures"


class OrderState(str, Enum):
    """Where an order has got to in fulfilment."""

    PROCESSING = "PROCESSING"
    SHIPPED = "SHIPPED"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


class OrderRecord(BaseModel):
    """One order, as the order system knows it."""

    model_config = STRICT_MODEL

    order_id: str = Field(min_length=1, max_length=64)
    customer_id: str = Field(min_length=1, max_length=64)
    state: OrderState
    placed_on: str = Field(min_length=1, max_length=32)
    total: Money
    days_since_delivery: int | None = Field(default=None, ge=0)


class OrderLookup(BaseModel):
    """The answer to "what do we know about this order?" — including "nothing"."""

    model_config = STRICT_MODEL

    order_id: str = Field(min_length=1, max_length=64)
    found: bool
    record: OrderRecord | None = None


class PolicyEntry(BaseModel):
    """One row of the refund policy: the single Action a Category permits."""

    model_config = STRICT_MODEL

    category: Category
    refundable: bool
    window_days: int = Field(ge=0)
    prescribed_action: Action
    summary: str = Field(min_length=1, max_length=500)


def _policy_for(entries: tuple[PolicyEntry, ...], category: Category) -> PolicyEntry:
    """Find the one Policy Entry governing `category`, or say plainly that there isn't one."""
    for entry in entries:
        if entry.category is category:
            return entry
    raise KeyError(f"no Policy Entry for {category.value}")


class ToolContext(BaseModel):
    """Read-only facts gathered at enrichment, fetched once per Ticket."""

    model_config = STRICT_MODEL

    order: OrderLookup | None = None
    policies: tuple[PolicyEntry, ...] = ()

    def policy_for(self, category: Category) -> PolicyEntry:
        return _policy_for(self.policies, category)


class Tools(Protocol):
    """The lookups available during enrichment. SDK-shaped: one function per operation."""

    def get_order_status(self, order_id: str) -> OrderLookup: ...

    def get_refund_policy(self, category: Category) -> PolicyEntry: ...


_ORDERS = TypeAdapter(tuple[OrderRecord, ...])
_POLICIES = TypeAdapter(tuple[PolicyEntry, ...])


@lru_cache(maxsize=8)
def _load(directory: Path) -> tuple[dict[str, OrderRecord], tuple[PolicyEntry, ...]]:
    orders = _ORDERS.validate_python(json.loads((directory / "orders.json").read_text("utf-8")))
    policies = _POLICIES.validate_python(
        json.loads((directory / "refund_policy.json").read_text("utf-8"))
    )
    return {order.order_id: order for order in orders}, policies


class FixtureTools:
    """The shipped Tools adapter: local JSON, no network, ever."""

    def __init__(self, directory: Path | None = None) -> None:
        self._orders, self._policies = _load(directory or _FIXTURES)

    def get_order_status(self, order_id: str) -> OrderLookup:
        record = self._orders.get(order_id)
        return OrderLookup(order_id=order_id, found=record is not None, record=record)

    def get_refund_policy(self, category: Category) -> PolicyEntry:
        return _policy_for(self._policies, category)


def gather_context(ticket: Ticket, tools: Tools) -> ToolContext:
    """Fetch every fact we hold about this Ticket, exactly once.

    Arguments come from validated Ticket fields and the Category enum — never from body text.
    """
    order = tools.get_order_status(ticket.order_id) if ticket.order_id else None
    policies = tuple(tools.get_refund_policy(category) for category in Category)
    return ToolContext(order=order, policies=policies)
