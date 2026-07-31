"""Deterministic guards: the half of the system that actually decides.

`apply_guards` converts a *proposal* (which has no authority) into the authoritative
verdict. Every rule runs; none short-circuits, so a ticket that trips three rules reports
three findings rather than the first one (FR-020).

This package imports ``models``, ``settings``, and ``states`` -- never ``drivers``. That
one-way dependency is what keeps the guards pure, and it is asserted by
``tests/test_layering.py``.

Rule order matters in exactly one place: the refund policy guard must settle the action
*before* the terminal-action guard inspects it, otherwise the terminal check would run
against the classifier's suggestion rather than the policy-corrected one.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..models import (
    ActionKind,
    Category,
    ClassificationProposal,
    GuardFinding,
    GuardRule,
    Priority,
    Sentiment,
    Ticket,
    ToolContext,
)
from ..settings import TriageSettings
from .amount import amount_guard
from .confidence import confidence_guard, needs_retry
from .injection import neutralize, scan_for_injection
from .language import detect_language, language_guard
from .priority import derive_priority
from .refund import refund_policy_guard, terminal_action_guard

__all__ = [
    "GuardVerdict",
    "apply_guards",
    "amount_guard",
    "confidence_guard",
    "needs_retry",
    "derive_priority",
    "detect_language",
    "language_guard",
    "neutralize",
    "refund_policy_guard",
    "scan_for_injection",
    "terminal_action_guard",
]


@dataclass(frozen=True, slots=True)
class GuardVerdict:
    """The deterministic outcome for a ticket, before it is wrapped in a `TriageResult`."""

    category: Category
    priority: Priority
    sentiment: Sentiment
    confidence: float
    recommended_action: ActionKind
    escalated_to_human: bool
    injection_detected: bool
    findings: tuple[GuardFinding, ...]


def apply_guards(
    ticket: Ticket,
    context: ToolContext,
    proposal: ClassificationProposal,
    settings: TriageSettings,
    *,
    retried: bool,
) -> GuardVerdict:
    """Run every deterministic rule over a proposal and return the binding verdict."""
    findings: list[GuardFinding] = []
    escalate = False

    category = proposal.category
    sentiment = proposal.sentiment
    action = proposal.suggested_action

    # --- 1. Prompt injection (FR-017, FR-019) -----------------------------------------
    # Feeds only the escalation verdict and the P0 rule. It contributes nothing to the
    # category or the action, which is half of why FR-018 holds; the other half is that the
    # driver never saw the injected text (see guards.injection.neutralize).
    injection_detected = context.injection.detected
    if injection_detected:
        escalate = True
        findings.append(
            GuardFinding(
                rule=GuardRule.PROMPT_INJECTION,
                field="escalated_to_human",
                proposed="False",
                final="True",
                detail=(
                    "Ticket text contains a suspected instruction-override attempt "
                    f"({', '.join(context.injection.signatures)}). The text was withheld "
                    "from the classifier and the ticket is escalated as a security event."
                ),
            )
        )

    # --- 2. Amount threshold (FR-012) --------------------------------------------------
    amount_finding = amount_guard(ticket, settings)
    amount_fired = amount_finding is not None
    if amount_finding is not None:
        escalate = True
        findings.append(amount_finding)

    # --- 3. Confidence (FR-014) --------------------------------------------------------
    conf_finding = confidence_guard(proposal, settings, retried=retried)
    if conf_finding is not None:
        escalate = True
        findings.append(conf_finding)

    # --- 4. Refund policy (FR-015, FR-016, FR-016a) ------------------------------------
    action, refund_findings = refund_policy_guard(context, proposal, category)
    for finding in refund_findings:
        findings.append(finding)
        if finding.field == "escalated_to_human":
            escalate = True

    # --- 5. Terminal action (FR-016b) --------------------------------------------------
    # Runs after the policy guard so it inspects the corrected action, not the suggestion.
    terminal_finding = terminal_action_guard(action)
    if terminal_finding is not None:
        escalate = True
        findings.append(terminal_finding)

    # --- 6. Priority derivation (FR-010b, FR-010d) -------------------------------------
    priority = derive_priority(
        category,
        sentiment,
        injection_detected=injection_detected,
        amount_guard_fired=amount_fired,
        escalated=escalate,
    )
    if priority is not proposal.priority:
        findings.append(
            GuardFinding(
                rule=GuardRule.PRIORITY_DERIVATION,
                field="priority",
                proposed=proposal.priority.value,
                final=priority.value,
                detail=(
                    "Priority is derived from the ticket, not adopted from the "
                    f"classifier: it proposed {proposal.priority.value}, the derivation "
                    f"matrix yields {priority.value}."
                ),
            )
        )

    return GuardVerdict(
        category=category,
        priority=priority,
        sentiment=sentiment,
        confidence=proposal.confidence,
        recommended_action=action,
        escalated_to_human=escalate,
        injection_detected=injection_detected,
        findings=tuple(findings),
    )
