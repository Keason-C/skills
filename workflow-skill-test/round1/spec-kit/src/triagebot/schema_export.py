"""Export JSON Schema from the pydantic models (task T053, FR-025).

This is the source of truth for the Python/TypeScript contract. The zod schema on the other
side is generated *from this output* (``ts/scripts/generate-zod.mjs``), never hand-written,
so the two languages cannot silently disagree about the shape of a result.

Output is byte-stable -- sorted keys, fixed indent, trailing newline -- so that
"regenerate and diff" is a meaningful staleness check.

    python -m triagebot.schema_export --out schema/
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .models import Ticket, TriageResult

#: Model -> filename. Add here and both sides pick it up.
EXPORTS: tuple[tuple[type, str], ...] = (
    (TriageResult, "triage_result.schema.json"),
    (Ticket, "ticket.schema.json"),
)


def render(model: type) -> str:
    """Return the byte-stable JSON Schema text for ``model``."""
    schema = model.model_json_schema(mode="serialization")
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def export(out_dir: Path) -> list[Path]:
    """Write every schema into ``out_dir``, returning the paths written."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for model, filename in EXPORTS:
        path = out_dir / filename
        path.write_text(render(model), encoding="utf-8")
        written.append(path)
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="triagebot.schema_export",
        description="Generate JSON Schema for the TriageBot public data contract.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("schema"),
        help="output directory (default: schema/)",
    )
    args = parser.parse_args(argv)

    for path in export(args.out):
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
