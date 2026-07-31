"""把宪法变成会失败的断言。

这些不是"风格检查"——它们守的是四条 NON-NEGOTIABLE 原则里的三条。
如果有人以后为了省事引了个向量库、或者在核心里直接 import 厂商 SDK、
或者把品类名硬编码进代码,这里会红。
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src" / "procurement_bot"
VENDOR_DRIVER = SRC / "llm" / "anthropic_driver.py"


def _source_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def test_no_vector_database_dependency():
    """宪法原则 V:用户明确否决了向量库方案("太重了")。"""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    for banned in (
        "faiss", "chroma", "pgvector", "qdrant", "weaviate", "milvus",
        "sentence-transformers", "embedding", "langchain", "llama-index",
    ):
        assert banned not in text, f"pyproject 里出现了被宪法禁止的依赖:{banned}"


def test_core_does_not_import_vendor_sdks():
    """宪法原则 IV:业务逻辑只依赖驱动抽象,不碰厂商 SDK。"""
    pattern = re.compile(r"^\s*(?:import|from)\s+(anthropic|openai|google\.|cohere|mistralai)",
                         re.MULTILINE)
    offenders = [
        f.relative_to(ROOT)
        for f in _source_files()
        if f != VENDOR_DRIVER and pattern.search(f.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"这些文件不该 import 厂商 SDK:{offenders}"


def test_vendor_driver_imports_lazily():
    """真实驱动的 import 必须在函数体内,这样没装 SDK 也能导入核心。"""
    lines = VENDOR_DRIVER.read_text(encoding="utf-8").splitlines()
    for line in lines:
        if re.match(r"^import\s+anthropic", line):
            raise AssertionError("anthropic 必须延迟导入(放在函数体内)")
    assert any("        import anthropic" in line for line in lines)


def test_domain_knowledge_is_not_hardcoded():
    """宪法原则 III:品类/供应商/人名只能来自语料和名单,不能写死在代码里。

    知识落在库里,不落在代码里 —— 否则换个部门就得改程序。
    """
    domain_terms = [
        "电解铜", "紧固件", "铝锭", "张伟", "王芳", "陈国华", "赵强",
        "Cu-CATH", "SUP-01", "达克罗",
    ]
    offenders: list[str] = []
    for f in _source_files():
        text = f.read_text(encoding="utf-8")
        for term in domain_terms:
            if term in text:
                offenders.append(f"{f.relative_to(ROOT)}: {term}")
    assert not offenders, f"领域知识被硬编码进了源码:{offenders}"


def test_passage_has_no_sensitivity_field():
    """INV-P2:片段不得独立持有密级,只能通过 doc_id 继承。

    让"某处忘了继承密级"这种越权在类型上就不可表达。
    """
    from dataclasses import fields

    from procurement_bot.models import Passage

    assert "sensitivity" not in {f.name for f in fields(Passage)}


def test_offline_guard_is_active():
    """禁网 fixture 真的生效了吗?—— 自我检验。"""
    import socket

    import pytest

    with pytest.raises(Exception) as exc:
        socket.create_connection(("example.com", 80), timeout=1)
    assert "测试禁止联网" in str(exc.value)


def test_every_source_file_is_reachable_from_the_plan():
    """plan.md 里列出的模块和实际源码目录保持一致(防止悄悄长出新模块)。"""
    plan = (
        ROOT / "specs" / "001-procurement-knowhow-bot" / "plan.md"
    ).read_text(encoding="utf-8")
    for f in _source_files():
        if f.name == "__init__.py":
            continue
        assert f.name in plan, f"{f.name} 没有出现在 plan.md 的结构里"
