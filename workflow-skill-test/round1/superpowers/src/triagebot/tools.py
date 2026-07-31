"""Agent tools, backed by local JSON fixtures.

Security note: these are the only functions that turn a triage run into a
lookup, so they are the natural place for injection to try to escape. Both of
them re-validate their arguments at the entry point even though callers are
already type-checked — an ``order_id`` must match a strict alphanumeric pattern
and a category must be an actual ``Category`` member. Free-text from a ticket
body has no path into either argument.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

from triagebot.models import ORDER_ID_PATTERN, Category, StrictModel

_ORDER_ID_RE = re.compile(ORDER_ID_PATTERN)
DEFAULT_FIXTURES_DIR = Path(__file__).parent / "fixtures"


class InvalidToolArgumentError(Exception):
    """Raised when a tool is called with an argument it refuses to accept."""


class OrderStatus(StrictModel):
    order_id: str
    status: str
    total: Decimal
    placed_days_ago: int
    refundable: bool


class RefundPolicy(StrictModel):
    category: Category
    policy_id: str
    canonical_action: str
    window_days: int
    summary: str


class ToolBox:
    """The two tools available to the agent, loaded once per instance."""

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        directory = fixtures_dir or DEFAULT_FIXTURES_DIR
        orders = json.loads((directory / "orders.json").read_text(encoding="utf-8"))
        policies = json.loads((directory / "refund_policies.json").read_text(encoding="utf-8"))
        self._orders: dict[str, OrderStatus] = {
            row["order_id"]: OrderStatus(**row) for row in orders
        }
        self._policies: dict[Category, RefundPolicy] = {
            RefundPolicy(**row).category: RefundPolicy(**row) for row in policies
        }

    def get_order_status(self, order_id: str) -> OrderStatus | None:
        """Look up an order. Returns ``None`` when the order does not exist."""
        if not isinstance(order_id, str) or not _ORDER_ID_RE.match(order_id):
            raise InvalidToolArgumentError(
                f"order_id must match {ORDER_ID_PATTERN!r}; refusing to look up {order_id!r}"
            )
        return self._orders.get(order_id)

    def get_refund_policy(self, category: Category) -> RefundPolicy | None:
        """Look up the policy entry for a category. Every category has one."""
        if not isinstance(category, Category):
            raise InvalidToolArgumentError(
                f"category must be a Category member; refusing to look up {category!r}"
            )
        return self._policies.get(category)
