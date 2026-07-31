"""权限:本系统唯一的安全边界。

**过滤发生在模型之前**(ADR-0002)。这不是"让模型别说",而是让保密内容
压根不出现在发给模型的字符串里。整个系统里只有这一个地方决定"谁能看见什么",
它是纯函数,没有 IO,没有模型调用。
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import Asker, Document, Library


@dataclass(frozen=True)
class Visibility:
    """一次提问的可见性划分。

    `visible` 会被送进 prompt;`withheld` **永远不进任何 prompt**,只在进程内
    参与一次"要不要提示涉密"的布尔判断(见 notices.py)。
    """

    visible: tuple[Document, ...]
    withheld: tuple[Document, ...]


def visible_to(library: Library, asker: Asker) -> Visibility:
    visible: list[Document] = []
    withheld: list[Document] = []
    for doc in library.documents:
        (visible if _can_see(doc, asker) else withheld).append(doc)
    return Visibility(visible=tuple(visible), withheld=tuple(withheld))


def _can_see(doc: Document, asker: Asker) -> bool:
    if not doc.restricted:
        return True
    # 保密文档只对"负责该品类的品类经理"可见 —— 边界按品类切,不按职级切。
    return asker.manages(doc.category)
