import pytest

from pkbot.identity import RosterError, UnknownUserError, get_user, load_roster
from pkbot.models import ROLE_CATEGORY_MANAGER

ROSTER = (
    "工号,姓名,角色,负责品类\n"
    "G0042,李四,采购员,\n"
    "G0007,王五,品类经理,紧固件;电子元器件\n"
)


def test_load_roster_parses_categories(tmp_path):
    p = tmp_path / "roster.csv"
    p.write_text(ROSTER, encoding="utf-8")
    roster = load_roster(p)
    assert roster["G0007"].role == ROLE_CATEGORY_MANAGER
    assert roster["G0007"].categories == ("紧固件", "电子元器件")
    assert roster["G0042"].categories == ()


def test_unknown_employee_is_rejected(tmp_path):
    p = tmp_path / "roster.csv"
    p.write_text(ROSTER, encoding="utf-8")
    roster = load_roster(p)
    with pytest.raises(UnknownUserError) as exc:
        get_user(roster, "G9999")
    assert "管理员" in str(exc.value)


def test_bad_role_rejected(tmp_path):
    p = tmp_path / "roster.csv"
    p.write_text("工号,姓名,角色,负责品类\nG1,张三,老板,\n", encoding="utf-8")
    with pytest.raises(RosterError):
        load_roster(p)


def test_missing_roster_file_is_clear_error(tmp_path):
    with pytest.raises(RosterError) as exc:
        load_roster(tmp_path / "nope.csv")
    assert "名单" in str(exc.value)
