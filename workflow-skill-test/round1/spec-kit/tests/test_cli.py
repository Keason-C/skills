"""Python CLI contract (task T034 verification).

Exit codes are part of the published contract (contracts/README.md §3), so they are tested
rather than assumed. SC-005 also lives here: an invalid ticket must be rejected *before*
classification and must name the offending field.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from triagebot.cli import EXIT_ERROR, EXIT_INVALID_TICKET, EXIT_OK, main

VALID_TICKET = {
    "id": "T-1",
    "customer_id": "C-1",
    "subject": "Cannot sign in",
    "body": "My password reset link does nothing.",
}


def write(tmp_path: Path, payload: object, name: str = "ticket.json") -> Path:
    path = tmp_path / name
    path.write_text(
        payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8"
    )
    return path


def test_valid_ticket_exits_zero_and_writes_result(tmp_path: Path) -> None:
    ticket = write(tmp_path, VALID_TICKET)
    out = tmp_path / "result.json"
    assert main(["--ticket", str(ticket), "--out", str(out), "--as-of", "2026-07-31"]) == EXIT_OK

    result = json.loads(out.read_text(encoding="utf-8"))
    assert result["ticket_id"] == "T-1"
    assert result["state"] in {"AUTO_RESOLVED", "ESCALATED"}


def test_result_goes_to_stdout_without_out(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    assert main(["--ticket", str(write(tmp_path, VALID_TICKET))]) == EXIT_OK
    assert json.loads(capsys.readouterr().out)["ticket_id"] == "T-1"


def test_pretty_flag_indents(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    main(["--ticket", str(write(tmp_path, VALID_TICKET)), "--pretty"])
    assert "\n  " in capsys.readouterr().out


@pytest.mark.parametrize(
    ("payload", "expected_field"),
    [
        ({**VALID_TICKET, "body": "   "}, "body"),
        ({**VALID_TICKET, "body": "x" * 9000}, "body"),
        ({**VALID_TICKET, "amount": -5}, "amount"),
        ({**VALID_TICKET, "unexpected": 1}, "unexpected"),
        ({"id": "T-1"}, "customer_id"),
    ],
)
def test_invalid_ticket_exits_two_and_names_the_field(
    tmp_path: Path,
    capsys: pytest.CaptureFixture,
    payload: dict,
    expected_field: str,
) -> None:
    """SC-005: rejected before classification, offending field named."""
    out = tmp_path / "result.json"
    code = main(["--ticket", str(write(tmp_path, payload)), "--out", str(out)])
    assert code == EXIT_INVALID_TICKET
    assert expected_field in capsys.readouterr().err
    assert not out.exists(), "nothing may be written for an invalid ticket"


def test_missing_file_exits_one(tmp_path: Path) -> None:
    assert main(["--ticket", str(tmp_path / "nope.json")]) == EXIT_ERROR


def test_malformed_json_exits_two(tmp_path: Path) -> None:
    assert main(["--ticket", str(write(tmp_path, "{not json"))]) == EXIT_INVALID_TICKET


def test_default_driver_is_offline(tmp_path: Path) -> None:
    """The CLI must not reach the network unless explicitly told to."""
    import sys

    main(["--ticket", str(write(tmp_path, VALID_TICKET))])
    assert "anthropic" not in sys.modules


def test_output_is_reproducible(tmp_path: Path) -> None:
    ticket = write(tmp_path, VALID_TICKET)
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    main(["--ticket", str(ticket), "--out", str(first), "--as-of", "2026-07-31"])
    main(["--ticket", str(ticket), "--out", str(second), "--as-of", "2026-07-31"])
    assert first.read_text(encoding="utf-8") == second.read_text(encoding="utf-8")


def test_example_tickets_all_triage(tmp_path: Path) -> None:
    """The committed examples must stay valid as the models evolve."""
    examples = sorted((Path(__file__).resolve().parents[1] / "examples").glob("ticket_*.json"))
    assert examples, "no example tickets found"
    for example in examples:
        out = tmp_path / f"{example.stem}.result.json"
        assert main(["--ticket", str(example), "--out", str(out), "--as-of", "2026-07-31"]) == EXIT_OK
