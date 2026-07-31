"""Deterministic guards: the part of the system that actually decides.

Every function here is pure — no I/O, no clock, no state — so each guard can be
tested on its own without constructing an engine. That is deliberate: these are
the rules a reviewer needs to be able to read and check by eye.

All thresholds live at the top of this module and nowhere else.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from triagebot.models import Category, GuardCode, Language, Priority, Sentiment
from triagebot.states import TriageState
from triagebot.tools import RefundPolicy

# --- thresholds (single source of truth) -------------------------------------

AMOUNT_ESCALATION_THRESHOLD = Decimal("1000.00")
"""Strictly above this amount, a human must look at the ticket."""

CONFIDENCE_THRESHOLD = 0.6
"""Strictly below this confidence, the suggestion is not trusted."""

MAX_RETRIES = 1
"""How many times the engine may re-ask the driver with richer tool context."""

UNSUPPORTED_LANGUAGE_CONFIDENCE_CAP = 0.5
"""Confidence ceiling for languages this system does not claim to handle."""

ESCALATING_GUARDS: frozenset[GuardCode] = frozenset(
    {
        GuardCode.AMOUNT_THRESHOLD,
        GuardCode.LOW_CONFIDENCE,
        GuardCode.PROMPT_INJECTION,
        GuardCode.P0_ALWAYS_HUMAN,
        GuardCode.MISSING_ORDER_EVIDENCE,
        GuardCode.REFUND_POLICY_MISSING,
    }
)
"""Guards whose presence forces a human hand-off, whatever else is true."""

EVIDENCE_REQUIRING_CATEGORIES: frozenset[Category] = frozenset(
    {Category.REFUND, Category.BILLING}
)

# --- signal vocabularies used by priority derivation -------------------------

OUTAGE_SIGNALS = (
    "is down", "service unavailable", "outage", "503", "cannot access",
    "can't access", "宕机", "无法访问", "服务不可用", "系统崩溃",
)
BLOCKING_SIGNALS = (
    "payment failed", "cannot pay", "can't pay", "locked out", "can't log in",
    "cannot log in", "unable to log in", "付款失败", "扣款失败", "登录不了",
    "无法登录", "无法付款",
)
INQUIRY_SIGNALS = (
    "how do i", "how can i", "suggestion", "feature request", "just wondering",
    "请问", "咨询", "建议",
)


def _mentions(text: str, signals: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(signal in lowered for signal in signals)


# --- individual guards -------------------------------------------------------


def amount_guard(amount: Decimal | None) -> GuardCode | None:
    """Tickets disputing more than the threshold always go to a human.

    Boundary is strict: exactly at the threshold does *not* escalate.
    """
    if amount is not None and amount > AMOUNT_ESCALATION_THRESHOLD:
        return GuardCode.AMOUNT_THRESHOLD
    return None


def confidence_guard(confidence: float) -> GuardCode | None:
    """Trip when the (post-retry) confidence is below the trust threshold."""
    if confidence < CONFIDENCE_THRESHOLD:
        return GuardCode.LOW_CONFIDENCE
    return None


def language_guard(
    language: Language, category: Category, confidence: float
) -> tuple[Category, float, GuardCode | None]:
    """Force unsupported languages to OTHER and cap their confidence.

    The cap is a ceiling, never a floor: a suggestion that was already less
    confident stays where it is.
    """
    if language is Language.OTHER:
        return (
            Category.OTHER,
            min(confidence, UNSUPPORTED_LANGUAGE_CONFIDENCE_CAP),
            GuardCode.UNSUPPORTED_LANGUAGE,
        )
    return category, confidence, None


def refund_policy_guard(
    category: Category, suggested_action: str, policy: RefundPolicy | None
) -> tuple[str, GuardCode | None]:
    """Make refund advice match written policy, never the model's invention.

    Returns the action that will actually be used. For REFUND tickets that is
    always the policy's canonical action; a model that proposed something else
    is silently corrected and the override is recorded.
    """
    if category is not Category.REFUND:
        return suggested_action, None
    if policy is None:
        return suggested_action, GuardCode.REFUND_POLICY_MISSING
    if suggested_action.strip() == policy.canonical_action.strip():
        return policy.canonical_action, None
    return policy.canonical_action, GuardCode.REFUND_POLICY_OVERRIDE


def order_evidence_guard(
    category: Category, order_lookup_attempted: bool, order_found: bool
) -> GuardCode | None:
    """Escalate money-related tickets whose referenced order does not exist.

    A ticket with no order id at all was never looked up, so it is not
    *missing* evidence — it simply never claimed any.
    """
    if not order_lookup_attempted or order_found:
        return None
    if category in EVIDENCE_REQUIRING_CATEGORIES:
        return GuardCode.MISSING_ORDER_EVIDENCE
    return None


# --- priority ----------------------------------------------------------------

_BUMP_ONE_TIER: dict[Priority, Priority] = {
    Priority.P3: Priority.P2,
    Priority.P2: Priority.P1,
}


def derive_priority(
    category: Category,
    amount: Decimal | None,
    sentiment: Sentiment,
    injection_detected: bool,
    text: str,
) -> Priority:
    """Derive priority from facts alone. The model's opinion is not an input.

    Order matters. The P0 override runs last precisely so that nothing before it
    can dilute a security or availability judgement.
    """
    # 1. Baseline.
    if category is Category.OTHER or _mentions(text, INQUIRY_SIGNALS):
        priority = Priority.P3
    else:
        priority = Priority.P2

    # 2. Blocking a core operation, or a large sum at stake.
    blocks_core_operation = category in {
        Category.BILLING,
        Category.ACCOUNT,
        Category.TECHNICAL,
    } and _mentions(text, BLOCKING_SIGNALS)
    large_amount = amount is not None and amount > AMOUNT_ESCALATION_THRESHOLD
    if blocks_core_operation or large_amount:
        priority = Priority.P1

    # 3. Anger raises urgency by one tier, but cannot reach P0.
    if sentiment is Sentiment.ANGRY:
        priority = _BUMP_ONE_TIER.get(priority, priority)

    # 4. P0 override — last, and not reachable by any of the steps above.
    is_outage = category is Category.TECHNICAL and _mentions(text, OUTAGE_SIGNALS)
    if injection_detected or is_outage:
        return Priority.P0

    return priority


# --- terminal-state admission ------------------------------------------------


def decide_final_state(
    guards: Sequence[GuardCode],
    confidence: float,
    priority: Priority,
    category: Category,
) -> TriageState:
    """Admit a ticket to AUTO_RESOLVED only when all four conditions hold."""
    if any(guard in ESCALATING_GUARDS for guard in guards):
        return TriageState.ESCALATED
    if confidence < CONFIDENCE_THRESHOLD:
        return TriageState.ESCALATED
    if priority is Priority.P0:
        return TriageState.ESCALATED
    if category is Category.OTHER:
        return TriageState.ESCALATED
    return TriageState.AUTO_RESOLVED
