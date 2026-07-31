"""JSON Schema export — the contract the TypeScript side validates against.

The committed files under `schema/` are generated from the pydantic models. A test regenerates
and compares them, so changing a model without re-exporting fails the suite offline rather than
surfacing later as a broken consumer.
"""

from __future__ import annotations

import json
from pathlib import Path

from triagebot.models import Ticket, TriageResult

SCHEMA_DIR = Path(__file__).resolve().parents[2] / "schema"

_EXPORTS = {
    "ticket.schema.json": Ticket,
    "triage_result.schema.json": TriageResult,
}


def render_schemas() -> dict[str, str]:
    """Render each public model's JSON Schema as the exact text that belongs on disk."""
    return {
        filename: json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
        for filename, model in _EXPORTS.items()
    }


def export_schemas(directory: Path | None = None) -> list[Path]:
    """Write the rendered schemas, returning the paths written."""
    target = directory or SCHEMA_DIR
    target.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    for filename, rendered in render_schemas().items():
        path = target / filename
        path.write_text(rendered, encoding="utf-8")
        written.append(path)
    return written
