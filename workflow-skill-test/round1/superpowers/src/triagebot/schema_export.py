"""Export the pydantic models as JSON Schema.

The exported files are the contract between the Python and TypeScript sides.
They are committed to the repository and a test asserts they are up to date, so
a model change that isn't re-exported turns the suite red rather than silently
drifting away from the zod schema on the other side.
"""

from __future__ import annotations

import json
from pathlib import Path

from triagebot.models import Ticket, TriageResult

MODELS = {"ticket": Ticket, "triage_result": TriageResult}


def export_schemas(out_dir: Path) -> dict[str, Path]:
    """Write one ``<name>.schema.json`` per model. Returns name -> path."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for name, model in MODELS.items():
        path = out_dir / f"{name}.schema.json"
        schema = model.model_json_schema()
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written[name] = path
    return written
