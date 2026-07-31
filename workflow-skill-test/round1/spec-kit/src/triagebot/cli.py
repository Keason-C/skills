"""Command line entry point: ``python -m triagebot.cli`` (task T034).

Exit codes are part of the contract (contracts/README.md §3):

===== ==========================================================================
  0   triaged; result written
  2   the ticket failed validation -- field-level errors on stderr, nothing written
  1   unexpected internal error
===== ==========================================================================

The default driver is the deterministic mock, so running this never touches the network
unless ``--driver anthropic`` is passed explicitly.
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

from pydantic import ValidationError

from .models import Ticket
from .pipeline import triage
from .settings import TriageSettings

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_INVALID_TICKET = 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="triagebot",
        description="Triage a customer support ticket. The LLM proposes; rules decide.",
    )
    parser.add_argument("--ticket", required=True, type=Path, help="path to a ticket JSON file")
    parser.add_argument("--out", type=Path, default=None, help="write result JSON here (default: stdout)")
    parser.add_argument("--pretty", action="store_true", help="indent the result JSON")
    parser.add_argument(
        "--driver",
        choices=("mock", "anthropic"),
        default="mock",
        help="classifier to use (default: mock, fully offline)",
    )
    parser.add_argument(
        "--as-of",
        type=date.fromisoformat,
        default=None,
        help="reference date (YYYY-MM-DD) for refund-window arithmetic; defaults to today",
    )
    return parser


def _load_driver(name: str) -> object:
    if name == "anthropic":
        from .drivers.anthropic_driver import AnthropicDriver

        return AnthropicDriver()
    from .drivers.mock import MockDriver

    return MockDriver()


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    try:
        raw = args.ticket.read_text(encoding="utf-8")
    except OSError as exc:
        print(f"error: cannot read {args.ticket}: {exc}", file=sys.stderr)
        return EXIT_ERROR

    # Parsed as JSON rather than dict-splatted: strict models reject Python-side coercion,
    # but accept the natural JSON encodings (models.py module docstring).
    try:
        ticket = Ticket.model_validate_json(raw)
    except ValidationError as exc:
        print("error: ticket failed validation", file=sys.stderr)
        for issue in exc.errors():
            location = ".".join(str(part) for part in issue["loc"]) or "<root>"
            print(f"  {location}: {issue['msg']}", file=sys.stderr)
        return EXIT_INVALID_TICKET

    try:
        result = triage(
            ticket,
            _load_driver(args.driver),  # type: ignore[arg-type]
            TriageSettings(),
            as_of=args.as_of,
        )
    except Exception as exc:  # noqa: BLE001 - CLI boundary turns anything into exit 1
        print(f"error: triage failed: {exc}", file=sys.stderr)
        return EXIT_ERROR

    payload = result.model_dump_json(indent=2 if args.pretty else None)
    if args.out is not None:
        args.out.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)
    return EXIT_OK


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
