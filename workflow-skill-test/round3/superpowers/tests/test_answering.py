import json

from pkbot.answering import answer_question, parse_response, render_context
from pkbot.drivers import MockDriver
from pkbot.models import ContextPack, LoadedDoc, Section

PACK = ContextPack(
    docs=(
        LoadedDoc(
            "public/规范.md",
            "不锈钢紧固件采购规范",
            (Section("第 4 节", "螺栓须符合 GB/T 5783。"),),
            False,
        ),
    ),
    skipped_oversized=(),
)


def _reply(**kw):
    return json.dumps(kw, ensure_ascii=False)


def test_valid_answer_with_good_citation_passes():
    driver = MockDriver(
        [
            _reply(
                status="answered",
                answer="须符合 GB/T 5783。",
                citations=[{"doc_id": "public/规范.md", "locator": "第 4 节"}],
            )
        ]
    )
    ans = answer_question(driver, "螺栓规格要求是什么", PACK)
    assert ans.status == "answered"
    assert ans.citations[0].doc_id == "public/规范.md"


def test_fabricated_citation_is_downgraded_to_no_answer():
    """闸门核心:引用了没装载的文档,答案再漂亮也作废。"""
    driver = MockDriver(
        [
            _reply(
                status="answered",
                answer="须符合 ISO 9001。",
                citations=[{"doc_id": "public/根本不存在.md", "locator": "第 1 节"}],
            )
        ]
    )
    ans = answer_question(driver, "螺栓规格要求是什么", PACK)
    assert ans.status == "no_answer"
    assert any("引用" in n for n in ans.notes)


def test_answer_without_citation_is_downgraded():
    driver = MockDriver([_reply(status="answered", answer="我觉得是这样。", citations=[])])
    assert answer_question(driver, "问题", PACK).status == "no_answer"


def test_malformed_json_is_downgraded_not_leaked():
    driver = MockDriver(["这不是 JSON,是模型随口说的一段话"])
    ans = answer_question(driver, "问题", PACK)
    assert ans.status == "no_answer"
    assert "这不是 JSON" not in ans.text


def test_model_says_no_answer_is_respected():
    driver = MockDriver([_reply(status="no_answer", answer="", citations=[])])
    assert answer_question(driver, "问题", PACK).status == "no_answer"


def test_empty_pack_short_circuits_without_calling_model():
    driver = MockDriver([])
    ans = answer_question(driver, "问题", ContextPack((), ()))
    assert ans.status == "no_answer"
    assert driver.calls == []


def test_partial_and_skipped_documents_are_disclosed():
    pack = ContextPack(
        docs=(LoadedDoc("a.md", "招标文件", (Section("第 9 章", "紧固件规格"),), True),),
        skipped_oversized=("超大报价表",),
    )
    driver = MockDriver(
        [
            _reply(
                status="answered",
                answer="见第 9 章。",
                citations=[{"doc_id": "a.md", "locator": "第 9 章"}],
            )
        ]
    )
    ans = answer_question(driver, "紧固件规格", pack)
    assert any("招标文件" in n and "部分" in n for n in ans.notes)
    assert any("超大报价表" in n for n in ans.notes)


def test_parse_response_strips_code_fence():
    assert parse_response('```json\n{"status": "no_answer"}\n```') == {
        "status": "no_answer"
    }


def test_render_context_labels_documents_with_doc_id():
    text = render_context(PACK)
    assert "public/规范.md" in text and "第 4 节" in text


def test_non_dict_citation_entry_is_rejected():
    driver = MockDriver(
        [_reply(status="answered", answer="内容", citations=["public/规范.md"])]
    )
    assert answer_question(driver, "问题", PACK).status == "no_answer"


def test_rejection_note_never_echoes_the_claimed_doc_id():
    """安全:模型报出的 doc_id 可能是保密文档路径,绝不能原样回显给用户。"""
    driver = MockDriver(
        [
            _reply(
                status="answered",
                answer="每件 12 元。",
                citations=[
                    {"doc_id": "confidential/紧固件/2025年度谈判纪要.md", "locator": "三"}
                ],
            )
        ]
    )
    ans = answer_question(driver, "报价多少", PACK)
    assert ans.status == "no_answer"
    joined = ans.text + " ".join(ans.notes)
    assert "confidential" not in joined
    assert "谈判纪要" not in joined
    assert any("引用" in n for n in ans.notes)
