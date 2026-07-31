"""The triage engine: orchestration only.

This module makes no judgements of its own. It walks the state machine, calls
the driver, calls the tools, and then asks ``guards.py`` what to do. If you want
to know *why* a ticket came out the way it did, read ``guards.py``; this file
only decides what order to ask the questions in.
"""

from __future__ import annotations

from triagebot import guards
from triagebot.drivers.base import LLMDriver, ToolContext
from triagebot.guards import (
    amount_guard,
    confidence_guard,
    decide_final_state,
    derive_priority,
    language_guard,
    order_evidence_guard,
    refund_policy_guard,
)
from triagebot.models import (
    Category,
    GuardCode,
    Language,
    LLMSuggestion,
    Priority,
    Ticket,
    TicketView,
    TriageResult,
)
from triagebot.sanitize import detect_injection, detect_language, redact_injection
from triagebot.states import TriageState, TriageStateMachine
from triagebot.tools import OrderStatus, RefundPolicy, ToolBox

_GUARD_EXPLANATIONS: dict[GuardCode, str] = {
    GuardCode.AMOUNT_THRESHOLD: (
        f"Disputed amount exceeds the {guards.AMOUNT_ESCALATION_THRESHOLD} USD "
        "auto-handling threshold, so a human must review it."
    ),
    GuardCode.LOW_CONFIDENCE: (
        f"Confidence stayed below {guards.CONFIDENCE_THRESHOLD} even after retrying "
        "with fuller tool context."
    ),
    GuardCode.PROMPT_INJECTION: (
        "The ticket text contains prompt-injection markers; the injected span was "
        "redacted before classification and a human is being asked to look."
    ),
    GuardCode.P0_ALWAYS_HUMAN: "P0 tickets always go to a human.",
    GuardCode.MISSING_ORDER_EVIDENCE: (
        "order not found: the referenced order does not exist, so the money claim "
        "cannot be verified automatically."
    ),
    GuardCode.UNSUPPORTED_LANGUAGE: (
        "The ticket is not in a supported language (en/zh), so it was filed as OTHER "
        "with capped confidence."
    ),
    GuardCode.REFUND_POLICY_OVERRIDE: (
        "recommended_action was overridden by refund policy / 建议动作已被退款政策覆盖."
    ),
    GuardCode.REFUND_POLICY_MISSING: (
        "No refund policy entry was found, so the refund cannot be actioned automatically."
    ),
}


