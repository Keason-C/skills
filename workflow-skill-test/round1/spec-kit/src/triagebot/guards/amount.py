"""Amount threshold guard (task T036, FR-012).

Comparison is on ``Decimal``, not ``float``: the boundary this rule is measured at is
exactly 1000.00 / 1000.01 (SC-001), which is precisely where binary floating point is least
trustworthy.
"""

from __future__ import annotations

from ..models import GuardFinding, GuardRule, Ticket
from ..settings import TriageSettings


def amount_guard(ticket: Ticket, settings: TriageSettings) -> GuardFinding | None:
    """Fire when the disputed amount is **strictly greater** than the threshold.

    Exactly at the threshold does not escalate -- the rule triggers on exceeding, not on
    reaching (spec.md -> Edge Cases).
    """
    if ticket.amount is None:
        return None
    if ticket.amount <= settings.amount_escalation_threshold:
        return None

    return GuardFinding(
        rule=GuardRule.AMOUNT_THRESHOLD,
        field="escalated_to_human",
        proposed="False",
        final="True",
        detail=(
            f"Disputed amount {ticket.amount} exceeds the escalation threshold "
            f"{settings.amount_escalation_threshold}; a human must decide regardless of "
            "how confident the classification is."
        ),
    )
