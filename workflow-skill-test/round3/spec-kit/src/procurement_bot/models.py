"""数据模型。严格对应 specs/001-procurement-knowhow-bot/data-model.md。

设计要点(不是随手写的,改之前请先读 data-model.md 的不变量):

* ``Passage`` **没有** ``sensitivity`` 字段(INV-P2)。密级一律通过 ``doc_id`` 回查
  ``Document`` 得到。这样"某处忘了继承密级"这种越权 bug 在类型上就不可表达。
* ``Answer`` 的不变量由 ``__post_init__`` 强制:没有出处就不允许是 ``answered``。
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# 枚举
# ---------------------------------------------------------------------------


class Sensitivity(str, Enum):
    INTERNAL = "internal"
    RESTRICTED = "restricted"


class Role(str, Enum):
    BUYER = "采购员"
    CATEGORY_MANAGER = "品类经理"
    PROCUREMENT_LEAD = "采购负责人"


class AnswerStatus(str, Enum):
    ANSWERED = "answered"
    UNKNOWN = "unknown"
    DENIED = "denied"


class EscalationReason(str, Enum):
    NO_COVERAGE = "no_coverage"
    PERMISSION_DENIED = "permission_denied"
    FABRICATION_BLOCKED = "fabrication_blocked"


class DateConfidence(str, Enum):
    BODY = "body"
    FILENAME = "filename"
    NONE = "none"


ALL_CATEGORIES = "*"


# ---------------------------------------------------------------------------
# 语料实体
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Document:
    doc_id: str  # 语料根下的相对路径(POSIX),天然唯一
    filename: str
    fmt: str
    sensitivity: Sensitivity
    category: str | None
    effective_date: date | None
    version: str | None
    date_confidence: DateConfidence
    ingested_at: datetime
    title_tokens: tuple[str, ...]

    def __post_init__(self) -> None:
        # INV-D1 / INV-D2
        if self.sensitivity is Sensitivity.INTERNAL and self.category is not None:
            raise ValueError(f"internal 文档不应有 category: {self.doc_id}")


@dataclass(frozen=True)
class Passage:
    passage_id: str  # "{doc_id}#{n}"
    doc_id: str
    locator: str
    text: str
    heading_path: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.text.strip():  # INV-P1
            raise ValueError(f"空片段: {self.passage_id}")


@dataclass(frozen=True)
class RejectedFile:
    path: str
    reason: str  # 人话
    detail: str  # 技术细节
    found_at: datetime


# ---------------------------------------------------------------------------
# 人
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Requester:
    employee_id: str
    name: str
    role: Role
    categories: frozenset[str]

    def __post_init__(self) -> None:
        # INV-Q1 / Q2 / Q3
        if self.role is Role.BUYER and self.categories:
            raise ValueError(f"采购员不应有负责品类: {self.employee_id}")
        if ALL_CATEGORIES in self.categories and self.role is not Role.PROCUREMENT_LEAD:
            raise ValueError(f"只有采购负责人可以使用 '*': {self.employee_id}")
        if self.role is Role.CATEGORY_MANAGER and (
            not self.categories or ALL_CATEGORIES in self.categories
        ):
            raise ValueError(f"品类经理必须有具体的负责品类: {self.employee_id}")

    @property
    def label(self) -> str:
        return f"{self.name}(工号 {self.employee_id})"


# ---------------------------------------------------------------------------
# 问答产物
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Citation:
    passage_id: str
    doc_name: str
    locator: str
    excerpt: str  # 由代码从 Passage 截取,不由模型产生(D-05)


@dataclass(frozen=True)
class ConflictGroup:
    doc_ids: tuple[str, ...]
    resolution: str  # "superseded" | "unresolved"
    primary_doc_id: str | None = None
    superseded_doc_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class Answer:
    status: AnswerStatus
    text: str
    citations: tuple[Citation, ...] = ()
    notices: tuple[str, ...] = ()
    contacts: tuple[Requester, ...] = ()
    conflicts: tuple[ConflictGroup, ...] = ()
    partial_context: bool = False
    escalation_id: str | None = None
    fabrication_blocked: bool = False

    def __post_init__(self) -> None:
        # INV-A1:没有出处就不是答案。这是宪法原则 I 在类型层的落地。
        if self.status is AnswerStatus.ANSWERED and not self.citations:
            raise ValueError("answered 的答案必须带引用(宪法原则 I)")
        # INV-A2
        if self.status is not AnswerStatus.ANSWERED and self.citations:
            raise ValueError("非 answered 的答案不得携带引用")


@dataclass(frozen=True)
class Escalation:
    escalation_id: str
    created_at: datetime
    employee_id: str
    name: str
    role: Role
    question: str
    reason: EscalationReason
    question_category: str | None
    routed_to: tuple[str, ...]


@dataclass(frozen=True)
class AuditRecord:
    at: datetime
    employee_id: str
    role: Role
    question: str
    status: AnswerStatus
    visible_hit_doc_ids: tuple[str, ...]
    restricted_hit: bool  # 只记布尔,绝不记受限文档名(INV-U1)
    fabrication_blocked: bool
    partial_context: bool
    escalation_id: str | None


# ---------------------------------------------------------------------------
# 报表
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IngestReport:
    documents: int
    passages: int
    internal_docs: int
    restricted_docs: int
    restricted_by_category: dict[str, int]
    rejected: tuple[RejectedFile, ...]
    index_path: str


@dataclass(frozen=True)
class GapRow:
    question: str
    count: int
    last_seen: datetime
    routed_to: tuple[str, ...]


@dataclass(frozen=True)
class GapReport:
    knowledge_gaps: tuple[GapRow, ...]
    permission_requests: tuple[GapRow, ...]


# ---------------------------------------------------------------------------
# 序列化
# ---------------------------------------------------------------------------


def to_jsonable(obj: Any) -> Any:
    """把 dataclass / enum / date 递归转成 JSON 可写的结构。"""
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: to_jsonable(getattr(obj, f.name)) for f in dataclasses.fields(obj)}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, (frozenset, set)):
        return sorted(to_jsonable(x) for x in obj)
    if isinstance(obj, (list, tuple)):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}
    return obj


__all__ = [name for name in dir() if not name.startswith("_")]
del field  # 未使用,避免误导
