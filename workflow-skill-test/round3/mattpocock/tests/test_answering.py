"""seam 2:`answer_question` 的接口 —— 主战场。

权限、出处核验、弃答、保密提示、转人工、冲突呈现都在这里测。
唯一被 mock 的东西是 `LlmDriver`(系统边界);其余一律用真东西。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from procurement_qa.answering import answer_question
from procurement_qa.ingest import ingest_library
from procurement_qa.llm import ScriptedDriver
from procurement_qa.model import Asker, Role
from procurement_qa.people import Roster

BUYER = Asker("1001", "李强", Role.BUYER, contact="lq@example.com")
METAL_MANAGER = Asker("2001", "王敏", Role.CATEGORY_MANAGER, ("金属",), "wm@example.com")
PACKAGING_MANAGER = Asker("2002", "赵磊", Role.CATEGORY_MANAGER, ("包材",), "zl@example.com")
BOSS = Asker("9001", "陈总", Role.CATEGORY_MANAGER, (), "cz@example.com")

ROSTER = Roster(askers=(BUYER, METAL_MANAGER, PACKAGING_MANAGER, BOSS), fallback=BOSS)

STRATEGY_ID = "金属/金属品类策略.docx"
QUOTE = "本品类采用双供应商策略"


@pytest.fixture
def library(knowledge_root: Path):
    return ingest_library(knowledge_root)


def _ask(question, driver, library, asker=BUYER):
    return answer_question(
        question=question,
        asker=asker,
        library=library,
        driver=driver,
        roster=ROSTER,
    )


def _answer_payload(answered=True, answer="金属品类走双供应商策略。", citations=None, reason=""):
    return json.dumps(
        {
            "answered": answered,
            "answer": answer,
            "citations": citations if citations is not None else [
                {"document_id": STRATEGY_ID, "quote": QUOTE}
            ],
            "reason": reason,
        },
        ensure_ascii=False,
    )


# --- 票 05:能答上来的问题 -------------------------------------------------


def test_能答的问题返回回答和指向真实文档的出处(library) -> None:
    driver = ScriptedDriver([json.dumps([STRATEGY_ID]), _answer_payload()])

    result = _ask("金属品类是什么策略?", driver, library)

    assert result.abstained is False
    assert "双供应商" in result.text
    assert [c.document_id for c in result.citations] == [STRATEGY_ID]
    assert library.by_id(result.citations[0].document_id) is not None


def test_选材阶段只看到知识目录看不到正文(library) -> None:
    driver = ScriptedDriver([json.dumps([STRATEGY_ID]), _answer_payload()])

    _ask("金属品类是什么策略?", driver, library)

    selection_prompt = driver.prompts[0]
    assert STRATEGY_ID in selection_prompt  # 目录里有它的编号
    assert QUOTE not in selection_prompt  # 但没有正文


def test_作答阶段只含被选中文档的正文(library) -> None:
    driver = ScriptedDriver([json.dumps([STRATEGY_ID]), _answer_payload()])

    _ask("金属品类是什么策略?", driver, library)

    answer_prompt = driver.prompts[1]
    assert QUOTE in answer_prompt
    assert "瓦楞纸箱" not in answer_prompt  # 没被选中的文档不在里面


def test_成功作答时不产生转人工(library) -> None:
    driver = ScriptedDriver([json.dumps([STRATEGY_ID]), _answer_payload()])

    result = _ask("金属品类是什么策略?", driver, library)

    assert result.handover is None


# --- 票 06:弃答与转人工 ---------------------------------------------------


def test_模型返回非法JSON就弃答而不是把异常抛给用户(library) -> None:
    driver = ScriptedDriver([json.dumps([STRATEGY_ID]), "这不是 JSON,是一段闲聊。"])

    result = _ask("金属品类是什么策略?", driver, library)

    assert result.abstained is True
    assert result.abstain_reason == "invalid_json"
    assert "不知道" in result.text


def test_模型编造不存在的文档编号整条回答作废(library) -> None:
    payload = _answer_payload(
        citations=[{"document_id": "金属/根本不存在.docx", "quote": QUOTE}]
    )
    driver = ScriptedDriver([json.dumps([STRATEGY_ID]), payload])

    result = _ask("金属品类是什么策略?", driver, library)

    assert result.abstained is True
    assert result.abstain_reason == "unknown_document"


def test_引文与原文对不上哪怕只差几个字也作废(library) -> None:
    payload = _answer_payload(
        citations=[{"document_id": STRATEGY_ID, "quote": "本品类采用三供应商策略"}]
    )
    driver = ScriptedDriver([json.dumps([STRATEGY_ID]), payload])

    result = _ask("金属品类是什么策略?", driver, library)

    assert result.abstained is True
    assert result.abstain_reason == "quote_not_found"


def test_引文里的空白差异不算对不上(library) -> None:
    payload = _answer_payload(
        citations=[{"document_id": STRATEGY_ID, "quote": "本品类采用\n双供应商 策略"}]
    )
    driver = ScriptedDriver([json.dumps([STRATEGY_ID]), payload])

    result = _ask("金属品类是什么策略?", driver, library)

    assert result.abstained is False


def test_模型自称答不了也走弃答(library) -> None:
    payload = _answer_payload(answered=False, answer="", citations=[], reason="文档里没提")
    driver = ScriptedDriver([json.dumps([STRATEGY_ID]), payload])

    result = _ask("金属的付款账期是多久?", driver, library)

    assert result.abstained is True
    assert result.abstain_reason == "model_abstained"


def test_声称答上来了却一条出处都没有也作废(library) -> None:
    driver = ScriptedDriver([json.dumps([STRATEGY_ID]), _answer_payload(citations=[])])

    result = _ask("金属品类是什么策略?", driver, library)

    assert result.abstained is True
    assert result.abstain_reason == "no_citations"


def test_驱动抛异常就弃答(library) -> None:
    class Broken:
        def complete(self, prompt: str) -> str:
            raise RuntimeError("网络断了")

    result = _ask("金属品类是什么策略?", Broken(), library)

    assert result.abstained is True
    assert result.abstain_reason == "driver_error"


def test_一份可见文档都没有就直接弃答不调用模型(library) -> None:
    from procurement_qa.model import Library

    driver = ScriptedDriver([])
    result = answer_question(
        question="随便问点什么",
        asker=BUYER,
        library=Library(),
        driver=driver,
        roster=ROSTER,
    )

    assert result.abstained is True
    assert result.abstain_reason == "no_visible_documents"
    assert driver.prompts == []


def test_弃答时转给该品类的品类经理(library) -> None:
    driver = ScriptedDriver([json.dumps([STRATEGY_ID]), "坏掉的输出"])

    result = _ask("金属品类的框架协议怎么签?", driver, library)

    assert result.handover is not None
    assert result.handover.to_name == "王敏"
    assert result.handover.to_contact == "wm@example.com"
    assert result.handover.is_fallback is False


def test_品类没人认领时转给兜底接收人(library) -> None:
    driver = ScriptedDriver([json.dumps([]), ""])

    result = _ask("化学品这块归谁管?", driver, library)

    assert result.abstained is True
    assert result.handover.to_name == "陈总"
    assert result.handover.is_fallback is True


# --- 票 07:保密内容明说但不透露 -------------------------------------------


def test_采购员问报价时被明确告知涉密并给出找谁(library) -> None:
    driver = ScriptedDriver([json.dumps([]), ""])

    result = _ask("金属供应商的报价是多少?", driver, library)

    assert result.restricted_notice != ""
    assert "保密" in result.restricted_notice
    assert "王敏" in result.restricted_notice
    assert result.withheld_titles != ()


def test_出现保密提示时被挡下文档的任何文字都不在prompt里(library) -> None:
    driver = ScriptedDriver([json.dumps([]), ""])

    result = _ask("金属供应商的报价是多少?", driver, library)

    assert result.restricted_notice != ""
    everything_sent = "\n".join(driver.prompts)
    assert "4820" not in everything_sent  # 报价单里的单价
    assert "2024金属供应商报价单" not in everything_sent  # 连标题都不在
    assert "底价" not in everything_sent  # 谈判策略里的字


def test_问题与被挡下文档无关时不喊涉密(library) -> None:
    driver = ScriptedDriver([json.dumps([STRATEGY_ID]), _answer_payload()])

    result = _ask("请购流程第一步是什么?", driver, library)

    assert result.restricted_notice == ""
    assert result.withheld_titles == ()


def test_品类经理问自己品类的保密问题正常作答且无提示(library) -> None:
    quote_id = "保密/金属/2024金属供应商报价单.xlsx"
    payload = json.dumps(
        {
            "answered": True,
            "answer": "ACME 报价 4820 元/吨。",
            "citations": [{"document_id": quote_id, "quote": "4820"}],
            "reason": "",
        },
        ensure_ascii=False,
    )
    driver = ScriptedDriver([json.dumps([quote_id]), payload])

    result = _ask("金属供应商的报价是多少?", driver, library, asker=METAL_MANAGER)

    assert result.abstained is False
    assert result.restricted_notice == ""
    assert "4820" in result.text


def test_能答的部分照答保密提示只是附加(library) -> None:
    driver = ScriptedDriver([json.dumps([STRATEGY_ID]), _answer_payload()])

    result = _ask("金属品类什么策略,报价是多少?", driver, library)

    assert result.abstained is False
    assert "双供应商" in result.text
    assert result.restricted_notice != ""


# --- 票 08:新旧说法与冲突 -------------------------------------------------


def test_作答prompt里每份文档都带着它的生效日期(library) -> None:
    driver = ScriptedDriver(
        [json.dumps([STRATEGY_ID, "包材/瓦楞纸箱规格书.pdf"]), _answer_payload()]
    )

    _ask("规格和策略分别是什么?", driver, library)

    assert "2024-03-01" in driver.prompts[1]
    assert "2023-11-15" in driver.prompts[1]


def test_有生效日期的排在无日期的前面日期新的在最前(library) -> None:
    driver = ScriptedDriver(
        [
            json.dumps(["流程/请购流程.md", "包材/瓦楞纸箱规格书.pdf", STRATEGY_ID]),
            _answer_payload(),
        ]
    )

    _ask("都讲了什么?", driver, library)

    prompt = driver.prompts[1]
    pos_2024 = prompt.index("金属品类策略")
    pos_2023 = prompt.index("瓦楞纸箱规格书")
    pos_none = prompt.index("请购流程")
    assert pos_2024 < pos_2023 < pos_none


def test_作答prompt要求并排列出冲突而不是替用户裁决(library) -> None:
    driver = ScriptedDriver([json.dumps([STRATEGY_ID]), _answer_payload()])

    _ask("金属品类是什么策略?", driver, library)

    prompt = driver.prompts[1]
    assert "不一致" in prompt
    assert "不要替" in prompt


def test_两份文档都被引用时两条出处都要通过核验(library) -> None:
    payload = _answer_payload(
        citations=[
            {"document_id": STRATEGY_ID, "quote": QUOTE},
            {"document_id": "包材/瓦楞纸箱规格书.pdf", "quote": "ECT"},
        ]
    )
    driver = ScriptedDriver(
        [json.dumps([STRATEGY_ID, "包材/瓦楞纸箱规格书.pdf"]), payload]
    )

    result = _ask("策略和规格分别是什么?", driver, library)

    assert result.abstained is False
    assert len(result.citations) == 2
