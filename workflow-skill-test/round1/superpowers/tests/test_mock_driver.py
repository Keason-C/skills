from triagebot.drivers.base import ToolContext
from triagebot.drivers.mock import MockDriver
from triagebot.models import Category, Language, Sentiment, TicketView
from triagebot.tools import ToolBox


def _view(body: str, **over):
    base = dict(
        ticket_id="T-1",
        subject="Help",
        redacted_body=body,
        language=Language.EN,
        amount=None,
        order_id=None,
    )
    base.update(over)
    return TicketView(**base)


def test_refund_keywords_yield_refund_category():
    s = MockDriver().classify(_view("I want a refund for my order"), ToolContext())
    assert s.category is Category.REFUND


def test_chinese_refund_keywords_yield_refund_category():
    view = _view("我要退款,这个订单有问题", language=Language.ZH)
    assert MockDriver().classify(view, ToolContext()).category is Category.REFUND


def test_technical_keywords_yield_technical_category():
    s = MockDriver().classify(_view("The app crashes with a 500 error"), ToolContext())
    assert s.category is Category.TECHNICAL


def test_unmatched_text_falls_back_to_other_with_low_confidence():
    s = MockDriver().classify(_view("Hello there friend"), ToolContext())
    assert s.category is Category.OTHER
    assert s.confidence < 0.6


def test_angry_wording_yields_angry_sentiment():
    s = MockDriver().classify(
        _view("This is unacceptable, I am furious about the refund"), ToolContext()
    )
    assert s.sentiment is Sentiment.ANGRY


def test_driver_is_deterministic_across_calls():
    driver, view = MockDriver(), _view("refund my order please")
    assert driver.classify(view, ToolContext()) == driver.classify(view, ToolContext())


def test_retry_with_new_evidence_raises_confidence():
    driver, view = MockDriver(), _view("Hello there friend")
    first = driver.classify(view, ToolContext())
    policy = ToolBox().get_refund_policy(Category.OTHER)
    retried = driver.classify(view, ToolContext(refund_policy=policy, is_retry=True))
    assert retried.confidence > first.confidence


def test_retry_without_new_evidence_keeps_confidence():
    driver, view = MockDriver(), _view("Hello there friend")
    first = driver.classify(view, ToolContext())
    retried = driver.classify(view, ToolContext(is_retry=True))
    assert retried.confidence == first.confidence


def test_confidence_never_exceeds_one():
    driver = MockDriver()
    view = _view("refund refund refund money back return the order")
    policy = ToolBox().get_refund_policy(Category.REFUND)
    s = driver.classify(view, ToolContext(refund_policy=policy, is_retry=True))
    assert 0.0 <= s.confidence <= 1.0


def test_driver_never_reads_the_raw_ticket_body_field():
    view = _view("refund please")
    assert not hasattr(view, "body")


def test_tool_context_reports_new_evidence_when_an_order_was_found():
    order = ToolBox().get_order_status("ORD-1001")
    assert ToolContext(order=order, order_lookup_attempted=True).has_new_evidence is True


def test_tool_context_reports_no_new_evidence_when_empty():
    assert ToolContext().has_new_evidence is False
