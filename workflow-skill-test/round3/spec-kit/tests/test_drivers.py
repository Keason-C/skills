"""驱动层:确定性与可替换性(宪法原则 IV / contracts/llm-driver.md)。"""

from __future__ import annotations

from procurement_bot.llm.base import LLMDriver, LLMRequest, LLMResponse, PassageView
from procurement_bot.llm.mock import KeywordMockDriver, ScriptedDriver


def _req(question: str, *passages: PassageView) -> LLMRequest:
    return LLMRequest(question=question, passages=passages)


def test_mock_driver_satisfies_the_protocol():
    assert isinstance(KeywordMockDriver(), LLMDriver)
    assert isinstance(ScriptedDriver(), LLMDriver)


def test_mock_answers_from_the_matching_passage():
    r = KeywordMockDriver().generate(
        _req(
            "品类负责人是谁",
            PassageView("a#0", "a.md — § 品类归属", "本品类负责人:张伟。规格另见附件。"),
            PassageView("b#0", "b.md — § 无关", "今天天气不错。"),
        )
    )
    assert r.sufficient and r.cited_passage_ids == ("a#0",)
    assert "张伟" in r.answer_text


def test_mock_declares_insufficient_when_nothing_overlaps():
    r = KeywordMockDriver().generate(
        _req("XYZQQ", PassageView("a#0", "a.md", "完全无关的内容"))
    )
    assert not r.sufficient
    assert r.cited_passage_ids == ()


def test_mock_declares_insufficient_with_no_passages():
    assert not KeywordMockDriver().generate(_req("任何问题")).sufficient


def test_mock_is_deterministic_on_ties():
    """平分时按 passage_id 字典序取小 —— 同样的输入必须给同样的输出。"""
    passages = (
        PassageView("z#0", "z.md", "电解铜相关内容"),
        PassageView("a#0", "a.md", "电解铜相关内容"),
    )
    results = {KeywordMockDriver().generate(_req("电解铜", *passages)).cited_passage_ids
               for _ in range(5)}
    assert results == {("a#0",)}


def test_mock_uses_the_source_label_too():
    """章节标题也参与匹配,和内核的标题加权保持一致。"""
    r = KeywordMockDriver().generate(
        _req(
            "品类归属情况",
            PassageView("a#0", "a.md — § 品类归属", "负责人是张伟。"),
            PassageView("b#0", "b.md — § 其他", "这里没有相关字样。"),
        )
    )
    assert r.cited_passage_ids == ("a#0",)


def test_scripted_driver_can_lie():
    """测试必须能构造一个"会编造出处"的模型,否则防幻觉就无从验证。"""
    driver = ScriptedDriver(
        script={"单价": LLMResponse("胡编的答案", ("根本不存在.md#0",), True)}
    )
    r = driver.generate(_req("电解铜的单价"))
    assert r.cited_passage_ids == ("根本不存在.md#0",)
    assert len(driver.calls) == 1


def test_scripted_driver_default_is_insufficient():
    assert not ScriptedDriver().generate(_req("任何问题")).sufficient
