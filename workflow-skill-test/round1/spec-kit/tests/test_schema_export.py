"""JSON Schema export -- scenario V27 (task T055).

FR-025: the published contract must be generated from the same definitions Python validates
against. These tests are the staleness detector on the Python side; `ts/test/generated.test.ts`
is the one on the TypeScript side.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from triagebot import ActionKind, Category, GuardRule, Language, Priority, Sentiment, TriageState
from triagebot.schema_export import EXPORTS, export, render
from triagebot.models import Ticket, TriageResult

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "schema"


@pytest.fixture(scope="module")
def result_schema() -> dict:
    return json.loads((SCHEMA_DIR / "triage_result.schema.json").read_text(encoding="utf-8"))


# --- Staleness ------------------------------------------------------------------------


@pytest.mark.parametrize(("model", "filename"), EXPORTS, ids=lambda x: getattr(x, "__name__", x))
def test_committed_schema_matches_freshly_generated(model: type, filename: str) -> None:
    """V27: a model change that skips regeneration fails the build here."""
    committed = (SCHEMA_DIR / filename).read_text(encoding="utf-8")
    assert committed == render(model), f"{filename} is stale - run: python -m triagebot.schema_export"


def test_render_is_byte_stable() -> None:
    """'Regenerate and diff' only means something if generation is deterministic."""
    assert render(TriageResult) == render(TriageResult)


def test_export_writes_every_declared_file(tmp_path: Path) -> None:
    written = export(tmp_path)
    assert {p.name for p in written} == {filename for _, filename in EXPORTS}
    for path in written:
        json.loads(path.read_text(encoding="utf-8"))


def test_module_runs_as_a_script(tmp_path: Path) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "triagebot.schema_export", "--out", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert (tmp_path / "triage_result.schema.json").exists()


# --- Content ---------------------------------------------------------------------------


def test_every_enum_member_is_published(result_schema: dict) -> None:
    """A member missing here would be silently rejected by the TypeScript consumer."""
    defs = result_schema["$defs"]
    for enum_cls, name in [
        (Category, "Category"),
        (Priority, "Priority"),
        (Sentiment, "Sentiment"),
        (ActionKind, "ActionKind"),
        (GuardRule, "GuardRule"),
        (Language, "Language"),
        (TriageState, "TriageState"),
    ]:
        published = set(defs[name]["enum"])
        assert published == {member.value for member in enum_cls}, f"{name} drifted"


def test_required_fields_match_the_model(result_schema: dict) -> None:
    optional = {
        name
        for name, field in TriageResult.model_fields.items()
        if not field.is_required()
    }
    assert set(result_schema["required"]) == set(TriageResult.model_fields) - optional


def test_schema_forbids_extra_properties(result_schema: dict) -> None:
    """`extra="forbid"` has to survive the crossing, or the TS side would accept junk."""
    assert result_schema["additionalProperties"] is False
    assert result_schema["$defs"]["GuardFinding"]["additionalProperties"] is False


def test_numeric_bounds_survive_the_crossing(result_schema: dict) -> None:
    confidence = result_schema["properties"]["confidence"]
    assert confidence["minimum"] == 0.0
    assert confidence["maximum"] == 1.0
    llm_calls = result_schema["properties"]["llm_calls"]
    assert (llm_calls["minimum"], llm_calls["maximum"]) == (1, 2)


def test_ticket_schema_publishes_its_limits() -> None:
    schema = json.loads((SCHEMA_DIR / "ticket.schema.json").read_text(encoding="utf-8"))
    assert schema["additionalProperties"] is False
    assert schema["properties"]["body"]["maxLength"] == Ticket.model_fields["body"].metadata[0].max_length
