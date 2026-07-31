"""领域类型。术语一律按 CONTEXT.md。"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum, StrEnum


class AbstainReason(StrEnum):
    """弃答的原因。取值是封闭集合,别再往代码里撒裸字符串。"""

    NO_VISIBLE_DOCUMENTS = "no_visible_documents"
    NO_DOCUMENTS_SELECTED = "no_documents_selected"
    DRIVER_ERROR = "driver_error"
    INVALID_JSON = "invalid_json"
    MODEL_ABSTAINED = "model_abstained"
    NO_CITATIONS = "no_citations"
    UNKNOWN_DOCUMENT = "unknown_document"
    QUOTE_NOT_FOUND = "quote_not_found"


class SkipReason(StrEnum):
    """一个文件没被读进知识库的原因。"""

    UNSUPPORTED_FORMAT = "unsupported_format"
    SCANNED_PDF = "scanned_pdf"
    EMPTY = "empty"
    UNREADABLE = "unreadable"


class Role(str, Enum):
    """提问人的角色。只有这两种。"""

    BUYER = "采购员"
    CATEGORY_MANAGER = "品类经理"


@dataclass(frozen=True)
class Asker:
    """提问人:发起一次提问的具体的人,携带角色与负责品类。"""

    employee_id: str
    name: str
    role: Role
    categories: tuple[str, ...] = ()
    contact: str = ""

    def manages(self, category: str) -> bool:
        return self.role is Role.CATEGORY_MANAGER and category in self.categories


@dataclass(frozen=True)
class Document:
    """一份知识文档,连同摄取时算出来的目录信息。"""

    document_id: str
    title: str
    category: str
    restricted: bool
    text: str
    source_path: str
    effective_date: dt.date | None = None
    summary: str = ""

    @property
    def char_count(self) -> int:
        return len(self.text)


@dataclass(frozen=True)
class SkippedFile:
    """一个没能读进来的文件。reason 是机器可读的码,detail 是给人看的。"""

    path: str
    reason: str
    detail: str


@dataclass(frozen=True)
class IngestReport:
    """摄取报告:读进去了哪些、没读进去哪些、各自因为什么。"""

    ingested: tuple[str, ...] = ()
    skipped: tuple[SkippedFile, ...] = ()

    @property
    def ingested_count(self) -> int:
        return len(self.ingested)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped)


@dataclass(frozen=True)
class Library:
    """知识库 = 知识目录 + 摄取报告。"""

    documents: tuple[Document, ...] = ()
    report: IngestReport = field(default_factory=IngestReport)

    def by_id(self, document_id: str) -> Document | None:
        for doc in self.documents:
            if doc.document_id == document_id:
                return doc
        return None


@dataclass(frozen=True)
class Citation:
    """出处:指向具体知识文档具体位置的引用。"""

    document_id: str
    quote: str


@dataclass(frozen=True)
class Handover:
    """转人工:把问题交给一个具体的人。"""

    to_name: str
    to_contact: str
    category: str
    is_fallback: bool = False


@dataclass(frozen=True)
class Answer:
    """一次提问的结果。弃答是一种正确的结果,不是故障。"""

    text: str
    citations: tuple[Citation, ...] = ()
    abstained: bool = False
    abstain_reason: str = ""
    restricted_notice: str = ""
    withheld_titles: tuple[str, ...] = ()
    handover: Handover | None = None
