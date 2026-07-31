"""检索层:分词、打分、确定性、未知词 guard。"""

from __future__ import annotations

from procurement_bot.models import Passage
from procurement_bot.retrieval import (
    build_idf,
    corpus_chars,
    score,
    tokenize,
    unknown_content_chars,
)


def _p(pid: str, text: str, heading: tuple[str, ...] = ()) -> Passage:
    return Passage(
        passage_id=pid, doc_id=pid.split("#")[0], locator="正文", text=text,
        heading_path=heading,
    )


def test_cjk_is_split_into_bigrams():
    assert tokenize("电解铜") == ["电解", "解铜"]


def test_single_cjk_char_is_kept():
    assert tokenize("铜 A") == ["铜", "a"]


def test_ascii_is_lowercased_and_split():
    assert tokenize("Cu-CATH-1") == ["cu", "cath", "1"]


def test_relevant_passage_scores_above_irrelevant():
    passages = [
        _p("a.md#0", "电解铜执行 Cu-CATH-1 标准。"),
        _p("b.md#0", "紧固件表面处理采用达克罗。"),
    ]
    idf = build_idf(passages)
    result = score("电解铜的标准是什么", passages, idf)
    assert result[0].passage.passage_id == "a.md#0"


def test_unrelated_question_scores_nothing():
    passages = [_p("a.md#0", "电解铜执行 Cu-CATH-1 标准。")]
    idf = build_idf(passages)
    assert score("XYZ QQQ", passages, idf) == []


def test_heading_hits_are_weighted_higher():
    plain = _p("a.md#0", "内容内容内容规格内容")
    titled = _p("b.md#0", "内容内容内容规格内容", heading=("规格要求",))
    idf = build_idf([plain, titled])
    result = score("规格要求", [plain, titled], idf)
    assert result[0].passage.passage_id == "b.md#0"


def test_scoring_is_deterministic():
    passages = [_p(f"d{i}.md#0", "电解铜标准与供应商清单") for i in range(5)]
    idf = build_idf(passages)
    first = [(sp.passage.passage_id, sp.score) for sp in score("电解铜", passages, idf)]
    second = [(sp.passage.passage_id, sp.score) for sp in score("电解铜", passages, idf)]
    assert first == second


def test_ties_break_on_passage_id_ascending():
    passages = [_p("z.md#0", "电解铜"), _p("a.md#0", "电解铜")]
    idf = build_idf(passages)
    result = score("电解铜", passages, idf)
    assert [sp.passage.passage_id for sp in result] == ["a.md#0", "z.md#0"]


# -- 未知词 guard --------------------------------------------------------------


def test_unknown_content_char_is_detected():
    known = corpus_chars([_p("a.md#0", "紧固件表面处理采用达克罗")])
    assert unknown_content_chars("钛合金紧固件的规格", known) == ["钛", "合", "金", "规", "格"]


def test_common_verbs_are_not_treated_as_unknown_terms():
    """'走''查'这类高频动词不该触发误拦(否则'流程走几级'会被判成不知道)。"""
    known = corpus_chars([_p("a.md#0", "审批流程共三级")])
    assert unknown_content_chars("审批流程走几级", known) == []


def test_question_fully_covered_has_no_unknown_terms():
    known = corpus_chars([_p("a.md#0", "电解铜品类负责人是张伟")])
    assert unknown_content_chars("电解铜品类负责人是谁", known) == []
