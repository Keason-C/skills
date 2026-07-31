"""人员名单解析与转人工路由(FR-011a / FR-014a)。"""

from __future__ import annotations

import pytest

from procurement_bot.errors import RosterFormatError, UnknownRequesterError
from procurement_bot.models import Role
from procurement_bot.roster import detect_category, load_roster

GOOD = """工号,姓名,角色,负责品类
P1001,李明,采购员,
P1002,张伟,品类经理,电解铜
P1005,赵强,品类经理,电解铜;铝锭
P9000,陈国华,采购负责人,*
"""


def _write(tmp_path, text, name="roster.csv", encoding="utf-8"):
    p = tmp_path / name
    p.write_text(text, encoding=encoding)
    return p


def test_three_roles_parse(tmp_path):
    r = load_roster(_write(tmp_path, GOOD))
    assert r.lookup("P1001").role is Role.BUYER
    assert r.lookup("P1002").role is Role.CATEGORY_MANAGER
    assert r.lookup("P9000").role is Role.PROCUREMENT_LEAD


def test_multiple_categories_split_on_semicolon(tmp_path):
    r = load_roster(_write(tmp_path, GOOD))
    assert r.lookup("P1005").categories == frozenset({"电解铜", "铝锭"})


def test_bom_is_tolerated(tmp_path):
    """Excel 存出来的 CSV 带 BOM,必须能读(D-10)。"""
    r = load_roster(_write(tmp_path, GOOD, encoding="utf-8-sig"))
    assert r.lookup("P1002").name == "张伟"


def test_buyer_with_category_is_rejected_with_line_number(tmp_path):
    bad = "工号,姓名,角色,负责品类\nP1001,李明,采购员,电解铜\n"
    with pytest.raises(RosterFormatError) as exc:
        load_roster(_write(tmp_path, bad))
    assert "第 2 行" in str(exc.value)


def test_invalid_role_is_rejected_with_line_number(tmp_path):
    bad = "工号,姓名,角色,负责品类\nP1001,李明,经理,电解铜\n"
    with pytest.raises(RosterFormatError) as exc:
        load_roster(_write(tmp_path, bad))
    assert "第 2 行" in str(exc.value) and "经理" in str(exc.value)


def test_star_only_allowed_for_lead(tmp_path):
    bad = "工号,姓名,角色,负责品类\nP1002,张伟,品类经理,*\n"
    with pytest.raises(RosterFormatError):
        load_roster(_write(tmp_path, bad))


def test_missing_column_is_rejected(tmp_path):
    bad = "工号,姓名,角色\nP1001,李明,采购员\n"
    with pytest.raises(RosterFormatError) as exc:
        load_roster(_write(tmp_path, bad))
    assert "负责品类" in str(exc.value)


def test_duplicate_employee_id_is_rejected(tmp_path):
    bad = GOOD + "P1002,另一个张伟,品类经理,铝锭\n"
    with pytest.raises(RosterFormatError):
        load_roster(_write(tmp_path, bad))


def test_unknown_employee_raises_not_silent_downgrade(tmp_path):
    """未知工号必须报错,不能悄悄降级成最小权限(CA-6 / D-10)。"""
    r = load_roster(_write(tmp_path, GOOD))
    with pytest.raises(UnknownRequesterError):
        r.lookup("P9999")


def test_route_to_category_owner(tmp_path):
    r = load_roster(_write(tmp_path, GOOD))
    owners = {x.employee_id for x in r.route_for("电解铜")}
    assert owners == {"P1002", "P1005"}


def test_route_falls_back_to_lead(tmp_path):
    r = load_roster(_write(tmp_path, GOOD))
    assert [x.employee_id for x in r.route_for("没人认领的品类")] == ["P9000"]
    assert [x.employee_id for x in r.route_for(None)] == ["P9000"]


def test_detect_category_prefers_longest_match():
    cats = frozenset({"铜", "电解铜"})
    assert detect_category("电解铜归谁管", cats) == "电解铜"


def test_detect_category_returns_none_when_absent():
    assert detect_category("今天天气怎么样", frozenset({"电解铜"})) is None
