"""Retry semantics, pinned with a probe driver.

The probe lives here rather than in the package: production code must not carry
test-only branches. It implements the same ``LLMDriver`` protocol the real
drivers do, which is exactly why the engine needs no knowledge of it.
"""

from triagebot.drivers.base import ToolContext
from triagebot.engine import TriageEngine
from triagebot.models import (
    Category,
    GuardCode,
    LLMSuggestion,
    Priority,
    Sentiment,
    Ticket,
    TicketView,
)
from triagebot.states import TriageState
from triagebot.tools import ToolBox


class RecordingDriver:
    """Returns a scripted confidence per call and records the context it saw."""

    def __init__(self, confidences: list[float]) -> None:
        self.confidences = list(confidences)
        self.contexts: list[ToolContext] = []

    def classify(self, view: TicketView, context: ToolContext) -> LLMSuggestion:
        self.contexts.append(context)
        index = min(len(self.contexts) - 1, len(self.confidences) - 1)
        return LLMSuggestion(
            category=Category.BILLING,
            sentiment=Sentiment.NEUTRAL,
            confidence=self.confidences[index],
            suggested_priority=Priority.P2,
            suggested_action="check the invoice",
            rationale="probe driver",
        )


class CategorySwitchingDriver:
    """Answers BILLING first, then REFUND on the retry.

    A real model is free to change its mind once it sees more evidence; this
    probe makes the engine prove it re-fetches the policy for the category it
    actually ended up with, not the one it guessed first.
    """

    def __init__(self) -> None:
        self.calls = 0

    def classify(self, view: TicketView, context: ToolContext) -> LLMSuggestion:
        self.calls += 1
        first = self.calls == 1
        return LLMSuggestion(
            category=Category.BILLING if first else Category.REFUND,
            sentiment=Sentiment.NEUTRAL,
            confidence=0.4 if first else 0.9,
            suggested_priority=Priority.P2,
            suggested_action="give them store credit instead",
            rationale="probe driver that changes its mind on retry",
        )


def test_a_retry_that_changes_category_refetches_the_matching_policy():
    r = TriageEngine(driver=CategorySwitchingDriver(), toolbox=ToolBox()).triage(_ticket())
    assert r.category is Category.REFUND
    assert r.recommended_action == ToolBox().get_refund_policy(Category.REFUND).canonical_action


def _ticket() -> Ticket:
    return Ticket(
        id="T-1",
        customer_id="C-1",
        subject="Invoice question",
        body="I was charged twice on my invoice",
        order_id="ORD-1001",
    )


def test_high_confidence_first_answer_is_not_retried():
    driver = RecordingDriver([0.9])
    TriageEngine(driver=driver, toolbox=ToolBox()).triage(_ticket())
    assert len(driver.contexts) == 1


def test_low_confidence_triggers_exactly_one_retry():
    driver = RecordingDriver([0.4, 0.4])
    TriageEngine(driver=driver, toolbox=ToolBox()).triage(_ticket())
    assert len(driver.contexts) == 2


def test_confidence_exactly_at_the_threshold_is_not_retried():
    driver = RecordingDriver([0.6])
    TriageEngine(driver=driver, toolbox=ToolBox()).triage(_ticket())
    assert len(driver.contexts) == 1


def test_the_retry_carries_strictly_more_tool_context():
    driver = RecordingDriver([0.4, 0.4])
    TriageEngine(driver=driver, toolbox=ToolBox()).triage(_ticket())
    first, second = driver.contexts
    assert first.refund_policy is None
    assert second.refund_policy is not None
    assert second.is_retry is True


def test_the_first_attempt_is_not_marked_as_a_retry():
    driver = RecordingDriver([0.9])
    TriageEngine(driver=driver, toolbox=ToolBox()).triage(_ticket())
    assert driver.contexts[0].is_retry is False


def test_retry_that_stays_low_escalates_to_a_human():
    driver = RecordingDriver([0.4, 0.4])
    r = TriageEngine(driver=driver, toolbox=ToolBox()).triage(_ticket())
    assert GuardCode.LOW_CONFIDENCE in r.guards_triggered
    assert r.final_state is TriageState.ESCALATED


def test_retry_that_recovers_confidence_auto_resolves():
    driver = RecordingDriver([0.4, 0.85])
    r = TriageEngine(driver=driver, toolbox=ToolBox()).triage(_ticket())
    assert GuardCode.LOW_CONFIDENCE not in r.guards_triggered
    assert r.final_state is TriageState.AUTO_RESOLVED


def test_engine_never_retries_more_than_once():
    driver = RecordingDriver([0.1, 0.1, 0.1])
    TriageEngine(driver=driver, toolbox=ToolBox()).triage(_ticket())
    assert len(driver.contexts) == 2


def test_the_recovered_confidence_is_the_one_reported():
    driver = RecordingDriver([0.4, 0.85])
    r = TriageEngine(driver=driver, toolbox=ToolBox()).triage(_ticket())
    assert r.confidence == 0.85
