"""A deterministic keyword-scoring driver.

Every test in this project uses this driver. It performs no I/O, consults no
clock, and uses no randomness, so the same input always produces byte-identical
output — which is what makes the guard tests meaningful assertions about the
guards rather than about a model's mood.
"""

from __future__ import annotations

from triagebot.drivers.base import ToolContext
from triagebot.models import Category, LLMSuggestion, Priority, Sentiment, TicketView

CATEGORY_KEYWORDS: dict[Category, tuple[str, ...]] = {
    Category.REFUND: (
        "refund", "money back", "return the", "reimburse",
        "退款", "退货", "退钱",
    ),
    Category.BILLING: (
        "invoice", "charged", "charge", "payment failed", "billing",
        "overcharg", "subscription", "double charge",
        "账单", "扣款", "付款失败", "收费", "发票",
    ),
    Category.TECHNICAL: (
        "crash", "error", "bug", "not working", "broken", "500", "503",
        "is down", "unavailable", "cannot access",
        "报错", "崩溃", "无法访问", "宕机", "打不开",
    ),
    Category.ACCOUNT: (
        "password", "log in", "login", "locked out", "account", "sign in",
        "密码", "登录", "账号", "账户",
    ),
}

# Ties are broken by this fixed order, never by dict iteration order.
CATEGORY_TIE_BREAK_ORDER: tuple[Category, ...] = (
    Category.REFUND,
    Category.BILLING,
    Category.TECHNICAL,
    Category.ACCOUNT,
)

ANGRY_KEYWORDS = (
    "unacceptable", "furious", "outrageous", "disgusted", "worst", "scam",
    "ridiculous", "太差劲", "愤怒", "投诉", "无法接受", "垃圾",
)
FRUSTRATED_KEYWORDS = (
    "again", "still not", "third time", "frustrat", "disappointed", "waiting",
    "又一次", "还是没有", "第三次", "失望", "一直在等",
)
SATISFIED_KEYWORDS = ("thank", "great", "appreciate", "谢谢", "感谢", "满意")

ACTION_TEMPLATES: dict[Category, str] = {
    Category.REFUND: "Review the order and process a refund if the policy allows it",
    Category.BILLING: "Reconcile the disputed charge against the customer's invoice",
    Category.TECHNICAL: "Reproduce the reported fault and open an engineering ticket",
    Category.ACCOUNT: "Guide the customer through account recovery after verifying identity",
    Category.OTHER: "Read the ticket manually and decide where it belongs",
}

BASE_CONFIDENCE = 0.55
CONFIDENCE_PER_HIT = 0.15
MAX_CONFIDENCE = 0.95
UNMATCHED_CONFIDENCE = 0.30
RETRY_EVIDENCE_BONUS = 0.25


def _count_hits(text: str, keywords: tuple[str, ...]) -> list[str]:
    return [keyword for keyword in keywords if keyword in text]


class MockDriver:
    """Deterministic stand-in for a real model. Implements :class:`LLMDriver`."""

    def classify(self, view: TicketView, context: ToolContext) -> LLMSuggestion:
        text = f"{view.subject}\n{view.redacted_body}".lower()

        hits_by_category = {
            category: _count_hits(text, keywords)
            for category, keywords in CATEGORY_KEYWORDS.items()
        }
        best_count = max((len(hits) for hits in hits_by_category.values()), default=0)

        if best_count == 0:
            category = Category.OTHER
            matched: list[str] = []
            confidence = UNMATCHED_CONFIDENCE
        else:
            category = next(
                candidate
                for candidate in CATEGORY_TIE_BREAK_ORDER
                if len(hits_by_category[candidate]) == best_count
            )
            matched = hits_by_category[category]
            confidence = min(
                BASE_CONFIDENCE + CONFIDENCE_PER_HIT * best_count, MAX_CONFIDENCE
            )

        if context.is_retry and context.has_new_evidence:
            confidence = min(confidence + RETRY_EVIDENCE_BONUS, MAX_CONFIDENCE)

        sentiment = self._sentiment(text)
        rationale = (
            f"MockDriver matched {matched or 'no'} keyword(s) for {category.value}"
            f"; sentiment cues suggest {sentiment.value}"
        )
        if context.is_retry:
            rationale += "; this was a retry with additional tool context"

        return LLMSuggestion(
            category=category,
            sentiment=sentiment,
            confidence=round(confidence, 4),
            suggested_priority=Priority.P3 if category is Category.OTHER else Priority.P2,
            suggested_action=ACTION_TEMPLATES[category],
            rationale=rationale,
        )

    @staticmethod
    def _sentiment(text: str) -> Sentiment:
        if _count_hits(text, ANGRY_KEYWORDS):
            return Sentiment.ANGRY
        if _count_hits(text, FRUSTRATED_KEYWORDS):
            return Sentiment.FRUSTRATED
        if _count_hits(text, SATISFIED_KEYWORDS):
            return Sentiment.SATISFIED
        return Sentiment.NEUTRAL
