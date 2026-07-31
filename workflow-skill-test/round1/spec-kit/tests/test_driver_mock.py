"""MockDriver behaviour (task T027).

FR-029 (deterministic, offline), FR-031 (English and Chinese).

The driver is only a classifier: it has no authority over anything. These tests check that it
is *reproducible*, which is the single property the rest of the suite relies on.
"""

from __future__ import annotations

import pytest

from triagebot import Category, Sentiment
from triagebot.drivers import LLMDriver
from triagebot.drivers.mock import CATEGORY_KEYWORDS, MockDriver

from .conftest import make_ticket


def test_mock_driver_satisfies_the_protocol() -> None:
    assert isinstance(MockDriver(), LLMDriver)


def test_classification_is_deterministic() -> None:
    """SC-004 depends on this: same ticket in, byte-identical proposal out, every time."""
    ticket = make_ticket(subject="Refund please", body="I want a refund for my order.")
    driver = MockDriver()
    first = driver.classify(ticket)
    for _ in range(5):
        assert driver.classify(ticket) == first


def test_two_driver_instances_agree() -> None:
    ticket = make_ticket(body="The app shows an error and then it will crash.")
    assert MockDriver().classify(ticket) == MockDriver().classify(ticket)


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("I would like a refund for this order.", Category.REFUND),
        ("My invoice shows a double charge this month.", Category.BILLING),
        ("The app shows an error and will crash on launch.", Category.TECHNICAL),
        ("I cannot sign in, my password reset fails.", Category.ACCOUNT),
        ("Just wondering when you open on weekends.", Category.OTHER),
    ],
)
def test_english_categories(body: str, expected: Category) -> None:
    # Neutral subject: the classifier reads subject and body together, so a default subject
    # mentioning "log in" would quietly decide the OTHER case for us.
    ticket = make_ticket(subject="Customer message", body=body)
    assert MockDriver().classify(ticket).category is expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("我要申请退款,这个商品有问题。", Category.REFUND),
        ("我的账单出现了重复收费。", Category.BILLING),
        ("应用一直报错然后崩溃。", Category.TECHNICAL),
        ("我的密码无法登录了。", Category.ACCOUNT),
    ],
)
def test_chinese_categories(body: str, expected: Category) -> None:
    """FR-031: the keyword tables genuinely cover Chinese, not only English."""
    assert MockDriver().classify(make_ticket(subject="问题", body=body)).category is expected


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("This is unacceptable and the worst service ever.", Sentiment.ANGRY),
        ("I am frustrated, this is the third time I report it.", Sentiment.FRUSTRATED),
        ("Thanks for the quick help earlier.", Sentiment.POSITIVE),
        ("Please advise on the delivery window.", Sentiment.NEUTRAL),
    ],
)
def test_sentiment_detection(body: str, expected: Sentiment) -> None:
    assert MockDriver().classify(make_ticket(body=body)).sentiment is expected


def test_unmatched_ticket_reports_low_confidence() -> None:
    """No keyword match is genuine uncertainty, and it must fall below the 0.60 threshold."""
    proposal = MockDriver().classify(make_ticket(subject="Hello", body="A general enquiry."))
    assert proposal.category is Category.OTHER
    assert proposal.confidence < 0.60


def test_context_raises_confidence(make_context) -> None:  # noqa: ANN001
    """The retry needs a reason to reach a different answer (FR-013)."""
    ticket = make_ticket(subject="Hello", body="A general enquiry.")
    driver = MockDriver()
    without = driver.classify(ticket).confidence
    with_context = driver.classify(ticket, make_context()).confidence
    assert with_context > without


def test_confidence_stays_within_unit_interval() -> None:
    strong = make_ticket(
        subject="Refund and money back",
        body="I want a refund, money back, reimburse me, return the item, send it back.",
    )
    assert 0.0 <= MockDriver().classify(strong).confidence <= 1.0


def test_proposed_priority_is_ignored_downstream_but_still_emitted() -> None:
    """The driver is allowed an opinion; it just does not get a vote (FR-010b)."""
    proposal = MockDriver().classify(make_ticket())
    assert proposal.priority is not None


def test_keyword_tables_cover_every_non_other_category() -> None:
    assert set(CATEGORY_KEYWORDS) == set(Category) - {Category.OTHER}
