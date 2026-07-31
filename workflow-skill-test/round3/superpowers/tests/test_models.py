from pathlib import Path

from pkbot.models import ContextPack, Document, LoadedDoc, Section, estimate_tokens


def test_estimate_tokens_counts_characters():
    assert estimate_tokens("不锈钢紧固件") == 6
    assert estimate_tokens("") == 0


def test_document_token_estimate_sums_sections():
    doc = Document(
        doc_id="public/a.md",
        title="A",
        path=Path("/x/a.md"),
        classification="public",
        category=None,
        sections=(Section("第 1 节", "abc"), Section("第 2 节", "de")),
    )
    assert doc.token_estimate == 5
    assert doc.full_text == "abc\nde"


def test_context_pack_doc_ids():
    pack = ContextPack(
        docs=(LoadedDoc("a", "A", (Section("全文", "x"),), False),),
        skipped_oversized=("大文件",),
    )
    assert pack.doc_ids == {"a"}
