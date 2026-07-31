"""Slice 12 — the committed example Verdicts are exactly what the pipeline produces today.

This is the other half of the cross-language contract: the TypeScript suite validates these
files with zod, so if they drift from the pipeline the TS tests would be checking stale JSON.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from triagebot.drivers.mock import MockDriver
from triagebot.models import Ticket, TriageResult
from triagebot.pipeline import triage_ticket

ROOT = Path(__file__).resolve().parents[1]
TICKETS = ROOT / "examples" / "tickets.json"
VERDICTS = ROOT / "examples" / "verdicts"


def _tickets() -> list[Ticket]:
    return [Ticket.model_validate(raw) for raw in json.loads(TICKETS.read_text("utf-8"))]


def test_the_sample_tickets_are_all_valid() -> None:
    assert len(_tickets()) >= 5


@pytest.mark.parametrize("ticket", _tickets(), ids=lambda t: t.id)
def test_each_committed_verdict_matches_what_the_pipeline_produces_now(ticket: Ticket) -> None:
    committed = TriageResult.model_validate_json(
        (VERDICTS / f"{ticket.id}.json").read_text("utf-8")
    )

    assert triage_ticket(ticket, MockDriver()) == committed


def test_the_examples_cover_both_terminal_outcomes() -> None:
    verdicts = [
        TriageResult.model_validate_json(path.read_text("utf-8"))
        for path in sorted(VERDICTS.glob("*.json"))
    ]

    assert any(verdict.escalated_to_human for verdict in verdicts)
    assert any(not verdict.escalated_to_human for verdict in verdicts)
    assert any(verdict.injection_detected for verdict in verdicts)
