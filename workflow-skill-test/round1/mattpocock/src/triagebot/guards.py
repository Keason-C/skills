"""The Guard chain: pure deterministic rules that overrule the Driver.

No Guard performs I/O — everything a Guard needs is on the Ticket, on the Suggestion, or in the
Tool Context gathered at enrichment. Escalation is monotonic: once a Guard sets it, nothing
clears it. `adjudicate` is the only place a Verdict is constructed (ADR-0001).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

from triagebot.models import (
    MONEY_MOVING_ACTIONS,
    Action,
    Category,
    Priority,
    Sentiment,
    Suggestion,
    Ticket,
    TriageResult,
)
from triagebot.injection import InjectionScan
from triagebot.stages import TriageStage, advance
from triagebot.tools import ToolContext

AMOUNT_THRESHOLD = Decimal("1000.00")
"""Disputes strictly above this reach a human (product decision P2)."""

EVIDENCE_DEPENDENT_CATEGORIES = frozenset({Category.REFUND, Category.BILLING})
"""Categories whose Verdict depends on an order we can actually see (product decision P8)."""

ANGER_SENSITIVE_CATEGORIES = frozenset({Category.REFUND, Category.BILLING})
"""Categories where an angry customer is a business risk, not just a tone (product decision P11).
Deliberately a separate constant from EVIDENCE_DEPENDENT_CATEGORIES: same members today, but two
unrelated reasons, and they will drift."""

ROUTINE_CATEGORIES = frozenset({Category.TECHNICAL, Category.ACCOUNT})
"""Categories whose ordinary Tickets sit at P2 (product decision P11)."""

CONFIDENCE_THRESHOLD = 0.6
"""Below this, the Driver is asked once more with the facts; still below, a human takes it
(product decision P3)."""


@dataclass(frozen=True, slots=True)
class Adjudication:
    """The working state of one Ticket's adjudication as it passes down the Guard chain."""

    ticket: Ticket
    context: ToolContext
    injection: InjectionScan
    category: Category
    sentiment: Sentiment
    confidence: float
    action: Action
    escalated: bool = False
    reasons: tuple[str, ...] = ()
    guards_fired: tuple[str, ...] = ()

    def record(self, guard: str, reason: str, **changes: object) -> Adjudication:
        """Record that `guard` acted, with its reason, applying any field changes."""
        return replace(
            self,
            guards_fired=self.guards_fired + (guard,),
            reasons=self.reasons + (reason,),
            **changes,  # type: ignore[arg-type]
        )

    def escalate(self, guard: str, reason: str, **changes: object) -> Adjudication:
        """Escalate. Monotonic — `escalated` only ever goes from False to True."""
        return self.record(guard, reason, escalated=True, **changes)


def injection_guard(state: Adjudication) -> Adjudication:
    """An Injection Attempt is a security event: flagged, escalated, and otherwise ignored.

    Note what this Guard does *not* do — it does not touch the Category, Sentiment or Action.
    The injected text was already redacted before the Driver saw it, so those fields were formed
    without it. That is what makes the attack inert rather than merely visible.
    """
    if not state.injection.detected:
        return state
    return state.escalate(
        "injection",
        "Instruction-like text aimed at the triage system was found in this ticket "
        f"({', '.join(state.injection.markers)}). It was removed before classification and "
        "played no part in this verdict; the ticket is routed to a human as a security event.",
    )


def amount_guard(state: Adjudication) -> Adjudication:
    """A dispute worth more than the threshold is never machine-decided."""
    amount = state.ticket.amount
    if amount is None or amount <= AMOUNT_THRESHOLD:
        return state
    return state.escalate(
        "amount",
        f"Disputed amount {amount} is above the {AMOUNT_THRESHOLD} threshold, "
        "so a human decides this one.",
    )


def refund_policy_guard(state: Adjudication) -> Adjudication:
    """On a REFUND Ticket the Action comes from the Policy Entry, never from the Driver."""
    if state.category is not Category.REFUND:
        return state

    policy = state.context.policy_for(Category.REFUND)
    if state.action is policy.prescribed_action:
        return state

    return state.record(
        "refund-policy",
        f"Refund policy prescribes {policy.prescribed_action.value} for a REFUND ticket, "
        f"replacing the suggested {state.action.value}. Policy: {policy.summary}",
        action=policy.prescribed_action,
    )


