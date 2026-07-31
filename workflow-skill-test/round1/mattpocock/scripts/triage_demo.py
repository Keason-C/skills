"""Triage the sample tickets and write one Verdict JSON file per ticket.

Usage: python scripts/triage_demo.py
Output: examples/verdicts/<ticket-id>.json — exactly what the TypeScript CLI consumes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from triagebot.drivers.mock import MockDriver  # noqa: E402
from triagebot.models import Ticket  # noqa: E402
from triagebot.pipeline import triage_ticket  # noqa: E402

TICKETS = ROOT / "examples" / "tickets.json"
VERDICTS = ROOT / "examples" / "verdicts"


def main() -> None:
    VERDICTS.mkdir(parents=True, exist_ok=True)
    driver = MockDriver()

    for raw in json.loads(TICKETS.read_text("utf-8")):
        ticket = Ticket.model_validate(raw)
        verdict = triage_ticket(ticket, driver)
        path = VERDICTS / f"{ticket.id}.json"
        path.write_text(verdict.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(
            f"{ticket.id}: {verdict.category.value} / {verdict.priority.value} / "
            f"{'ESCALATED' if verdict.escalated_to_human else 'AUTO-RESOLVED'} -> {path.name}"
        )


if __name__ == "__main__":
    main()
