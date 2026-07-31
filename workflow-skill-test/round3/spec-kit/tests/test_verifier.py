"""防幻觉校验器(宪法原则 I / D-05)。假定模型会说谎,用确定性代码去验。"""

from __future__ import annotations

from procurement_bot.llm.base import LLMRequest, LLMResponse, PassageView
from procurement_bot.verifier import check

REQUEST = LLMRequest(
    question="电解铜归谁管",
    passages=(
        PassageView("a.md#0", "a.md — § 品类归属", "本品类负责人:张伟。"),
        PassageView("a.md#1", "a.md — § 规格", "执行 Cu-CATH-1 标准。"),
    ),
)


def test_valid_response_passes():
    r = check(REQUEST, LLMResponse("负责人是张伟。", ("a.md#0",), True))
    assert r.ok and r.cited_ids == ("a.md#0",)


def test_insufficient_is_rejected_even_with_body():
    """模型说材料不足时,即使它顺手写了正文也一律丢弃(LD-2)。"""
    r = check(REQUEST, LLMResponse("我猜是张伟。", ("a.md#0",), False))
    assert not r.ok and not r.fabrication_blocked


def test_empty_citations_are_rejected():
    r = check(REQUEST, LLMResponse("负责人是张伟。", (), True))
    assert not r.ok


def test_blank_answer_is_rejected():
    r = check(REQUEST, LLMResponse("   \n ", ("a.md#0",), True))
    assert not r.ok


def test_fabricated_citation_is_blocked():
    """最危险的情况:模型编了一个不存在的来源。"""
    r = check(REQUEST, LLMResponse("负责人是李四。", ("不存在的.md#9",), True))
    assert not r.ok
    assert r.fabrication_blocked
    assert "不存在的.md#9" in r.reason


def test_partially_fabricated_citation_is_blocked():
    """真假混着也不放过 —— 一个假引用就足以让整个答案作废。"""
    r = check(REQUEST, LLMResponse("答案", ("a.md#0", "假的.md#0"), True))
    assert not r.ok and r.fabrication_blocked


def test_duplicate_citations_are_collapsed_in_order():
    r = check(REQUEST, LLMResponse("答案", ("a.md#1", "a.md#0", "a.md#1"), True))
    assert r.cited_ids == ("a.md#1", "a.md#0")
