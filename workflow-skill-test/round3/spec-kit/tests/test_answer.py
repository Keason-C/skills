"""端到端问答行为(US1:有据可答 / 无据转人工 / 拦住幻觉)。"""

from __future__ import annotations

from procurement_bot.core import AskService, UNKNOWN_TEXT
from procurement_bot.llm.base import LLMResponse
from procurement_bot.llm.mock import ExplodingDriver, KeywordMockDriver, ScriptedDriver
from procurement_bot.models import AnswerStatus, EscalationReason


def test_grounded_question_is_answered_with_citations(service):
    answer = service.ask("电解铜这个品类归谁管", "P1001")
    assert answer.status is AnswerStatus.ANSWERED
    assert answer.citations, "answered 必须带出处(宪法原则 I)"
    assert "张伟" in answer.text
    assert answer.citations[0].doc_name == "品类管理手册-电解铜.md"
    assert "品类归属" in answer.citations[0].locator


def test_citation_excerpt_comes_from_the_corpus_not_the_model(service):
    """出处由代码从原文截取,模型伪造不了(D-05)。"""
    answer = service.ask("电解铜这个品类归谁管", "P1001")
    citation = answer.citations[0]
    passage = next(
        p for p in service.index.passages if p.passage_id == citation.passage_id
    )
    assert passage.text.startswith(citation.excerpt[:20])


def test_question_about_missing_material_abstains(service):
    answer = service.ask("钛合金紧固件的规格要求是什么", "P1001")
    assert answer.status is AnswerStatus.UNKNOWN
    assert answer.citations == ()
    assert UNKNOWN_TEXT in answer.text


def test_abstention_creates_an_escalation(service):
    answer = service.ask("钛合金紧固件的规格要求是什么", "P1001")
    assert answer.escalation_id
    escalations = service._escalations.all()
    assert escalations[-1].reason is EscalationReason.NO_COVERAGE
    assert escalations[-1].escalation_id == answer.escalation_id


def test_abstention_tells_the_user_who_to_ask(service):
    answer = service.ask("钛合金紧固件的规格要求是什么", "P1001")
    assert {c.employee_id for c in answer.contacts} == {"P1003"}  # 紧固件 → 王芳


def test_lying_driver_is_blocked(service):
    """模型编造出处 → 整个答案作废,降级为"不知道"。"""
    service.driver = ScriptedDriver(
        default=LLMResponse("电解铜由王五负责。", ("完全不存在的文件.md#0",), True)
    )
    answer = service.ask("电解铜这个品类归谁管", "P1001")
    assert answer.status is AnswerStatus.UNKNOWN
    assert answer.fabrication_blocked
    assert "王五" not in answer.text
    assert service._escalations.all()[-1].reason is EscalationReason.FABRICATION_BLOCKED


def test_insufficient_flag_discards_the_body(service):
    service.driver = ScriptedDriver(
        default=LLMResponse("我猜大概是张三吧。", ("品类管理手册-电解铜.md#0",), False)
    )
    answer = service.ask("电解铜这个品类归谁管", "P1001")
    assert answer.status is AnswerStatus.UNKNOWN
    assert "张三" not in answer.text


def test_driver_crash_degrades_to_unknown(service):
    """CA-7:模型服务挂了也不能把异常抛给调用方。"""
    service.driver = ExplodingDriver()
    answer = service.ask("电解铜这个品类归谁管", "P1001")
    assert answer.status is AnswerStatus.UNKNOWN


def test_empty_corpus_answers_nothing(tmp_path, roster_path):
    corpus = tmp_path / "empty_corpus"
    corpus.mkdir()
    state = tmp_path / "state"
    AskService.build_index(corpus, state)
    svc = AskService.load(corpus, roster_path, state, KeywordMockDriver())
    answer = svc.ask("电解铜归谁管", "P1001")
    assert answer.status is AnswerStatus.UNKNOWN
    assert answer.escalation_id


def test_partial_context_notice(tmp_path, roster_path):
    """FR-006:资料被截断时必须显式声明(analyze 发现 E3 补的用例)。"""
    corpus = tmp_path / "big"
    corpus.mkdir()
    for i in range(20):
        (corpus / f"供应商{i:02d}.md").write_text(
            f"# 供应商资料 {i}\n\n## 概况\n\n本供应商编号 SUP-{i:03d},主营电解铜加工。\n",
            encoding="utf-8",
        )
    state = tmp_path / "state"
    AskService.build_index(corpus, state)
    svc = AskService.load(corpus, roster_path, state, KeywordMockDriver(), top_k=3)
    answer = svc.ask("电解铜供应商的概况", "P1001")
    assert answer.partial_context is True
    assert any("只参考了其中相关度最高" in n for n in answer.notices)


def test_answered_status_requires_citations_by_construction():
    """INV-A1 是在类型层强制的,不是靠自觉。"""
    import pytest

    from procurement_bot.models import Answer

    with pytest.raises(ValueError):
        Answer(status=AnswerStatus.ANSWERED, text="没有出处的答案")
