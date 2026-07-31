"""Slice 10 — Python and TypeScript share one schema, and drift fails the suite offline."""

from __future__ import annotations

import json
from pathlib import Path

from triagebot.schema_export import SCHEMA_DIR, render_schemas

EXPECTED_FILES = {"ticket.schema.json", "triage_result.schema.json"}


def test_the_export_produces_a_schema_for_each_public_model() -> None:
    assert set(render_schemas()) == EXPECTED_FILES


def test_the_committed_schema_matches_the_current_models() -> None:
    for filename, rendered in render_schemas().items():
        committed = (SCHEMA_DIR / filename).read_text("utf-8")
        assert committed == rendered, (
            f"{filename} is out of date — run `python scripts/export_schema.py`"
        )


def test_the_verdict_schema_names_the_fields_consumers_depend_on() -> None:
    schema = json.loads(render_schemas()["triage_result.schema.json"])
    properties = schema["properties"]

    for field in (
        "ticket_id",
        "category",
        "priority",
        "sentiment",
        "confidence",
        "recommended_action",
        "escalated_to_human",
        "injection_detected",
        "stage",
        "rationale",
    ):
        assert field in properties


def test_the_verdict_schema_forbids_unknown_fields() -> None:
    schema = json.loads(render_schemas()["triage_result.schema.json"])

    assert schema["additionalProperties"] is False


def test_the_export_writes_the_files_it_renders(tmp_path: Path) -> None:
    from triagebot.schema_export import export_schemas

    written = export_schemas(tmp_path)

    assert {path.name for path in written} == EXPECTED_FILES
    for path in written:
        assert json.loads(path.read_text("utf-8"))["title"]
