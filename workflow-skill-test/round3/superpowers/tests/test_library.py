from pathlib import Path

from pkbot.library import classify_path, scan_library
from pkbot.models import CONFIDENTIAL, PUBLIC


def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_classify_path_rules():
    assert classify_path(Path("public/a.md")) == (PUBLIC, None)
    assert classify_path(Path("registry/b.csv")) == (PUBLIC, None)
    assert classify_path(Path("confidential/紧固件/c.md")) == (CONFIDENTIAL, "紧固件")
    assert classify_path(Path("confidential/d.md")) == (CONFIDENTIAL, None)


def test_scan_collects_documents_and_unreadables(tmp_path):
    _write(tmp_path, "public/流程.md", "# 流程\n先立项。")
    _write(tmp_path, "confidential/紧固件/纪要.md", "# 纪要\n单价下降。")
    (tmp_path / "public" / "扫描件.wps").write_bytes(b"\x00")
    (tmp_path / "roster.csv").write_text("工号,姓名,角色,负责品类\n", encoding="utf-8")

    lib = scan_library(tmp_path)
    assert {d.doc_id for d in lib.documents} == {
        "public/流程.md",
        "confidential/紧固件/纪要.md",
    }
    assert [u.path.name for u in lib.unreadable] == ["扫描件.wps"]


def test_roster_file_is_not_a_document(tmp_path):
    (tmp_path / "roster.csv").write_text("工号,姓名,角色,负责品类\n", encoding="utf-8")
    _write(tmp_path, "public/a.md", "# A\nhello")
    lib = scan_library(tmp_path)
    assert all("roster" not in d.doc_id for d in lib.documents)
    assert all("roster" not in u.path.name for u in lib.unreadable)


def test_missing_root_returns_empty_library(tmp_path):
    lib = scan_library(tmp_path / "不存在")
    assert lib.documents == () and lib.unreadable == ()
