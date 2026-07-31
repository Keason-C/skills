"""The LLM driver boundary.

A driver's whole job is *understanding*: given a redacted ticket view and the
facts the tools returned, propose a classification. It is structurally unable to
decide anything — its return type is ``LLMSuggestion``, and nothing downstream
copies a suggestion into a result without passing it through ``guards.py``.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from triagebot.models import LLMSuggestion, StrictModel, TicketView
from triagebot.tools import OrderStatus, RefundPolicy


class ToolContext(StrictModel):
    """The tool facts handed to a driver for one classification attempt."""

    order: OrderStatus | None = None
    order_lookup_attempted: bool = False
    refund_policy: RefundPolicy | None = None
    is_retry: bool = False

    @property
    def has_new_evidence(self) -> bool:
        """True when the tools actually produced a fact the driver can use."""
        return self.order is not None or self.refund_policy is not None


@runtime_checkable
class LLMDriver(Protocol):
    """Anything that can turn a redacted ticket view into a suggestion."""

    def classify(self, view: TicketView, context: ToolContext) -> LLMSuggestion:
        """Propose a classification. Never authoritative."""
        ...
