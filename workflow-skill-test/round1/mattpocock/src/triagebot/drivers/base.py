"""The Driver seam.

A Driver turns a Ticket into a Suggestion. That is the whole interface: one method, one return
type, no ability to request a tool call (ADR-0003). Two adapters ship — `MockDriver` and
`AnthropicDriver` — and the tests supply a third, which is what makes this a real seam rather
than a hypothetical one.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from triagebot.models import Suggestion, Ticket
from triagebot.tools import ToolContext


@runtime_checkable
class LLMDriver(Protocol):
    """Turns a Ticket into an unapproved Suggestion.

    `context` is `None` on the first pass and populated on the low-confidence retry
    (ADR-0002). Implementations must be total: they return a Suggestion for any accepted
    Ticket, including a hostile one, rather than raising.
    """

    def suggest(self, ticket: Ticket, context: ToolContext | None) -> Suggestion: ...
