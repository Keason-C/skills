"""唯一的权限闸门。

前置于一切检索——不可见的文档从不进入打分,也从不进入上下文,
所以模型物理上不可能"不小心"引用到它们。
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import (
    CONFIDENTIAL,
    ROLE_ADMIN,
    ROLE_CATEGORY_MANAGER,
    Document,
    Library,
    User,
)


@dataclass(frozen=True)
class Visibility:
    visible: tuple[Document, ...]
    hidden: tuple[Document, ...]


def _can_see(user: User, doc: Document) -> bool:
    if doc.classification != CONFIDENTIAL:
        return True
    if user.role == ROLE_ADMIN:
        return True
    if user.role == ROLE_CATEGORY_MANAGER and doc.category is not None:
        return doc.category in user.categories
    return False


def partition(user: User, library: Library) -> Visibility:
    visible: list[Document] = []
    hidden: list[Document] = []
    for doc in library.documents:
        (visible if _can_see(user, doc) else hidden).append(doc)
    return Visibility(tuple(visible), tuple(hidden))


def owners_for_category(roster: dict[str, User], category: str | None) -> tuple[str, ...]:
    """找出负责某品类的品类经理姓名,用于"这个问题该找谁"的提示。"""
    if not category:
        return ()
    return tuple(
        user.name
        for user in roster.values()
        if user.role == ROLE_CATEGORY_MANAGER and category in user.categories
    )
