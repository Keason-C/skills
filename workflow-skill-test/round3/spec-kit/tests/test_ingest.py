"""导入管线:密级/品类判定、被拒文件、零静默丢失、幂等。"""

from __future__ import annotations

from pathlib import Path

from procurement_bot.core import AskService
from procurement_bot.ingest.loader import build_index
from procurement_bot.models import Sensitivity


def test_sensitivity_is_decided_by_path(corpus: Path):
    index = build_index(corpus)
    docs = index.docs_by_id
    assert docs["品类管理手册-电解铜.md"].sensitivity is Sensitivity.INTERNAL
    assert docs["保密/电解铜/成本构成说明.md"].sensitivity is Sensitivity.RESTRICTED


def test_category_comes_from_secret_subdirectory(corpus: Path):
    index = build_index(corpus)
    assert index.docs_by_id["保密/电解铜/成本构成说明.md"].category == "电解铜"
    assert index.docs_by_id["保密/紧固件/谈判策略要点.md"].category == "紧固件"


def test_file_directly_under_secret_root_has_no_category(corpus: Path):
    """未归品类的保密文件 → category=None → 只有采购负责人能看(FR-008a)。"""
    index = build_index(corpus)
    assert index.docs_by_id["保密/集团年度成本目标.md"].category is None


def test_internal_documents_never_carry_a_category(corpus: Path):
    index = build_index(corpus)
    for doc in index.documents:
        if doc.sensitivity is Sensitivity.INTERNAL:
            assert doc.category is None


def test_content_keywords_do_not_make_a_file_secret(tmp_path: Path):
    """需求方明确否决"按关键词自动判密":猜错一次就是事故(FR-008)。"""
    root = tmp_path / "c"
    root.mkdir()
    (root / "公开说明.md").write_text(
        "# 说明\n\n这里提到了报价、成本、谈判策略等字样,但文件不在保密文件夹里。\n",
        encoding="utf-8",
    )
    index = build_index(root)
    assert index.docs_by_id["公开说明.md"].sensitivity is Sensitivity.INTERNAL


def test_no_file_is_silently_lost(tmp_path: Path):
    """SC-008 / INV-R1:导入成功 + 未纳入 == 目录下文件总数。"""
    root = tmp_path / "c"
    (root / "sub").mkdir(parents=True)
    (root / "好文件.md").write_text("# 标题\n\n内容内容", encoding="utf-8")
    (root / "sub" / "另一个.txt").write_text("正文", encoding="utf-8")
    (root / "未知.bin").write_bytes(b"\x00\x01binary")
    (root / "坏的.pdf").write_bytes(b"%PDF-1.4 truncated")
    (root / "空的.md").write_text("", encoding="utf-8")

    index = build_index(root)
    on_disk = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
    accounted = {d.doc_id for d in index.documents} | {r.path for r in index.rejected}
    assert accounted == on_disk


def test_corrupt_file_is_reported_and_does_not_break_the_batch(tmp_path: Path):
    root = tmp_path / "c"
    root.mkdir()
    (root / "好文件.md").write_text("# 标题\n\n有用的内容", encoding="utf-8")
    (root / "坏的.pdf").write_bytes(b"%PDF-1.4 broken")
    (root / "未知.bin").write_bytes(b"\x00\x01")

    index = build_index(root)
    assert len(index.documents) == 1  # 好文件仍然进来了
    reasons = {r.path: r.reason for r in index.rejected}
    assert "坏的.pdf" in reasons
    assert "不支持的格式(.bin)" == reasons["未知.bin"]
    for reason in reasons.values():  # 原因必须是人话,不是异常类名
        assert "Error" not in reason and "Traceback" not in reason


def test_ingest_is_idempotent(corpus: Path):
    """INV-I1:同一语料重复导入,产出完全一致(时间戳除外)。"""
    a, b = build_index(corpus), build_index(corpus)
    assert [d.doc_id for d in a.documents] == [d.doc_id for d in b.documents]
    assert [p.passage_id for p in a.passages] == [p.passage_id for p in b.passages]
    assert [p.text for p in a.passages] == [p.text for p in b.passages]
    assert a.idf == b.idf


def test_new_file_is_queryable_after_reingest(
    corpus: Path, roster_path: Path, tmp_path: Path
):
    """SC-004 / FR-019:加一份文件、重跑 ingest,立刻能问到,不需要改代码。

    (analyze 发现 E2 补的用例)
    """
    from procurement_bot.llm.mock import KeywordMockDriver
    from procurement_bot.models import AnswerStatus

    state = tmp_path / ".pbot"
    AskService.build_index(corpus, state)
    svc = AskService.load(corpus, roster_path, state, KeywordMockDriver())
    assert svc.ask("镍板的验收标准是什么", "P1001").status is AnswerStatus.UNKNOWN

    (corpus / "镍板验收标准.md").write_text(
        "# 镍板验收标准\n\n## 验收\n\n镍板验收标准为纯度不低于 99.96%,单张重量 4 至 6 公斤。\n",
        encoding="utf-8",
    )
    AskService.build_index(corpus, state)
    svc2 = AskService.load(corpus, roster_path, state, KeywordMockDriver())
    answer = svc2.ask("镍板的验收标准是什么", "P1001")
    assert answer.status is AnswerStatus.ANSWERED
    assert "镍板验收标准.md" in {c.doc_name for c in answer.citations}


def test_office_temp_files_are_ignored(tmp_path: Path):
    root = tmp_path / "c"
    root.mkdir()
    (root / "正常.md").write_text("# 标题\n\n内容", encoding="utf-8")
    (root / "~$正常.docx").write_bytes(b"office temp")
    index = build_index(root)
    assert [d.doc_id for d in index.documents] == ["正常.md"]
    assert index.rejected == ()
