"""从管理员维护的 CSV 名单解析身份。名单里没有的工号一律拒绝服务。

刻意不做"未知用户按最低权限处理":身份含糊比拒绝服务危险得多。
"""

from __future__ import annotations

import csv
from pathlib import Path

from .models import ROLE_ADMIN, ROLE_BUYER, ROLE_CATEGORY_MANAGER, User

VALID_ROLES = {ROLE_BUYER, ROLE_CATEGORY_MANAGER, ROLE_ADMIN}
REQUIRED_COLUMNS = ["工号", "姓名", "角色", "负责品类"]


class RosterError(Exception):
    """名单文件本身有问题(不存在、缺列、角色非法)。"""


class UnknownUserError(Exception):
    """工号不在名单里。"""


def load_roster(path: Path) -> dict[str, User]:
    if not path.exists():
        raise RosterError(f"找不到名单文件:{path}。请管理员创建后再使用。")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise RosterError(f"名单文件缺少列:{'、'.join(missing)}")
        roster: dict[str, User] = {}
        for row in reader:
            employee_id = (row["工号"] or "").strip()
            if not employee_id:
                continue
            role = (row["角色"] or "").strip()
            if role not in VALID_ROLES:
                raise RosterError(
                    f"工号 {employee_id} 的角色 '{role}' 不认识,"
                    f"只能填:{'、'.join(sorted(VALID_ROLES))}"
                )
            raw_categories = (row["负责品类"] or "").strip()
            categories = tuple(c.strip() for c in raw_categories.split(";") if c.strip())
            roster[employee_id] = User(
                employee_id, (row["姓名"] or "").strip(), role, categories
            )
    return roster


def get_user(roster: dict[str, User], employee_id: str) -> User:
    user = roster.get(employee_id.strip())
    if user is None:
        raise UnknownUserError(
            f"工号 {employee_id} 不在名单里,无法确认你的身份和权限。"
            f"请联系管理员把你加进名单。"
        )
    return user
