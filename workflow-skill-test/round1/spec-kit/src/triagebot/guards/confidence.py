"""Confidence guard (task T039, FR-013, FR-014, research R2).

These are *predicates*. Performing the retry is I/O -- it calls a driver -- so it lives in
``pipeline.py``. Keeping the decision separate from the action is what allows this module to
stay pure and lets every confidence case be tested with plain values and no fakes.
"""

from __future__ import annotations

from ..models import ClassificationProposal, GuardFinding, GuardRule
from ..settings import TriageSettings


def needs_retry(proposal: ClassificationProposal, settings: TriageSettings) -> bool:
    """True when the proposal is below the confidence threshold (FR-013).

    Exactly at the threshold is sufficient, so no retry (spec.md -> Edge Cases).
    """
    return proposal.confidence < settings.confidence_threshold


def confidence_guard(
    proposal: ClassificationProposal,
    settings: TriageSettings,
    *,
    retried: bool,
) -> GuardFinding | None:
    """Fire when confidence is still short after the retry budget is spent (FR-014)."""
    if proposal.confidence >= settings.confidence_threshold:
        return None
    if not retried:
        # Still below threshold but the retry has not happened yet; the pipeline will
        # retry rather than escalate. Nothing to record.
        return None

    return GuardFinding(
        rule=GuardRule.LOW_CONFIDENCE,
        field="escalated_to_human",
        proposed="False",
        final="True",
        detail=(
            f"Confidence {proposal.confidence:.2f} remains below the threshold "
            f"{settings.confidence_threshold:.2f} after one retry with tool context; "
            "escalating rather than guessing."
        ),
    )
