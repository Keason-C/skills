"""Triage orchestration -- the only module that imports both drivers and guards.

Flow, expressed as the state machine (FR-022):

    NEW --enrich--> ENRICHED --classify(+retry)--> CLASSIFIED --guards--> AUTO_RESOLVED
                                                                        \\-> ESCALATED

Two design points worth stating explicitly:

**Enrichment gathers everything, unconditionally.** ``enrich`` fetches the refund policy for
every ticket, not only ones the classifier later calls a refund. The obvious alternative --
"fetch the policy when the proposal says REFUND" -- is circular: enrichment happens *before*
classification, so at that moment there is no proposal. Fetching unconditionally keeps
ENRICHED meaning what it says: all context is gathered. (Caught in cross-artifact analysis,
finding F1.)

**The retry lives here, not in a guard.** ``guards.confidence`` decides *whether* a retry is
warranted; performing it is I/O, and guards must stay pure (research R2).
"""

from __future__ import annotations

from datetime import date

from .drivers import LLMDriver
from .guards import (
    apply_guards,
    detect_language,
    language_guard,
    needs_retry,
    neutralize,
    scan_for_injection,
)
from .models import (
    Category,
    ClassificationProposal,
    GuardFinding,
    OrderFound,
    OrderNotFound,
    PolicyFound,
    Ticket,
    ToolContext,
    TriageResult,
    TriageState,
)
from .settings import TriageSettings
from .states import StateMachine
from .tools.orders import get_order_status
from .tools.policies import get_refund_policy

__all__ = ["triage", "enrich"]


def enrich(ticket: Ticket, *, as_of: date) -> ToolContext:
    """Gather every piece of context the guards could need (FR-005, FR-007, FR-017).

    Runs before any driver call, so the injection scan -- the security boundary -- is never
    downstream of the probabilistic component.
    """
    injection = scan_for_injection(ticket.subject, ticket.body)
    language = detect_language(f"{ticket.subject}\n{ticket.body}")

    order = None
    if ticket.order_id is not None:
        order = get_order_status(ticket.order_id, as_of=as_of)

    # Fetched unconditionally; see the module docstring.
    policy = get_refund_policy(Category.REFUND)

    return ToolContext(order=order, policy=policy, injection=injection, language=language)


def _classify_once(
    driver: LLMDriver,
    ticket_for_driver: Ticket,
    context: ToolContext | None,
    language_of_ticket: "object",
    settings: TriageSettings,
) -> tuple[ClassificationProposal, GuardFinding | None]:
    """One classifier call plus the unsupported-language cap (FR-032)."""
    proposal = driver.classify(ticket_for_driver, context)
    return language_guard(proposal, language_of_ticket, settings)  # type: ignore[arg-type]


def _build_rationale(
    ticket: Ticket,
    context: ToolContext,
    verdict_findings: tuple[GuardFinding, ...],
    category: Category,
    action: str,
    proposal_reasoning: str,
) -> str:
    parts = [
        f"Classified as {category.value}; recommended action {action}.",
        f"Classifier reasoning: {proposal_reasoning}",
    ]

    order = context.order
    if isinstance(order, OrderNotFound):
        parts.append(
            f"Order {order.order_id} was not found in the order system; triage continued "
            "without order context."
        )
    elif isinstance(order, OrderFound):
        detail = f"Order {order.order_id} is {order.state.value}"
        if order.days_since_delivery is not None:
            detail += f", delivered {order.days_since_delivery} day(s) ago"
        parts.append(detail + ".")

    if isinstance(context.policy, PolicyFound) and category is Category.REFUND:
        parts.append(f"Refund policy applied: {context.policy.summary}")

    if verdict_findings:
        parts.append("Deterministic rules that fired:")
        parts.extend(f"- [{f.rule.value}] {f.detail}" for f in verdict_findings)
    else:
        parts.append("No deterministic rule overrode the classification.")

    return "\n".join(parts)


def triage(
    ticket: Ticket,
    driver: LLMDriver | None = None,
    settings: TriageSettings | None = None,
    *,
    as_of: date | None = None,
) -> TriageResult:
    """Turn a ticket into an authoritative decision.

    ``as_of`` is the reference date for refund-window arithmetic. It defaults to today --
    the single clock read in the entire system, deliberately placed at the outermost edge so
    that every layer beneath it is a pure function of its inputs. Tests always pass it
    explicitly, which is what makes SC-004 (identical re-runs) checkable.
    """
    if driver is None:
        from .drivers.mock import MockDriver

        driver = MockDriver()
    settings = settings or TriageSettings()
    as_of = as_of or date.today()

    machine = StateMachine()

    # --- NEW -> ENRICHED ---------------------------------------------------------------
    context = enrich(ticket, as_of=as_of)
    machine.advance(TriageState.ENRICHED)

    # The driver never sees raw attacker text: sentences containing an injection signature
    # are redacted from the copy handed over (FR-018). The original `ticket` -- exactly what
    # the customer wrote -- is untouched and remains the audit record.
    if context.injection.detected:
        safe_subject, safe_body = neutralize(ticket.subject, ticket.body)
        ticket_for_driver = ticket.with_text(subject=safe_subject, body=safe_body)
    else:
        ticket_for_driver = ticket

    # --- ENRICHED -> CLASSIFIED --------------------------------------------------------
    language_findings: list[GuardFinding] = []
    proposal, lang_finding = _classify_once(
        driver, ticket_for_driver, None, context.language, settings
    )
    if lang_finding is not None:
        language_findings.append(lang_finding)
    llm_calls = 1
    retried = False

    if needs_retry(proposal, settings) and llm_calls < settings.max_llm_calls:
        proposal, lang_finding = _classify_once(
            driver, ticket_for_driver, context, context.language, settings
        )
        llm_calls += 1
        retried = True
        if lang_finding is not None:
            language_findings.append(lang_finding)

    machine.advance(TriageState.CLASSIFIED)

    # --- CLASSIFIED -> terminal --------------------------------------------------------
    verdict = apply_guards(ticket, context, proposal, settings, retried=retried)
    findings = tuple(language_findings) + verdict.findings

    final_state = (
        TriageState.ESCALATED if verdict.escalated_to_human else TriageState.AUTO_RESOLVED
    )
    machine.advance(final_state)

    rationale = _build_rationale(
        ticket,
        context,
        findings,
        verdict.category,
        verdict.recommended_action.value,
        proposal.reasoning,
    )

    return TriageResult(
        ticket_id=ticket.id,
        category=verdict.category,
        priority=verdict.priority,
        sentiment=verdict.sentiment,
        confidence=verdict.confidence,
        recommended_action=verdict.recommended_action,
        escalated_to_human=verdict.escalated_to_human,
        rationale=rationale,
        injection_detected=verdict.injection_detected,
        language=context.language,
        state=final_state,
        state_path=machine.path,
        guard_findings=findings,
        retried=retried,
        llm_calls=llm_calls,
    )
