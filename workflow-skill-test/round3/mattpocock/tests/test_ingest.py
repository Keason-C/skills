"""seam 1:`ingest_library` 的接口。

测的是行为:知识库进去,知识目录 + 摄取报告出来。不碰内部函数。
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from procurement_qa.ingest import ingest_library


def _by_title(library, title: str):
    return next(d for d in library.documents if d.title == title)


def test_五种格式的正文都能读出来(knowledge_root: Path) -> None:
    library = ingest_library(knowledge_root)

    assert "双供应商策略" in _by_title(library, "金属品类策略").text
    assert "ACME Metals Ltd" in _by_title(library, "金属合格供应商名录").text
    assert "ECT" in _by_title(library, "瓦楞纸箱规格书").text
    assert "品类经理审批" in _by_title(library, "请购流程").text
    assert "框架协议" in _by_title(library, "常见问题").text


def test_不支持的格式进摄取报告而不是被静默丢弃(knowledge_root: Path) -> None:
    library = ingest_library(knowledge_root)

    skipped = {s.path: s for s in library.report.skipped}
    dat = next(p for p in skipped if p.endswith("旧系统导出.dat"))
    assert skipped[dat].reason == "unsupported_format"
    assert ".dat" in skipped[dat].detail

    assert not any(d.title == "旧系统导出" for d in library.documents)


def test_没有文字层的PDF被单独标成疑似扫描件(knowledge_root: Path) -> None:
    library = ingest_library(knowledge_root)

    scanned = [s for s in library.report.skipped if s.reason == "scanned_pdf"]
    assert len(scanned) == 1
    assert scanned[0].path.endswith("扫描合同.pdf")


def test_保密文件夹下的文档整份算保密其余算公开(knowledge_root: Path) -> None:
    library = ingest_library(knowledge_root)

    assert _by_title(library, "2024金属供应商报价单").restricted is True
    assert _by_title(library, "包材谈判策略").restricted is True
    assert _by_title(library, "金属品类策略").restricted is False
    assert _by_title(library, "金属合格供应商名录").restricted is False


def test_品类从目录名推断保密文件夹下取下一级目录名(knowledge_root: Path) -> None:
    library = ingest_library(knowledge_root)

    assert _by_title(library, "金属品类策略").category == "金属"
    assert _by_title(library, "瓦楞纸箱规格书").category == "包材"
    # 保密/金属/xxx.xlsx —— 品类是"金属",不是"保密"
    assert _by_title(library, "2024金属供应商报价单").category == "金属"
    assert _by_title(library, "包材谈判策略").category == "包材"


def test_正文里写了生效日期就抽出来没写就是空(knowledge_root: Path) -> None:
    library = ingest_library(knowledge_root)

    assert _by_title(library, "金属品类策略").effective_date == dt.date(2024, 3, 1)
    assert _by_title(library, "瓦楞纸箱规格书").effective_date == dt.date(2023, 11, 15)
    assert _by_title(library, "请购流程").effective_date is None


def test_文档编号是相对路径便于出处指回原文件(knowledge_root: Path) -> None:
    library = ingest_library(knowledge_root)

    assert _by_title(library, "金属品类策略").document_id == "金属/金属品类策略.docx"


def test_空文件不进目录并写进报告(tmp_path: Path) -> None:
    root = tmp_path / "k"
    (root / "流程").mkdir(parents=True)
    (root / "流程" / "空的.md").write_text("   \n\n", encoding="utf-8")

    library = ingest_library(root)

    assert library.documents == ()
    assert [s.reason for s in library.report.skipped] == ["empty"]


def test_摄取报告统计读进去和没读进去的份数(knowledge_root: Path) -> None:
    library = ingest_library(knowledge_root)

    assert library.report.ingested_count == 7
    assert library.report.skipped_count == 2
