"""知识目录长出摘要 —— 两段式选材(ADR-0001)能工作的前提。

摘要由 LlmDriver 生成;测试里一律用 ScriptedDriver(ADR-0004),永不触网。
"""

from __future__ import annotations

from pathlib import Path

from procurement_qa.ingest import ingest_library
from procurement_qa.llm import ScriptedDriver
from procurement_qa.summarise import make_summariser


class BrokenDriver:
    def complete(self, prompt: str) -> str:
        raise RuntimeError("模型服务挂了")


def test_摄取后每份文档都有摘要(knowledge_root: Path) -> None:
    driver = ScriptedDriver(default="这是一句话摘要。")

    library = ingest_library(knowledge_root, summariser=make_summariser(driver))

    assert all(doc.summary == "这是一句话摘要。" for doc in library.documents)


def test_驱动报错时摘要为空但摄取不中断(knowledge_root: Path) -> None:
    library = ingest_library(knowledge_root, summariser=make_summariser(BrokenDriver()))

    assert len(library.documents) == 7
    assert all(doc.summary == "" for doc in library.documents)


def test_假驱动把收到的每一条prompt都记下来供后续断言(knowledge_root: Path) -> None:
    driver = ScriptedDriver(default="摘要")

    ingest_library(knowledge_root, summariser=make_summariser(driver))

    assert len(driver.prompts) == 7
    assert any("金属品类策略" in p for p in driver.prompts)


def test_脚本化驱动按顺序吐出预设回答(knowledge_root: Path) -> None:
    driver = ScriptedDriver(["第一条", "第二条"], default="兜底")

    assert driver.complete("a") == "第一条"
    assert driver.complete("b") == "第二条"
    assert driver.complete("c") == "兜底"


def test_真实驱动存在且可导入但测试里绝不调用它() -> None:
    from procurement_qa.llm import AnthropicDriver

    driver = AnthropicDriver(api_key="不会被使用")

    # 只断言它是个满足 LlmDriver 协议的东西 —— 不碰网络。
    assert callable(driver.complete)
    assert driver.model == "claude-opus-5"
