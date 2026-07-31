"""Priority derivation (task T029, FR-010b).

The signature carries **no proposal argument**. That is the point: adopting the classifier's
priority is not merely discouraged, it is impossible to express here. The classifier's
proposed priority still travels in ``ClassificationProposal`` for audit, and
``apply_guards`` records a finding when the two disagree (FR-010d).

The matrix is the product owner's, verbatim (spec.md -> Clarifications):

* injection detected                                   -> P0
* amount guard fired                                   -> at least P1
* escalated for any reason                             -> at least P1
* sentiment ANGRY and category REFUND or BILLING       -> at least P1
* category TECHNICAL or ACCOUNT, nothing above applied -> P2
* otherwise                                            -> P3

"At least P1" composes through ``most_severe`` rather than a chain of comparisons, so the
rules are order-independent -- a property the tests rely on.
"""

from __future__ import annotations

from ..models import Category, Priority, Sentiment, most_severe

_ANGRY_ESCALATING_CATEGORIES = frozenset({Category.REFUND, Category.BILLING})
_ELEVATED_CATEGORIES = frozenset({Category.TECHNICAL, Category.ACCOUNT})


def derive_priority(
    category: Category,
    sentiment: Sentiment,
    *,
    injection_detected: bool,
    amount_guard_fired: bool,
    escalated: bool,
) -> Priority:
    """Compute the authoritative priority from already-final values."""
    # A security event outranks everything else.
    if injection_detected:
        return Priority.P0

    priority = Priority.P3
    if category in _ELEVATED_CATEGORIES:
        priority = most_severe(priority, Priority.P2)
    if sentiment is Sentiment.ANGRY and category in _ANGRY_ESCALATING_CATEGORIES:
        priority = most_severe(priority, Priority.P1)
    if amount_guard_fired:
        priority = most_severe(priority, Priority.P1)
    if escalated:
        priority = most_severe(priority, Priority.P1)
    return priority
