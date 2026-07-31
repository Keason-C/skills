from pathlib import Path

from pkbot.models import PUBLIC, Document, Section
from pkbot.retrieval import build_context, matched_term_count, rank, tokenize


def _doc(doc_id, sections):
    return Document(doc_id, doc_id, Path(doc_id), PUBLIC, None, tuple(sections))


def test_tokenize_handles_cjk_bigrams_and_latin():
    toks = tokenize("紧固件 M8x30")
    assert "紧固" in toks and "固件" in toks and "m8x30" in toks


def test_rank_puts_matching_document_first():
    docs = [
        _doc("a.md", [Section("全文", "办公用品采购流程说明")]),
        _doc("b.md", [Section("全文", "不锈钢紧固件规格与供应商")]),
    ]
    ranked = rank("紧固件供应商有哪些", docs)
    assert ranked[0][0].doc_id == "b.md"
    assert ranked[0][1] > 0


def test_unrelated_documents_score_zero_and_are_dropped():
    docs = [_doc("a.md", [Section("全文", "办公用品采购流程")])]
    pack = build_context("电子元器件价格", docs, budget=1000)
    assert pack.docs == ()


def test_oversized_document_falls_back_to_matching_sections():
    big = _doc(
        "big.md",
        [
            Section("第 1 章", "无关内容" * 200),
            Section("第 9 章", "紧固件技术规格要求" * 5),
        ],
    )
    pack = build_context("紧固件技术规格", [big], budget=200)
    assert len(pack.docs) == 1
    loaded = pack.docs[0]
    assert loaded.partial is True
    assert [s.locator for s in loaded.sections] == ["第 9 章"]


def test_document_too_big_for_any_section_is_reported_as_skipped():
    huge = _doc("huge.md", [Section("全文", "紧固件" * 500)])
    pack = build_context("紧固件", [huge], budget=100)
    assert pack.docs == ()
    assert pack.skipped_oversized == ("huge.md",)


def test_full_document_loaded_when_it_fits():
    doc = _doc("small.md", [Section("全文", "紧固件供应商:甲乙丙")])
    pack = build_context("紧固件供应商", [doc], budget=10_000)
    assert pack.docs[0].partial is False
    assert pack.doc_ids == {"small.md"}


def test_empty_question_returns_nothing():
    doc = _doc("a.md", [Section("全文", "紧固件")])
    assert rank("", [doc]) == []
    assert build_context("", [doc]).docs == ()


def test_matched_term_count_counts_distinct_query_terms():
    doc = _doc("a.md", [Section("全文", "成本构成中原材料约占 62%")])
    # "材料" 命中,其余不命中 → 只有 1 个 distinct 词
    assert matched_term_count("包装材料的验收标准是什么", doc) == 1
    strong = _doc("b.md", [Section("全文", "供应商甲的报价与谈判结果")])
    assert matched_term_count("供应商甲谈到什么报价", strong) >= 3
