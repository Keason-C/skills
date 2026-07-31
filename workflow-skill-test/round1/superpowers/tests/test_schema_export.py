import json
from pathlib import Path

from triagebot.models import Category, Priority, Sentiment
from triagebot.schema_export import export_schemas

REPO_ROOT = Path(__file__).parent.parent


def test_export_writes_both_schema_files(tmp_path):
    written = export_schemas(tmp_path)
    assert (tmp_path / "ticket.schema.json").exists()
    assert (tmp_path / "triage_result.schema.json").exists()
    assert set(written) == {"ticket", "triage_result"}


def test_exported_result_schema_lists_every_category(tmp_path):
    export_schemas(tmp_path)
    schema = json.loads((tmp_path / "triage_result.schema.json").read_text())
    assert set(schema["$defs"]["Category"]["enum"]) == {c.value for c in Category}


def test_exported_result_schema_lists_every_priority(tmp_path):
    export_schemas(tmp_path)
    schema = json.loads((tmp_path / "triage_result.schema.json").read_text())
    assert set(schema["$defs"]["Priority"]["enum"]) == {p.value for p in Priority}


def test_exported_result_schema_lists_every_sentiment(tmp_path):
    export_schemas(tmp_path)
    schema = json.loads((tmp_path / "triage_result.schema.json").read_text())
    assert set(schema["$defs"]["Sentiment"]["enum"]) == {s.value for s in Sentiment}


def test_exported_result_schema_requires_the_escalation_flag(tmp_path):
    export_schemas(tmp_path)
    schema = json.loads((tmp_path / "triage_result.schema.json").read_text())
    assert "escalated_to_human" in schema["required"]


def test_exported_result_schema_forbids_extra_properties(tmp_path):
    export_schemas(tmp_path)
    schema = json.loads((tmp_path / "triage_result.schema.json").read_text())
    assert schema["additionalProperties"] is False


def test_committed_schema_is_up_to_date(tmp_path):
    export_schemas(tmp_path)
    for name in ("ticket", "triage_result"):
        committed = json.loads((REPO_ROOT / "schema" / f"{name}.schema.json").read_text())
        fresh = json.loads((tmp_path / f"{name}.schema.json").read_text())
        assert committed == fresh, f"{name}.schema.json is stale — re-run scripts/export_schema.py"


def test_committed_sample_result_is_valid_against_the_model():
    from triagebot.models import TriageResult

    sample = json.loads((REPO_ROOT / "ts" / "test" / "fixtures" / "valid-result.json").read_text())
    assert TriageResult(**sample).ticket_id == sample["ticket_id"]
