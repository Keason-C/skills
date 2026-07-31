"""LLM drivers: the probabilistic half of the system (task T019).

A driver's *only* output is a `ClassificationProposal`, and a proposal has no authority
(FR-009). Nothing a driver returns is trusted: the guards revalidate and may override every
field. That is what makes it safe to swap a keyword mock for a frontier model without
re-reasoning about correctness.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ..models import ClassificationProposal, Ticket, ToolContext

__all__ = ["LLMDriver", "MockDriver", "AnthropicDriver"]


@runtime_checkable
class LLMDriver(Protocol):
    """What the pipeline requires of a classifier."""

    def classify(
        self,
        ticket: Ticket,
        context: ToolContext | None = None,
    ) -> ClassificationProposal:
        """Propose a classification.

        ``context`` is ``None`` on the first call and populated on the retry (FR-013), which
        is what gives the retry a reason to reach a different answer.

        The ``ticket`` handed to a driver may be a *neutralised copy* whose injected
        sentences have been redacted; drivers must never be given raw attacker text.
        """
        ...


def __getattr__(name: str) -> object:
    """Lazily expose the concrete drivers.

    ``AnthropicDriver`` lives behind this so that importing ``triagebot.drivers`` never
    pulls in the optional ``anthropic`` SDK -- the constitution forbids the core import
    graph from depending on an LLM SDK.
    """
    if name == "MockDriver":
        from .mock import MockDriver

        return MockDriver
    if name == "AnthropicDriver":
        from .anthropic_driver import AnthropicDriver

        return AnthropicDriver
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
