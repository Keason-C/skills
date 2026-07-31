"""人员名单:权限判定与转人工路由的共同数据源(FR-011a / FR-014a)。

格式见 contracts/corpus-layout.md。需求方原话是"你给我个格式我填",所以这里
用 CSV —— 他能用 Excel 直接编辑。

错误处理原则:**宁可报错也不降级**。名单填错时抛异常并指明行号,而不是悄悄
把人当成最低权限——后者会变成"某某突然查不到东西"的玄学故障。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from .errors import RosterFormatError, UnknownRequesterError
from .models import ALL_CATEGORIES, Requester, Role

REQUIRED_COLUMNS = ["工号", "姓名", "角色", "负责品类"]
CATEGORY_SEPARATORS = ";;、,"

# 模板里用的是占位名字和占位品类,请整行替换成你们自己的人和品类。
# (领域知识不进代码 —— 宪法原则 III)
TEMPLATE = """工号,姓名,角色,负责品类
E001,张三,采购员,
E002,李四,品类经理,品类甲
E003,王五,品类经理,品类乙;品类丙
E100,赵六,采购负责人,*
"""


def _split_categories(raw: str) -> frozenset[str]:
    if not raw.strip():
        return frozenset()
    parts = [raw]
    for sep in CATEGORY_SEPARATORS:
        parts = [piece for part in parts for piece in part.split(sep)]
    return frozenset(p.strip() for p in parts if p.strip())


@dataclass(frozen=True)
class Roster:
    by_id: dict[str, Requester]

    @property
    def categories(self) -> frozenset[str]:
        """名单中出现过的全部品类(不含 `*`)。供转人工的品类识别使用。"""
        out: set[str] = set()
        for r in self.by_id.values():
            out |= {c for c in r.categories if c != ALL_CATEGORIES}
        return frozenset(out)

    def lookup(self, employee_id: str) -> Requester:
        try:
            return self.by_id[employee_id]
        except KeyError as exc:
            raise UnknownRequesterError(
                f"工号 {employee_id} 不在人员名单中。请检查 roster.csv。"
            ) from exc

    def route_for(self, category: str | None) -> tuple[Requester, ...]:
        """该找谁(FR-014a)。识别不出品类、或该品类无人认领 → 兜底给采购负责人。"""
        if category:
            owners = tuple(
                sorted(
                    (
                        r
                        for r in self.by_id.values()
                        if r.role is Role.CATEGORY_MANAGER and category in r.categories
                    ),
                    key=lambda r: r.employee_id,
                )
            )
            if owners:
                return owners
        return self.fallback

    @property
    def fallback(self) -> tuple[Requester, ...]:
        return tuple(
            sorted(
                (r for r in self.by_id.values() if r.role is Role.PROCUREMENT_LEAD),
                key=lambda r: r.employee_id,
            )
        )


def load_roster(path: Path | str) -> Roster:
    p = Path(path)
    if not p.is_file():
        raise RosterFormatError(f"人员名单文件不存在:{p}")

    # utf-8-sig 兼容 Excel 存出来的带 BOM 的 CSV
    with p.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        fieldnames = [f.strip() for f in (reader.fieldnames or [])]
        missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
        if missing:
            raise RosterFormatError(
                f"人员名单缺少列:{'、'.join(missing)};应为 {'、'.join(REQUIRED_COLUMNS)}"
            )

        by_id: dict[str, Requester] = {}
        for lineno, row in enumerate(reader, start=2):  # 第 1 行是表头
            clean = {k.strip(): (v or "").strip() for k, v in row.items() if k}
            emp = clean.get("工号", "")
            if not emp:
                continue  # 允许空行
            name = clean.get("姓名", "")
            role_raw = clean.get("角色", "")
            try:
                role = Role(role_raw)
            except ValueError as exc:
                raise RosterFormatError(
                    f"第 {lineno} 行:角色「{role_raw}」不合法,"
                    f"只能填 {'、'.join(r.value for r in Role)}"
                ) from exc
            if emp in by_id:
                raise RosterFormatError(f"第 {lineno} 行:工号 {emp} 重复")

            categories = _split_categories(clean.get("负责品类", ""))
            try:
                requester = Requester(
                    employee_id=emp, name=name, role=role, categories=categories
                )
            except ValueError as exc:
                raise RosterFormatError(f"第 {lineno} 行:{exc}") from exc
            by_id[emp] = requester

    if not by_id:
        raise RosterFormatError(f"人员名单为空:{p}")
    return Roster(by_id=by_id)


def detect_category(question: str, categories: frozenset[str]) -> str | None:
    """从问题里认出品类(D-11)。

    词表来自数据(名单 + 保密子目录),**不硬编码任何品类名**(宪法原则 III)。
    最长匹配优先:较长的品类名应该胜过它的子串。
    """
    hits = [c for c in categories if c and c in question]
    if not hits:
        return None
    return max(sorted(hits), key=len)
