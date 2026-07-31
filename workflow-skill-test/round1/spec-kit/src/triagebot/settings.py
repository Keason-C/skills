"""Tunable thresholds (task T006).

Every threshold in the system lives here and nowhere else. The constitution forbids reading
them from module-level mutable globals, so this object is frozen and injected.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import Field

from .models import MAX_BODY_LENGTH, StrictModel


class TriageSettings(StrictModel):
    """Thresholds governing the deterministic guards.

    Defaults are the values the product owner fixed during clarification
    (spec.md -> Clarifications, session 2026-07-31).
    """

    #: Strictly greater than this escalates; exactly this does not (FR-012).
    amount_escalation_threshold: Decimal = Decimal("1000")

    #: Below this triggers one retry; at or above is sufficient (FR-013, FR-014).
    confidence_threshold: Annotated[float, Field(ge=0.0, le=1.0)] = 0.60

    #: Hard ceiling on classifier calls per ticket (FR-013, SC-003a).
    max_llm_calls: Annotated[int, Field(ge=1, le=2)] = 2

    #: Confidence ceiling for tickets in an unsupported language (FR-032).
    unsupported_language_confidence_cap: Annotated[float, Field(ge=0.0, le=1.0)] = 0.5

    #: Mirrors the ``Ticket.body`` constraint; see ``models.MAX_BODY_LENGTH`` (FR-002).
    max_body_length: Annotated[int, Field(ge=1)] = MAX_BODY_LENGTH
