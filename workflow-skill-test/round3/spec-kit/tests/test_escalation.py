"""转人工与知识缺口(US3 / FR-013~FR-016 / FR-021)。"""

from __future__ import annotations

import json

from procurement_bot.models import AnswerStatus, EscalationReason, to_jsonable


def test_no_coverage_creates_a_knowledge_gap(service):
    service.ask("钛合金紧固件的规格要求是什么", "P1001")
    report = service.gaps()
    assert [r.question for r in report.knowledge_gaps] == ["钛合金紧固件的规格要求是什么"]
    assert report.permission_requests == ()


def test_permission_denied_is_listed_separately(service):
    """C-G2:权限咨询不是知识缺口,混在一起会让人误以为要去补文档。"""
    service.ask("电解铜的采购单价是多少", "P1001")
    report = service.gaps()
    assert report.knowledge_gaps == ()
    assert [r.question for r in report.permission_requests] == ["电解铜的采购单价是多少"]


def test_gaps_are_ordered_by_frequency(service):
    for _ in range(3):
        service.ask("钛合金紧固件的规格要求是什么", "P1001")
    service.ask("镍板的验收标准是什么", "P1001")

    rows = service.gaps().knowledge_gaps
    assert rows[0].question == "钛合金紧固件的规格要求是什么"
    assert rows[0].count == 3
    assert rows[1].count == 1


def test_same_question_with_different_punctuation_is_one_gap(service):
    service.ask("钛合金紧固件的规格要求是什么", "P1001")
    service.ask("钛合金紧固件的规格要求是什么?", "P1001")
    rows = service.gaps().knowledge_gaps
    assert len(rows) == 1 and rows[0].count == 2


def test_routing_points_to_the_category_owner(service):
    service.ask("钛合金紧固件的规格要求是什么", "P1001")
    assert service.gaps().knowledge_gaps[0].routed_to == ("P1003",)


def test_routing_falls_back_to_the_lead(service):
    """无法识别品类的问题 → 兜底给采购负责人(需求方本人)。"""
    answer = service.ask("镍板的验收标准是什么", "P1001")
    assert [c.employee_id for c in answer.contacts] == ["P9000"]


def test_escalation_record_contains_no_restricted_content(service):
    from conftest import SECRET_PRICE

    service.ask("电解铜的采购单价是多少", "P1001")
    blob = json.dumps(to_jsonable(service._escalations.all()), ensure_ascii=False)
    assert SECRET_PRICE not in blob
    assert "成本构成说明" not in blob


def test_escalation_record_fields(service):
    answer = service.ask("钛合金紧固件的规格要求是什么", "P1001")
    esc = service._escalations.all()[-1]
    assert esc.escalation_id == answer.escalation_id
    assert esc.employee_id == "P1001"
    assert esc.name == "李明"
    assert esc.question_category == "紧固件"
    assert esc.reason is EscalationReason.NO_COVERAGE


def test_audit_record_is_complete(service):
    """FR-021:审计记录字段完整(analyze 发现 E4 补的用例)。"""
    service.ask("电解铜这个品类归谁管", "P1001")
    record = service.audit_tail(1)[0]
    assert record.employee_id == "P1001"
    assert record.question == "电解铜这个品类归谁管"
    assert record.status is AnswerStatus.ANSWERED
    assert record.visible_hit_doc_ids == ("品类管理手册-电解铜.md",)
    # 这个问题里的"电解铜"也出现在受限文档里,所以确实发生了权限过滤 ——
    # FR-021 要求记录的正是"是否发生过权限过滤",这里为 True 是对的。
    assert record.restricted_hit is True
    assert record.fabrication_blocked is False
    assert record.partial_context is False
    assert record.escalation_id is None
    assert record.at is not None


def test_audit_restricted_hit_is_false_when_nothing_was_filtered(service):
    """完全碰不到保密材料的问题,restricted_hit 应为 False。"""
    service.ask("审批流程走几级", "P1001")
    assert service.audit_tail(1)[0].restricted_hit is False


def test_audit_accumulates_across_questions(service):
    service.ask("电解铜这个品类归谁管", "P1001")
    service.ask("钛合金紧固件的规格要求是什么", "P1001")
    assert len(service.audit_tail(50)) == 2
