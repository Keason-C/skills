"""The deterministic Driver every test uses.

Keyword tables, no randomness, no I/O. It exists so the Guard chain can be exercised end to end
with a Driver that behaves like a plausible-but-fallible classifier — never as a pretend LLM.
"""

from __future__ import annotations

from triagebot.models import Action, Category, Priority, Sentiment, Suggestion, Ticket
from triagebot.tools import ToolContext

CATEGORY_KEYWORDS: dict[Category, tuple[str, ...]] = {
    Category.REFUND: (
        # English
        "refund",
        "money back",
        "reimburse",
        "chargeback",
        "return the item",
        # Chinese
        "退款",
        "退钱",
        "退货",
        "退还",
    ),
    Category.BILLING: (
        # English
        "charged",
        "charge",
        "invoice",
        "billing",
        "subscription",
        "overcharged",
        "payment failed",
        "double charge",
        # Chinese
        "扣款",
        "账单",
        "发票",
        "订阅",
        "多收",
        "重复收费",
        "付款失败",
    ),
    Category.TECHNICAL: (
        # English
        "crash",
        "error",
        "bug",
        "not working",
        "broken",
        "fails to load",
        "timeout",
        # Chinese
        "崩溃",
        "闪退",
        "报错",
        "故障",
        "打不开",
        "无法使用",
        "坏了",
    ),
    Category.ACCOUNT: (
        # English
        "password",
        "log in",
        "login",
        "sign in",
        "locked out",
        "two-factor",
        "email address",
        # Chinese
        "密码",
        "账号",
        "登录",
        "注册",
        "被锁",
        "两步验证",
    ),
}

SENTIMENT_KEYWORDS: dict[Sentiment, tuple[str, ...]] = {
    Sentiment.ANGRY: (
        # English
        "furious",
        "outrageous",
        "unacceptable",
        "scam",
        "disgusted",
        "appalling",
        "legal action",
        # Chinese
        "欺诈",
        "骗子",
        "无法接受",
        "太差",
        "气死",
        "投诉",
        "简直",
    ),
    Sentiment.FRUSTRATED: (
        # English
        "frustrated",
        "again",
        "still not",
        "third time",
        "annoyed",
        "disappointed",
        "no response",
        # Chinese
        "失望",
        "又一次",
        "还是不行",
        "第三次",
        "没人回复",
        "很烦",
    ),
    Sentiment.SATISFIED: (
        # English
        "thank you",
        "thanks",
        "appreciate",
        "great service",
        "happy with",
        # Chinese
        "谢谢",
        "感谢",
        "满意",
        "很好",
    ),
}

DEFAULT_ACTIONS: dict[Category, Action] = {
    Category.REFUND: Action.AUTO_REFUND,
    Category.BILLING: Action.ROUTE_TO_BILLING,
    Category.TECHNICAL: Action.ROUTE_TO_TECH_SUPPORT,
    Category.ACCOUNT: Action.ROUTE_TO_ACCOUNT_TEAM,
    Category.OTHER: Action.ESCALATE_TO_HUMAN,
}

SUGGESTED_PRIORITIES: dict[Category, Priority] = {
    Category.REFUND: Priority.P2_NORMAL,
    Category.BILLING: Priority.P2_NORMAL,
    Category.TECHNICAL: Priority.P2_NORMAL,
    Category.ACCOUNT: Priority.P3_LOW,
    Category.OTHER: Priority.P3_LOW,
}

_BASE_CONFIDENCE = 0.5
_PER_HIT = 0.15
_MAX_CONFIDENCE = 0.95
_NO_SIGNAL_CONFIDENCE = 0.35

UNSUPPORTED_LANGUAGE_CONFIDENCE = 0.4
"""A Ticket outside English and Chinese is honestly uncategorised, with confidence capped below
the threshold so the ordinary confidence Guard routes it to a human (product decision P9)."""


def _looks_chinese(text: str) -> bool:
    return any("一" <= char <= "鿿" for char in text)


def _looks_english(text: str) -> bool:
    return any("a" <= char <= "z" for char in text.lower())


class MockDriver:
    """Deterministic keyword classification in English and Chinese. The shipped offline adapter."""

    def suggest(self, ticket: Ticket, context: ToolContext | None) -> Suggestion:
        text = f"{ticket.subject}\n{ticket.body}".lower()
        seen = "with order and policy facts" if context is not None else "from the ticket text"

        if not (_looks_chinese(text) or _looks_english(text)):
            return Suggestion(
                category=Category.OTHER,
                priority=SUGGESTED_PRIORITIES[Category.OTHER],
                sentiment=Sentiment.NEUTRAL,
                confidence=UNSUPPORTED_LANGUAGE_CONFIDENCE,
                action=DEFAULT_ACTIONS[Category.OTHER],
                rationale=(
                    f"Read {seen}: the ticket is not in English or Chinese, "
                    "so it cannot be categorised with any confidence."
                ),
            )

        category, hits = self._categorise(text)
        sentiment = self._read_sentiment(text)
        confidence = (
            _NO_SIGNAL_CONFIDENCE
            if hits == 0
            else min(_BASE_CONFIDENCE + _PER_HIT * hits, _MAX_CONFIDENCE)
        )

        return Suggestion(
            category=category,
            priority=SUGGESTED_PRIORITIES[category],
            sentiment=sentiment,
            confidence=confidence,
            action=DEFAULT_ACTIONS[category],
            rationale=(
                f"Read {seen}: matched {hits} {category.value} signal(s), "
                f"tone reads {sentiment.value}."
            ),
        )

    def _categorise(self, text: str) -> tuple[Category, int]:
        scores = {
            category: sum(keyword in text for keyword in keywords)
            for category, keywords in CATEGORY_KEYWORDS.items()
        }
        best = max(scores, key=lambda category: scores[category])
        if scores[best] == 0:
            return Category.OTHER, 0
        return best, scores[best]

    def _read_sentiment(self, text: str) -> Sentiment:
        for sentiment, keywords in SENTIMENT_KEYWORDS.items():
            if any(keyword in text for keyword in keywords):
                return sentiment
        return Sentiment.NEUTRAL
