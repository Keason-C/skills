"""同主题多版本的裁决 —— 需求方亲自定的规则(FR-005a / FR-005b)。"""

from __future__ import annotations

from procurement_bot.models import AnswerStatus


def test_dated_versions_use_the_newer_one_and_flag_the_old(service):
    """FR-005a:写了生效日期的,按新的答 + 注明另有旧版。"""
    answer = service.ask("采购审批流程走几级", "P1001")
    assert answer.status is AnswerStatus.ANSWERED
    assert "三级" in answer.text
    assert answer.citations[0].doc_name == "采购流程说明.md"
    assert any("另有旧版" in n and "2019" in n for n in answer.notices)


def test_superseded_document_is_not_cited(service):
    answer = service.ask("采购审批流程走几级", "P1001")
    assert "采购流程说明-2019旧版.md" not in {c.doc_name for c in answer.citations}


def test_undated_conflicts_are_shown_side_by_side(service):
    """FR-005b:比不出新旧的,两份并列摆出,机器人不许硬挑。"""
    answer = service.ask("紧固件的表面处理要求", "P1001")
    assert answer.status is AnswerStatus.ANSWERED
    names = {c.doc_name for c in answer.citations}
    assert names == {"规格要求-紧固件.md", "规格要求-紧固件-补充.md"}
    assert "不一致" in answer.text
    assert any("资料不一致" in n for n in answer.notices)


def test_undated_conflict_shows_both_actual_contents(service):
    answer = service.ask("紧固件的表面处理要求", "P1001")
    blob = " ".join(c.excerpt for c in answer.citations)
    assert "达克罗" in blob and "镀锌钝化" in blob


def test_conflict_group_resolution_labels(service):
    answer = service.ask("紧固件的表面处理要求", "P1001")
    assert [g.resolution for g in answer.conflicts] == ["unresolved"]

    answer2 = service.ask("采购审批流程走几级", "P1001")
    assert [g.resolution for g in answer2.conflicts] == ["superseded"]


def test_unrelated_documents_are_not_grouped(service):
    """标题不相似的文档不该被判成"同一主题的多个版本"。"""
    answer = service.ask("电解铜这个品类归谁管", "P1001")
    assert answer.conflicts == ()
    assert answer.notices == ()