class TriageEngine:
    """Runs one ticket through the triage lifecycle."""

    def __init__(self, driver: LLMDriver, toolbox: ToolBox | None = None) -> None:
        self._driver = driver
        self._toolbox = toolbox or ToolBox()
        self._last_history: tuple[TriageState, ...] = ()

    @property
    def last_history(self) -> tuple[TriageState, ...]:
        """States visited during the most recent :meth:`triage` call."""
        return self._last_history

    def triage(self, ticket: Ticket) -> TriageResult:
        machine = TriageStateMachine()

        # --- NEW: sanitise before anything else looks at the text ------------
        raw_text = f"{ticket.subject}\n{ticket.body}"
        injection_hits = detect_injection(raw_text)
        injection_detected = bool(injection_hits)
        redacted_subject = redact_injection(ticket.subject)
        redacted_body = redact_injection(ticket.body)
        language = detect_language(f"{redacted_subject}\n{redacted_body}")

        # --- ENRICHED: fetch tool facts --------------------------------------
        order: OrderStatus | None = None
        order_lookup_attempted = False
        if ticket.order_id is not None:
            order_lookup_attempted = True
            order = self._toolbox.get_order_status(ticket.order_id)
        machine.transition_to(TriageState.ENRICHED)

        view = TicketView(
            ticket_id=ticket.id,
            subject=redacted_subject,
            redacted_body=redacted_body,
            language=language,
            amount=ticket.amount,
            order_id=ticket.order_id,
        )

        # --- classification, with at most one richer-context retry ------------
        guard_codes: list[GuardCode] = []
        first_context = ToolContext(
            order=order, order_lookup_attempted=order_lookup_attempted
        )
        suggestion = self._driver.classify(view, first_context)
        category, confidence, language_code = self._apply_language_guard(language, suggestion)
        policy: RefundPolicy | None = None

        if confidence_guard(confidence) is not None:
            for _attempt in range(guards.MAX_RETRIES):
                policy = self._toolbox.get_refund_policy(category)
                retry_context = ToolContext(
                    order=order,
                    order_lookup_attempted=order_lookup_attempted,
                    refund_policy=policy,
                    is_retry=True,
                )
                suggestion = self._driver.classify(view, retry_context)
                category, confidence, language_code = self._apply_language_guard(
                    language, suggestion
                )

        if language_code is not None:
            guard_codes.append(language_code)

        machine.transition_to(TriageState.CLASSIFIED)

        # --- deterministic adjudication --------------------------------------
        # The policy fetched during a retry belongs to the category the driver
        # proposed *at that time*. A retry may have changed its mind, so the
        # policy is re-fetched for the category we actually ended up with —
        # never assume the cached one still matches.
        if policy is None or policy.category is not category:
            policy = self._toolbox.get_refund_policy(category)
        recommended_action, policy_code = refund_policy_guard(
            category, suggestion.suggested_action, policy
        )
        if policy_code is not None:
            guard_codes.append(policy_code)

        priority = derive_priority(
            category=category,
            amount=ticket.amount,
            sentiment=suggestion.sentiment,
            injection_detected=injection_detected,
            text=f"{redacted_subject}\n{redacted_body}",
        )

        if injection_detected:
            guard_codes.append(GuardCode.PROMPT_INJECTION)
        if priority is Priority.P0:
            guard_codes.append(GuardCode.P0_ALWAYS_HUMAN)

        amount_code = amount_guard(ticket.amount)
        if amount_code is not None:
            guard_codes.append(amount_code)

        confidence_code = confidence_guard(confidence)
        if confidence_code is not None:
            guard_codes.append(confidence_code)

        evidence_code = order_evidence_guard(
            category, order_lookup_attempted, order is not None
        )
        if evidence_code is not None:
            guard_codes.append(evidence_code)

        # --- terminal state ---------------------------------------------------
        final_state = decide_final_state(guard_codes, confidence, priority, category)
        machine.transition_to(final_state)
        self._last_history = machine.history

        return TriageResult(
            ticket_id=ticket.id,
            category=category,
            priority=priority,
            sentiment=suggestion.sentiment,
            confidence=confidence,
            recommended_action=recommended_action,
            escalated_to_human=final_state is TriageState.ESCALATED,
            rationale=self._build_rationale(suggestion, guard_codes, injection_hits, order),
            final_state=final_state,
            guards_triggered=tuple(dict.fromkeys(guard_codes)),
            injection_detected=injection_detected,
            language=language,
        )

    @staticmethod
    def _apply_language_guard(
        language: Language, suggestion: LLMSuggestion
    ) -> tuple[Category, float, GuardCode | None]:
        return language_guard(language, suggestion.category, suggestion.confidence)

    @staticmethod
    def _build_rationale(
        suggestion: LLMSuggestion,
        guard_codes: list[GuardCode],
        injection_hits: tuple[str, ...],
        order: OrderStatus | None,
    ) -> str:
        parts = [f"Driver: {suggestion.rationale}"]
        if injection_hits:
            parts.append(f"Injection markers detected: {', '.join(injection_hits)}.")
        if order is not None:
            parts.append(f"Order {order.order_id} is {order.status}.")
        for code in dict.fromkeys(guard_codes):
            parts.append(f"[{code.value}] {_GUARD_EXPLANATIONS[code]}")
        rationale = " ".join(parts)
        return rationale[:4000]
