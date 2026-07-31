"""TriageBot -- customer support ticket triage.

The design thesis in one line: **the LLM understands, deterministic code decides.**

A driver reads a ticket and returns a `ClassificationProposal`, which carries no authority.
A layer of pure guards then produces the `TriageResult`, overriding whatever it disagrees
with and recording each override as a `GuardFinding`. Correctness claims are made about the
guards, never about the model.

    >>> from triagebot import Ticket, triage
    >>> result = triage(Ticket(id="T-1", customer_id="C-1",
    ...                        subject="Cannot log in", body="Password reset fails."))
    >>> result.escalated_to_human
    False
"""

from __future__ import annotations

from .errors import DriverError, IllegalTransitionError, TriageError
from .models import (
    TERMINAL_ACTIONS,
    ActionKind,
    Category,
    ClassificationProposal,
    GuardFinding,
    GuardRule,
    InjectionScan,
    Language,
    OrderFound,
    OrderNotFound,
    OrderState,
    PolicyFound,
    PolicyNotFound,
    Priority,
    Sentiment,
    Ticket,
    ToolContext,
    TriageResult,
    TriageState,
)
from .pipeline import enrich, triage
from .settings import TriageSettings
from .states import LEGAL_TRANSITIONS, StateMachine

__version__ = "1.0.0"

__all__ = [
    "__version__",
    # entry points
    "triage",
    "enrich",
    # configuration
    "TriageSettings",
    # core models
    "Ticket",
    "TriageResult",
    "ClassificationProposal",
    "GuardFinding",
    "ToolContext",
    "InjectionScan",
    "OrderFound",
    "OrderNotFound",
    "PolicyFound",
    "PolicyNotFound",
    # enums
    "ActionKind",
    "Category",
    "GuardRule",
    "Language",
    "OrderState",
    "Priority",
    "Sentiment",
    "TriageState",
    "TERMINAL_ACTIONS",
    # state machine
    "StateMachine",
    "LEGAL_TRANSITIONS",
    # errors
    "TriageError",
    "IllegalTransitionError",
    "DriverError",
]
