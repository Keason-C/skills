"""Slice 01 — malformed Tickets are refused at the boundary, before any Guard sees them."""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from triagebot.models import Ticket

from .conftest import ticket


def test_a_well_formed_ticket_is_accepted() -> None:
    accepted = ticket(id="TCK-100", subject="Refund please", body="I want my money back.")

    assert accepted.id == "TCK-100"
    assert accepted.amount is None


def test_an_empty_body_is_refused() -> None:
    with pytest.raises(ValidationError):
        ticket(body="")


def test_a_whitespace_only_body_is_refused() -> None:
    with pytest.raises(ValidationError):
        ticket(body="   \n\t  ")


def test_a_body_over_twenty_thousand_characters_is_refused() -> None:
    with pytest.raises(ValidationError):
        ticket(body="a" * 20_001)


def test_a_body_of_exactly_twenty_thousand_characters_is_accepted() -> None:
    assert len(ticket(body="a" * 20_000).body) == 20_000


def test_a_subject_over_two_hundred_characters_is_refused() -> None:
    with pytest.raises(ValidationError):
        ticket(subject="s" * 201)


def test_a_subject_of_exactly_two_hundred_characters_is_accepted() -> None:
    assert len(ticket(subject="s" * 200).subject) == 200


def test_an_unknown_field_is_refused() -> None:
    with pytest.raises(ValidationError):
        Ticket(
            id="TCK-1",
            customer_id="CUST-1",
            subject="Hi",
            body="Hello",
            internal_priority_override="P0",  # type: ignore[call-arg]
        )


def test_a_negative_amount_is_refused() -> None:
    with pytest.raises(ValidationError):
        ticket(amount=Decimal("-0.01"))


def test_a_non_finite_amount_is_refused() -> None:
    with pytest.raises(ValidationError):
        ticket(amount=Decimal("NaN"))


def test_an_amount_is_exact_not_floating_point() -> None:
    priced = ticket(amount=Decimal("1000.01"))

    assert priced.amount == Decimal("1000.01")
    assert isinstance(priced.amount, Decimal)


def test_a_ticket_cannot_be_mutated_after_acceptance() -> None:
    accepted = ticket()

    with pytest.raises(ValidationError):
        accepted.body = "something else"  # type: ignore[misc]
