"""权限:系统唯一的安全边界(ADR-0002)。

纯函数,不碰模型、不碰文件系统。这里定义"谁能看见什么";
"看不见的东西不会进 prompt"由 test_answering.py 直接断言 prompt 字符串来钉死。
"""

from __future__ import annotations

from pathlib import Path

from procurement_qa.access import visible_to
from procurement_qa.ingest import ingest_library
from procurement_qa.model import Asker, Role

BUYER = Asker("1001", "李强", Role.BUYER)
METAL_MANAGER = Asker("2001", "王敏", Role.CATEGORY_MANAGER, ("金属",))
PACKAGING_MANAGER = Asker("2002", "赵磊", Role.CATEGORY_MANAGER, ("包材",))


def _titles(docs) -> set[str]:
    return {d.title for d in docs}


def test_采购员的可见集合里没有任何保密文档(knowledge_root: Path) -> None:
    library = ingest_library(knowledge_root)

    view = visible_to(library, BUYER)

    assert all(doc.restricted is False for doc in view.visible)
    assert "2024金属供应商报价单" not in _titles(view.visible)
    assert "包材谈判策略" not in _titles(view.visible)


def test_品类经理看得到自己品类的保密文档(knowledge_root: Path) -> None:
    library = ingest_library(knowledge_root)

    view = visible_to(library, METAL_MANAGER)

    assert "2024金属供应商报价单" in _titles(view.visible)


def test_品类经理看不到别的品类的保密文档(knowledge_root: Path) -> None:
    library = ingest_library(knowledge_root)

    view = visible_to(library, METAL_MANAGER)

    assert "包材谈判策略" not in _titles(view.visible)
    assert "包材谈判策略" in _titles(view.withheld)


def test_公开文档对所有角色都可见与品类无关(knowledge_root: Path) -> None:
    library = ingest_library(knowledge_root)

    for asker in (BUYER, METAL_MANAGER, PACKAGING_MANAGER):
        titles = _titles(visible_to(library, asker).visible)
        assert {"金属品类策略", "瓦楞纸箱规格书", "请购流程"} <= titles


def test_被挡下的文档以独立集合返回不与可见集合混淆(knowledge_root: Path) -> None:
    library = ingest_library(knowledge_root)

    view = visible_to(library, BUYER)

    assert _titles(view.withheld) == {"2024金属供应商报价单", "包材谈判策略"}
    assert not (_titles(view.visible) & _titles(view.withheld))
    assert len(view.visible) + len(view.withheld) == len(library.documents)
