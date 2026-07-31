"""测试夹具:现场生成真实的二进制知识文档,不往仓库里塞样例文件。

这些文件在 tmp 目录里生成、用完即弃。摄取模块面对的是真的 .docx/.xlsx/.pdf,
不是 mock —— 文件系统和文件格式在 `ingest` 这个 seam 上属于被测行为本身。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts.docgen import (  # noqa: E402
    write_docx,
    write_pdf,
    write_scanned_pdf,
    write_text,
    write_xlsx,
)


@pytest.fixture
def knowledge_root(tmp_path: Path) -> Path:
    """一个五脏俱全的小知识库:五种格式 + 保密文件夹 + 扫描件 + 不支持的格式。"""
    root = tmp_path / "knowledge"

    write_docx(
        root / "金属" / "金属品类策略.docx",
        ["金属品类策略", "生效日期:2024-03-01", "本品类采用双供应商策略,年度框架协议一年一签。"],
    )
    write_xlsx(
        root / "金属" / "金属合格供应商名录.xlsx",
        [["供应商", "资质", "状态"], ["ACME Metals Ltd", "ISO9001", "合格"], ["华兴金属", "ISO9001", "合格"]],
    )
    write_pdf(
        root / "包材" / "瓦楞纸箱规格书.pdf",
        ["瓦楞纸箱规格书 Corrugated Carton Spec", "生效日期: 2023-11-15", "边压强度 ECT >= 32 lb/in"],
    )
    write_text(root / "流程" / "请购流程.md", "# 请购流程\n\n1. 提交请购单\n2. 品类经理审批\n3. 采购下单\n")
    write_text(root / "流程" / "常见问题.txt", "问:框架协议在哪查?答:在合同系统里查。\n")

    # 保密文件夹:整份保密(ADR-0005)
    write_xlsx(
        root / "保密" / "金属" / "2024金属供应商报价单.xlsx",
        [["供应商", "单价(元/吨)", "折扣"], ["ACME Metals Ltd", "4820", "3%"], ["华兴金属", "4950", "1%"]],
    )
    write_docx(
        root / "保密" / "包材" / "包材谈判策略.docx",
        ["包材谈判策略", "底价不得低于每平米 2.10 元,首轮报价从 2.60 元起谈。"],
    )

    # 读不进去的两类
    write_scanned_pdf(root / "合同" / "扫描合同.pdf")
    (root / "杂项").mkdir(parents=True, exist_ok=True)
    (root / "杂项" / "旧系统导出.dat").write_bytes(b"\x00\x01\x02binary junk")

    return root
