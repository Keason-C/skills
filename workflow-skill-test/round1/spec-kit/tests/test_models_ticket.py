"""Ticket intake validation -- scenarios V2-V5 (task T023).

Requirements under test: FR-001 (blank fields), FR-002 (over-length body, rejected not
truncated), FR-003 (negative amount), FR-004 (unknown fields), SC-005 (rejected before
classification, offending field named).
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from triagebot import Ticket
from triagebot.models import MAX_BODY_LENGTH

from .conftest import make_ticket


def _fields(exc: ValidationError) -> set[str]:
    return {".".join(str(part) for part in issue["loc"]) for issue in exc.value.errors()}


def test_valid_ticket_round_trips() -> None:
    ticket = make_ticket(order_id="ORD-1001", amount=Decimal("10.50"))
    assert ticket.id == "T-1"
    assert ticket.amount == Decimal("10.50")


def test_ticket_is_frozen() -> None:
    """Immutability is what makes 'same input -> identical result' a type-level property."""
    ticket = make_ticket()
    with pytest.raises(ValidationError):
        ticket.body = "something else"  # type: ignore[misc]


# --- V2: blank / whitespace-only ------------------------------------------------------


@pytest.mark.parametrize("blank", ["", "   ", "\n\t  \n"])
def test_blank_body_rejected(blank: str) -> None:
    with pytest.raises(ValidationError) as exc:
        make_ticket(body=blank)
    assert "body" in _fields(exc)


@pytest.mark.parametrize("field", ["id", "customer_id", "subject", "body"])
def test_every_required_field_rejects_whitespace(field: str) -> None:
    with pytest.raises(ValidationError) as exc:
        make_ticket(**{field: "   "})  # type: ignore[arg-type]
    assert field in _fields(exc), f"{field} should be named in the error"


def test_missing_required_field_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        Ticket(id="T-1", customer_id="C-1", subject="hi")  # type: ignore[call-arg]
    assert "body" in _fields(exc)


def test_subject_and_body_are_stripped() -> None:
    ticket = make_ticket(subject="  spaced  ", body="  padded body  ")
    assert ticket.subject == "spaced"
    assert ticket.body == "padded body"


# --- V3: over-length ------------------------------------------------------------------


def test_body_at_limit_accepted() -> None:
    ticket = make_ticket(body="x" * MAX_BODY_LENGTH)
    assert len(ticket.body) == MAX_BODY_LENGTH


def test_body_over_limit_rejected_not_truncated() -> None:
    """FR-002: rejecting matters because truncation would let text hide past the cut."""
    with pytest.raises(ValidationError) as exc:
        make_ticket(body="x" * (MAX_BODY_LENGTH + 1))
    assert "body" in _fields(exc)


def test_subject_over_limit_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        make_ticket(subject="x" * 201)
    assert "subject" in _fields(exc)


# --- V5: negative and malformed amounts -----------------------------------------------


def test_negative_amount_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        make_ticket(amount=Decimal("-0.01"))
    assert "amount" in _fields(exc)


def test_zero_amount_accepted() -> None:
    assert make_ticket(amount=Decimal("0")).amount == Decimal("0")


def test_too_many_decimal_places_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        make_ticket(amount=Decimal("10.001"))
    assert "amount" in _fields(exc)


def test_strict_mode_rejects_python_side_coercion() -> None:
    """Strict mode is why a string amount cannot sneak in through the Python API."""
    with pytest.raises(ValidationError):
        Ticket(
            id="T-1",
            customer_id="C-1",
            subject="s",
            body="b",
            amount="1000",  # type: ignore[arg-type]
        )


# --- V4: unknown fields ---------------------------------------------------------------


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError) as exc:
        Ticket(
            id="T-1",
            customer_id="C-1",
            subject="s",
            body="b",
            priority="P0",  # type: ignore[call-arg]
        )
    assert "priority" in _fields(exc)


# --- JSON boundary --------------------------------------------------------------------


def test_json_input_accepts_natural_encodings() -> None:
    """The CLI parses JSON, where numbers and strings for Decimal are both acceptable."""
    ticket = Ticket.model_validate_json(
        '{"id":"T-9","customer_id":"C-9","subject":"s","body":"b","amount":1000}'
    )
    assert ticket.amount == Decimal("1000")


def test_json_input_still_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError) as exc:
        Ticket.model_validate_json(
            '{"id":"T-9","customer_id":"C-9","subject":"s","body":"b","nope":1}'
        )
    assert "nope" in _fields(exc)
