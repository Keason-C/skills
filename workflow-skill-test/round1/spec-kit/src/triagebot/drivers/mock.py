"""Deterministic stand-in for a language model (task T020).

Every test uses this driver, which is what lets the whole suite run offline with no
credentials (FR-029, Principle IV). It is a keyword classifier: crude, but *reproducible*,
and reproducibility is the property the tests actually need.

**Vocabulary invariant.** The keyword tables below must share no token with the injection
signature table in ``guards.injection``. If they overlapped, appending injection text to a
ticket could legitimately change its category, and the FR-018 equivalence test would be
testing nothing. Enforced by
``tests/test_guard_injection.py::test_signature_vocabulary_is_disjoint_from_driver_keywords``.
"""

from __future__ import annotations

from ..models import (
    ActionKind,
    Category,
    ClassificationProposal,
    Priority,
    Sentiment,
    Ticket,
    ToolContext,
)

#: Category keyword tables, English and Chinese (FR-031).
CATEGORY_KEYWORDS: dict[Category, tuple[str, ...]] = {
    Category.REFUND: (
        "refund",
        "money back",
        "reimburse",
        "return the item",
        "send it back",
        "退款",
        "退货",
        "退钱",
    ),
    Category.BILLING: (
        "invoice",
        "billing",
        "charged twice",
        "overcharge",
        "double charge",
        "subscription fee",
        "账单",
        "扣款",
        "重复收费",
        "发票",
    ),
    Category.TECHNICAL: (
        "error",
        "crash",
        "bug",
        "broken",
        "not loading",
        "timeout",
        "报错",
        "崩溃",
        "打不开",
        "故障",
    ),
    Category.ACCOUNT: (
        "login",
        "log in",
        "password",
        "locked out",
        "sign in",
        "two-factor",
        "登录",
        "密码",
        "账号锁定",
    ),
}

SENTIMENT_KEYWORDS: dict[Sentiment, tuple[str, ...]] = {
    Sentiment.ANGRY: (
        "furious",
        "unacceptable",
        "outrageous",
        "terrible",
        "worst",
        "愤怒",
        "太差",
        "无法接受",
    ),
    Sentiment.FRUSTRATED: (
        "frustrated",
        "annoying",
        "still not",
        "third time",
        "again",
        "烦",
        "又一次",
        "还是不行",
    ),
    Sentiment.POSITIVE: (
        "thanks",
        "thank you",
        "appreciate",
        "great",
        "谢谢",
        "感谢",
    ),
}

#: What the model would *like* to do per category. Several of these are terminal actions,
#: which the guards then refuse to execute -- exactly the intended dynamic.
DEFAULT_ACTIONS: dict[Category, ActionKind] = {
    Category.REFUND: ActionKind.APPROVE_REFUND,
    Category.BILLING: ActionKind.ANSWER_QUESTION,
    Category.TECHNICAL: ActionKind.INVESTIGATE_TECHNICAL,
    Category.ACCOUNT: ActionKind.RESET_CREDENTIALS,
    Category.OTHER: ActionKind.REQUEST_INFO,
}

#: Confidence model. Deliberately simple and total: no keyword match means genuine
#: uncertainty (0.50, below the 0.60 threshold), so the retry path is reachable with
#: ordinary input rather than only with a stub.
_NO_MATCH_CONFIDENCE = 0.50
_BASE_CONFIDENCE = 0.62
_PER_MATCH = 0.11
_CONTEXT_BONUS = 0.12
_MAX_CONFIDENCE = 0.95


class MockDriver:
    """A deterministic keyword classifier implementing the `LLMDriver` protocol."""

    name = "mock"

    def classify(
        self,
        ticket: Ticket,
        context: ToolContext | None = None,
    ) -> ClassificationProposal:
        haystack = f"{ticket.subject}\n{ticket.body}".lower()

        category, matches = self._categorise(haystack)
        sentiment = self._sentiment(haystack)
        confidence = self._confidence(matches, context is not None)
        action = DEFAULT_ACTIONS[category]

        reasoning = (
            f"Matched {matches} keyword(s) for {category.value}; sentiment read as "
            f"{sentiment.value}."
        )
        if context is not None:
            reasoning += " Re-assessed with order and policy context attached."

        return ClassificationProposal(
            category=category,
            # A priority the guards will ignore: the driver is allowed an opinion, it just
            # does not get a vote (FR-010b).
            priority=Priority.P2,
            sentiment=sentiment,
            confidence=confidence,
            suggested_action=action,
            reasoning=reasoning,
        )

    @staticmethod
    def _categorise(haystack: str) -> tuple[Category, int]:
        best_category = Category.OTHER
        best_count = 0
        # Iterate in a fixed order so ties resolve deterministically (FR-021).
        for category in (
            Category.REFUND,
            Category.BILLING,
            Category.TECHNICAL,
            Category.ACCOUNT,
        ):
            count = sum(1 for kw in CATEGORY_KEYWORDS[category] if kw in haystack)
            if count > best_count:
                best_category, best_count = category, count
        return best_category, best_count

    @staticmethod
    def _sentiment(haystack: str) -> Sentiment:
        for sentiment in (Sentiment.ANGRY, Sentiment.FRUSTRATED, Sentiment.POSITIVE):
            if any(kw in haystack for kw in SENTIMENT_KEYWORDS[sentiment]):
                return sentiment
        return Sentiment.NEUTRAL

    @staticmethod
    def _confidence(matches: int, has_context: bool) -> float:
        if matches == 0:
            value = _NO_MATCH_CONFIDENCE
        else:
            value = _BASE_CONFIDENCE + _PER_MATCH * (matches - 1)
        if has_context:
            value += _CONTEXT_BONUS
        return round(min(value, _MAX_CONFIDENCE), 4)
