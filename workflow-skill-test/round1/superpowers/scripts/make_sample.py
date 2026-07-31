#!/usr/bin/env python
"""Produce the TS test fixtures by running a real triage.

The point of generating rather than hand-writing these: the TypeScript tests
then prove that zod accepts what pydantic actually emits, not what someone
believed pydantic emits.
"""

import json
from pathlib import Path

from triagebot.drivers.mock import MockDriver
from triagebot.engine import TriageEngine
from triagebot.models import Ticket
from triagebot.tools import ToolBox

REPO_ROOT = Path(__file__).parent.parent
FIXTURES = REPO_ROOT / "ts" / "test" / "fixtures"


def main() -> None:
    FIXTURES.mkdir(parents=True, exist_ok=True)
    engine = TriageEngine(driver=MockDriver(), toolbox=ToolBox())

    ticket = Ticket(
        id="T-1001",
        customer_id="C-77",
        subject="Refund request for damaged item",
        body="I would like a refund for my order, the item arrived damaged.",
        order_id="ORD-1001",
    )
    result = engine.triage(ticket)
    valid = json.loads(result.model_dump_json())
    (FIXTURES / "valid-result.json").write_text(
        json.dumps(valid, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # A tampered copy: the enum member does not exist. zod must reject it.
    invalid = dict(valid, category="SUPERURGENT")
    (FIXTURES / "invalid-result.json").write_text(
        json.dumps(invalid, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    print(f"wrote {(FIXTURES / 'valid-result.json').relative_to(REPO_ROOT)}")
    print(f"wrote {(FIXTURES / 'invalid-result.json').relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
