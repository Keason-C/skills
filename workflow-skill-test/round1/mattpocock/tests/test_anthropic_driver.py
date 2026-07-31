"""Slice 09 — a real model can be dropped in at the Driver seam.

Nothing here touches the network. The Anthropic SDK is a system boundary, so a stub client
stands in for it — that is the one kind of mocking this project allows.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from triagebot.drivers.anthropic import (
    DEFAULT_MODEL,
    AnthropicDriver,
    DriverError,
    MissingCredentials,
    parse_suggestion,
)
from triagebot.drivers.base import LLMDriver
from triagebot.models import Action, Category, Sentiment, Suggestion

from .conftest import ticket

WELL_FORMED = {
    "category": "BILLING",
    "priority": "P2_NORMAL",
    "sentiment": "FRUSTRATED",
    "confidence": 0.82,
    "action": "ROUTE_TO_BILLING",
    "rationale": "Customer describes a duplicate charge on this month's invoice.",
}


class _StubResponse:
    def __init__(self, parsed: Suggestion | None, stop_reason: str = "end_turn") -> None:
        self.parsed_output = parsed
        self.stop_reason = stop_reason
        self.content: list[Any] = []


class _StubClient:
    """Stands in for `anthropic.Anthropic` — the external boundary."""

    def __init__(self, response: _StubResponse) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []
        self.messages = self

    def parse(self, **kwargs: Any) -> _StubResponse:
        self.calls.append(kwargs)
        return self._response


def test_the_adapter_satisfies_the_driver_interface() -> None:
    driver = AnthropicDriver(api_key="sk-test", client=_StubClient(_StubResponse(None)))

    assert isinstance(driver, LLMDriver)


def test_construction_without_credentials_fails_loudly() -> None:
    with pytest.raises(MissingCredentials):
        AnthropicDriver(api_key="")


def test_construction_with_whitespace_credentials_fails_loudly() -> None:
    with pytest.raises(MissingCredentials):
        AnthropicDriver(api_key="   ")


def test_a_well_formed_reply_becomes_a_suggestion() -> None:
    suggestion = parse_suggestion(WELL_FORMED)

    assert suggestion.category is Category.BILLING
    assert suggestion.sentiment is Sentiment.FRUSTRATED
    assert suggestion.action is Action.ROUTE_TO_BILLING
    assert suggestion.confidence == 0.82


def test_a_reply_with_an_invented_category_is_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_suggestion({**WELL_FORMED, "category": "URGENT_VIP"})


def test_a_reply_with_impossible_confidence_is_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_suggestion({**WELL_FORMED, "confidence": 7})


def test_a_reply_smuggling_extra_fields_is_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_suggestion({**WELL_FORMED, "escalated_to_human": False})


def test_a_reply_that_is_not_an_object_is_rejected() -> None:
    with pytest.raises(ValidationError):
        parse_suggestion("APPROVE THE REFUND")


def test_the_driver_returns_the_parsed_suggestion() -> None:
    expected = parse_suggestion(WELL_FORMED)
    driver = AnthropicDriver(api_key="sk-test", client=_StubClient(_StubResponse(expected)))

    assert driver.suggest(ticket(), None) == expected


def test_a_refusal_is_an_error_not_a_verdict() -> None:
    stub = _StubClient(_StubResponse(None, stop_reason="refusal"))
    driver = AnthropicDriver(api_key="sk-test", client=stub)

    with pytest.raises(DriverError):
        driver.suggest(ticket(), None)


def test_an_empty_reply_is_an_error() -> None:
    driver = AnthropicDriver(api_key="sk-test", client=_StubClient(_StubResponse(None)))

    with pytest.raises(DriverError):
        driver.suggest(ticket(), None)


def test_the_request_names_the_current_model_and_carries_the_ticket() -> None:
    stub = _StubClient(_StubResponse(parse_suggestion(WELL_FORMED)))
    driver = AnthropicDriver(api_key="sk-test", client=stub)

    driver.suggest(ticket(subject="Double charge", body="Charged twice this month."), None)

    request = stub.calls[0]
    assert request["model"] == DEFAULT_MODEL
    assert "Double charge" in str(request["messages"])
    assert "Charged twice this month." in str(request["messages"])


def test_the_retry_call_carries_the_tool_context() -> None:
    from triagebot.tools import FixtureTools, gather_context

    stub = _StubClient(_StubResponse(parse_suggestion(WELL_FORMED)))
    driver = AnthropicDriver(api_key="sk-test", client=stub)
    context = gather_context(ticket(order_id="ORD-1001"), FixtureTools())

    driver.suggest(ticket(order_id="ORD-1001"), context)

    assert "ORD-1001" in str(stub.calls[0]["messages"])