def unknown_order_guard(state: Adjudication) -> Adjudication:
    """An order we cannot find is missing evidence: no refund stands, and some Tickets escalate."""
    order = state.context.order
    if order is None or order.found:
        return state

    reason = (
        f"Cited order {order.order_id} is not in the order system, "
        "so we cannot verify what the customer is describing."
    )
    changes: dict[str, object] = {}
    if state.action in MONEY_MOVING_ACTIONS:
        changes["action"] = Action.REQUEST_MORE_INFO

    if state.category in EVIDENCE_DEPENDENT_CATEGORIES:
        return state.escalate("unknown-order", reason, **changes)
    return state.record("unknown-order", reason, **changes)


def refund_execution_guard(state: Adjudication) -> Adjudication:
    """Money never moves without a human — at any amount (product decision P6)."""
    if state.action not in MONEY_MOVING_ACTIONS:
        return state
    return state.escalate(
        "refund-execution",
        f"{state.action.value} is a money-moving action, which a human always executes.",
    )


def confidence_guard(state: Adjudication) -> Adjudication:
    """A Suggestion the Driver could not stand behind — even after the retry — goes to a human."""
    if state.confidence >= CONFIDENCE_THRESHOLD:
        return state
    return state.escalate(
        "confidence",
        f"Confidence {state.confidence} stayed below the {CONFIDENCE_THRESHOLD} threshold "
        "after a second look with the order and policy facts.",
    )


def escalation_consistency_guard(state: Adjudication) -> Adjudication:
    """An Action that asks for a human means the Ticket goes to one. The two never disagree."""
    if state.action is not Action.ESCALATE_TO_HUMAN or state.escalated:
        return state
    return state.escalate(
        "escalation-consistency",
        "The recommended action is to hand this to a human, so the ticket is escalated.",
    )


def auto_resolution_guard(state: Adjudication) -> Adjudication:
    """Auto-resolution is a privilege with four conditions; failing any of them means a human.

    The four (product decision P6) are: nothing overruled the Driver, confidence cleared the
    threshold, the Priority is not the top tier, and the Category is not OTHER. The first three
    are already true of any Ticket reaching here un-escalated, so this Guard exists for the
    fourth — "we don't know" is never closed by a machine.
    """
    if state.escalated or state.category is not Category.OTHER:
        return state
    return state.escalate(
        "auto-resolution",
        "Category OTHER means we could not tell what this ticket is about, "
        "so it is never closed without a human.",
    )


GUARD_CHAIN = (
    injection_guard,
    amount_guard,
    refund_policy_guard,
    unknown_order_guard,
    refund_execution_guard,
    confidence_guard,
    escalation_consistency_guard,
    auto_resolution_guard,
)
"""Order matters: the policy Guard may set a money-moving Action, and every Guard after it needs
to see the Action as rewritten rather than as suggested. The last two run once the rest have had
their say, because they react to the escalation state itself."""


def compute_priority(state: Adjudication) -> Priority:
    """The Priority the Verdict carries. Never the Driver's (product decision P11).

    An Injection Attempt is a security event and takes the top tier. Anything else that reaches a
    human is at least P1 — including a large dispute, which is deliberately *not* P0: a big
    number is not an outage.
    """
    if state.injection.detected:
        return Priority.P0_URGENT
    if state.escalated:
        return Priority.P1_HIGH
    if state.sentiment is Sentiment.ANGRY and state.category in ANGER_SENSITIVE_CATEGORIES:
        return Priority.P1_HIGH
    if state.category in ROUTINE_CATEGORIES:
        return Priority.P2_NORMAL
    return Priority.P3_LOW


def adjudicate(
    ticket: Ticket,
    suggestion: Suggestion,
    context: ToolContext,
    injection: InjectionScan,
) -> TriageResult:
    """Run the Guard chain over a Suggestion and return the Verdict it approves."""
    state = Adjudication(
        ticket=ticket,
        context=context,
        injection=injection,
        category=suggestion.category,
        sentiment=suggestion.sentiment,
        confidence=suggestion.confidence,
        action=suggestion.action,
    )
    for guard in GUARD_CHAIN:
        state = guard(state)

    terminal = TriageStage.ESCALATED if state.escalated else TriageStage.AUTO_RESOLVED
    rationale = " ".join((suggestion.rationale, *state.reasons))

    return TriageResult(
        ticket_id=ticket.id,
        category=state.category,
        priority=compute_priority(state),
        sentiment=state.sentiment,
        confidence=state.confidence,
        recommended_action=state.action,
        escalated_to_human=state.escalated,
        injection_detected=injection.detected,
        stage=advance(TriageStage.CLASSIFIED, terminal),
        rationale=rationale,
        guards_fired=state.guards_fired,
    )
