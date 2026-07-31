"""Offline tests for the real Claude driver.

The driver itself is never instantiated here: constructing it imports the
`anthropic` SDK and would invite a network call. What *is* tested is everything
that can be tested without one — prompt construction and response parsing —
which is also where the security-relevant behaviour lives.
"""

import pytest
from pydantic import ValidationError

from triagebot.drivers.anthropic_driver import build_prompt, parse_response
from triagebot.drivers.base import ToolContext
from triagebot.models import Category, Language, TicketView
from triagebot.tools import ToolBox


def _view(body: str = "I want a refund"):
    return TicketView(
        ticket_id="T-1",
        subject="Refund",
        redacted_body=body,
        language=Language.EN,
        amount=None,
        order_id="ORD-1001",
    )


def test_prompt_contains_the_redacted_body():
    assert "I want a refund" in build_prompt(_view(), ToolContext())


def test_prompt_includes_tool_context_when_present():
    policy = ToolBox().get_refund_policy(Category.REFUND)
    assert policy.policy_id in build_prompt(_view(), ToolContext(refund_policy=policy))


def test_prompt_includes_order_facts_when_present():
    order = ToolBox().get_order_status("ORD-1001")
    assert "shipped" in build_prompt(_view(), ToolContext(order=order))


def test_prompt_marks_the_ticket_body_as_untrusted_data():
    assert "untrusted" in build_prompt(_view(), ToolContext()).lower()


def test_prompt_carries_the_redaction_marker_through():
    view = _view("[REDACTED:INJECTION] please refund")
    assert "[REDACTED:INJECTION]" in build_prompt(view, ToolContext())


def test_prompt_says_the_retry_is_a_retry():
    assert "retry" in build_prompt(_view(), ToolContext(is_retry=True)).lower()


def test_parse_response_builds_a_validated_suggestion():
    s = parse_response(
        {
            "category": "REFUND",
            "sentiment": "NEUTRAL",
            "confidence": 0.8,
            "suggested_priority": "P2",
            "suggested_action": "refund it",
            "rationale": "clear refund request",
        }
    )
    assert s.category is Category.REFUND


def test_parse_response_rejects_an_out_of_range_confidence():
    with pytest.raises(ValidationError):
        parse_response(
            {
                "category": "REFUND",
                "sentiment": "NEUTRAL",
                "confidence": 1.5,
                "suggested_priority": "P2",
                "suggested_action": "x",
                "rationale": "y",
            }
        )


def test_parse_response_rejects_an_invented_category():
    with pytest.raises(ValidationError):
        parse_response(
            {
                "category": "SUPERURGENT",
                "sentiment": "NEUTRAL",
                "confidence": 0.8,
                "suggested_priority": "P2",
                "suggested_action": "x",
                "rationale": "y",
            }
        )


def test_parse_response_rejects_extra_fields_the_model_invented():
    with pytest.raises(ValidationError):
        parse_response(
            {
                "category": "REFUND",
                "sentiment": "NEUTRAL",
                "confidence": 0.8,
                "suggested_priority": "P2",
                "suggested_action": "x",
                "rationale": "y",
                "escalate": True,
            }
        )


def test_importing_the_module_does_not_require_the_sdk():
    import triagebot.drivers.anthropic_driver as mod

    assert hasattr(mod, "AnthropicDriver")


def test_the_driver_satisfies_the_llm_driver_protocol():
    from triagebot.drivers.anthropic_driver import AnthropicDriver
    from triagebot.drivers.base import LLMDriver

    assert issubclass(AnthropicDriver, LLMDriver)
