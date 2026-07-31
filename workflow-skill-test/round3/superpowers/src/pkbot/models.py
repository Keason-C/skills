"""所有跨模块共享的数据结构。全部 frozen,便于在纯函数之间安全传递。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PUBLIC = "public"
CONFIDENTIAL = "confidential"

ROLE_BUYER = "采购员"
ROLE_CATEGORY_MANAGER = "品类经理"
ROLE_ADMIN = "管理员"


def estimate_tokens(text: str) -> int:
    """确定性 token 估算:中文一字约一 token,英文偏保守。够用且可测。"""
    return len(text)


@dataclass(frozen=True)
class Section:
    """文档里的一个小节,locator 是给人看的出处标记。"""

    locator: str
    text: str

    @property
    def token_estimate(self) -> int:
        return estimate_tokens(self.text)


@dataclass(frozen=True)
class Document:
    """一份可读文档。密级与品类由所在文件夹决定,不由内容推断。"""

    doc_id: str
    title: str
    path: Path
    classification: str
    category: str | None
    sections: tuple[Section, ...]

    @property
    def token_estimate(self) -> int:
        return sum(s.token_estimate for s in self.sections)

    @property
    def full_text(self) -> str:
        return "\n".join(s.text for s in self.sections)


@dataclass(frozen=True)
class UnreadableFile:
    """读不了的文件,reason 必须是人话。"""

    path: Path
    reason: str


@dataclass(frozen=True)
class Library:
    documents: tuple[Document, ...]
    unreadable: tuple[UnreadableFile, ...]


@dataclass(frozen=True)
class User:
    employee_id: str
    name: str
    role: str
    categories: tuple[str, ...]


@dataclass(frozen=True)
class LoadedDoc:
    """本次真实装进上下文的文档。partial 表示只装了部分小节。"""

    doc_id: str
    title: str
    sections: tuple[Section, ...]
    partial: bool


@dataclass(frozen=True)
class ContextPack:
    docs: tuple[LoadedDoc, ...]
    skipped_oversized: tuple[str, ...]

    @property
    def doc_ids(self) -> set[str]:
        return {d.doc_id for d in self.docs}


@dataclass(frozen=True)
class Citation:
    doc_id: str
    locator: str


@dataclass(frozen=True)
class Answer:
    status: str
    text: str
    citations: tuple[Citation, ...] = ()
    notes: tuple[str, ...] = ()
