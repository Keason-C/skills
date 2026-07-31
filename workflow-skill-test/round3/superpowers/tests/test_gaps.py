from datetime import datetime, timedelta, timezone

import pytest

from pkbot.gaps import load_entries, record_question, resolve_gap, weekly_report
from pkbot.models import ROLE_ADMIN, ROLE_BUYER, ROLE_CATEGORY_MANAGER, User

BUYER = User("G0042", "李四", ROLE_BUYER, ())
MANAGER = User("G0007", "王五", ROLE_CATEGORY_MANAGER, ("紧固件",))
NOW = datetime(2026, 7, 31, 10, 0, tzinfo=timezone.utc)


def test_report_counts_total_and_unanswered(tmp_path):
    record_question(tmp_path, BUYER, "问题一", "answered", now=NOW)
    record_question(tmp_path, BUYER, "问题二", "no_answer", now=NOW)
    record_question(tmp_path, BUYER, "问题三", "denied", now=NOW)
    rep = weekly_report(tmp_path, now=NOW)
    assert rep.total == 3
    assert [e["question"] for e in rep.unanswered] == ["问题二", "问题三"]


def test_report_window_excludes_old_entries(tmp_path):
    record_question(tmp_path, BUYER, "上个月的", "no_answer", now=NOW - timedelta(days=40))
    record_question(tmp_path, BUYER, "本周的", "no_answer", now=NOW)
    rep = weekly_report(tmp_path, days=7, now=NOW)
    assert rep.total == 1
    assert rep.unanswered[0]["question"] == "本周的"


def test_resolve_writes_public_faq_document_and_marks_resolved(tmp_path):
    state, lib = tmp_path / "state", tmp_path / "library"
    gap_id = record_question(state, BUYER, "紧固件走什么流程", "no_answer", now=NOW)
    path = resolve_gap(state, lib, gap_id, "走三级审批。", author=MANAGER, now=NOW)
    assert path.is_relative_to(lib / "public" / "faq")
    body = path.read_text(encoding="utf-8")
    assert "紧固件走什么流程" in body and "走三级审批" in body and "王五" in body
    entry = next(e for e in load_entries(state) if e["id"] == gap_id)
    assert entry["resolved"] is True
    assert weekly_report(state, now=NOW).resolved == 1


def test_resolve_can_mark_confidential(tmp_path):
    state, lib = tmp_path / "state", tmp_path / "library"
    gap_id = record_question(state, BUYER, "去年谈到多少钱", "denied", now=NOW)
    path = resolve_gap(
        state,
        lib,
        gap_id,
        "单价 12 元。",
        author=MANAGER,
        confidential=True,
        category="紧固件",
        now=NOW,
    )
    assert path.is_relative_to(lib / "confidential" / "紧固件" / "faq")


def test_confidential_resolution_requires_category(tmp_path):
    state, lib = tmp_path / "state", tmp_path / "library"
    gap_id = record_question(state, BUYER, "q", "no_answer", now=NOW)
    with pytest.raises(ValueError):
        resolve_gap(state, lib, gap_id, "a", author=MANAGER, confidential=True)


def test_resolving_unknown_gap_raises(tmp_path):
    with pytest.raises(KeyError):
        resolve_gap(tmp_path / "state", tmp_path / "lib", "nope", "a", author=MANAGER)


def test_resolved_entries_drop_out_of_unanswered_list(tmp_path):
    state, lib = tmp_path / "state", tmp_path / "library"
    gap_id = record_question(state, BUYER, "问题", "no_answer", now=NOW)
    assert len(weekly_report(state, now=NOW).unanswered) == 1
    resolve_gap(state, lib, gap_id, "答案", author=MANAGER, now=NOW)
    assert weekly_report(state, now=NOW).unanswered == []


# --- 代码审查 C1:路径穿越 ---


def test_category_with_path_traversal_is_rejected(tmp_path):
    state, lib = tmp_path / "state", tmp_path / "library"
    gap_id = record_question(state, BUYER, "q", "no_answer", now=NOW)
    with pytest.raises(ValueError):
        resolve_gap(
            state,
            lib,
            gap_id,
            "内容",
            author=MANAGER,
            confidential=True,
            category="../../../etc",
        )


def test_category_with_separator_is_rejected(tmp_path):
    state, lib = tmp_path / "state", tmp_path / "library"
    gap_id = record_question(state, BUYER, "q", "no_answer", now=NOW)
    with pytest.raises(ValueError):
        resolve_gap(
            state,
            lib,
            gap_id,
            "内容",
            author=MANAGER,
            confidential=True,
            category="紧固件/子目录",
        )


# --- 代码审查 C2:补答授权 ---


def test_buyer_cannot_backfill_documents(tmp_path):
    """采购员读不到保密文档,也不该能往库里写文档。"""
    state, lib = tmp_path / "state", tmp_path / "library"
    gap_id = record_question(state, BUYER, "q", "no_answer", now=NOW)
    with pytest.raises(PermissionError):
        resolve_gap(state, lib, gap_id, "内容", author=BUYER)


def test_manager_cannot_backfill_into_other_category(tmp_path):
    """写权限必须和读权限对称:管紧固件的经理不能往电子元器件里塞东西。"""
    state, lib = tmp_path / "state", tmp_path / "library"
    gap_id = record_question(state, BUYER, "q", "no_answer", now=NOW)
    with pytest.raises(PermissionError):
        resolve_gap(
            state,
            lib,
            gap_id,
            "内容",
            author=MANAGER,
            confidential=True,
            category="电子元器件",
        )


def test_admin_can_backfill_any_category(tmp_path):
    state, lib = tmp_path / "state", tmp_path / "library"
    admin = User("G0001", "赵六", ROLE_ADMIN, ())
    gap_id = record_question(state, BUYER, "q", "no_answer", now=NOW)
    path = resolve_gap(
        state,
        lib,
        gap_id,
        "内容",
        author=admin,
        confidential=True,
        category="电子元器件",
        now=NOW,
    )
    assert path.is_relative_to(lib / "confidential" / "电子元器件" / "faq")
