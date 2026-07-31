"""摄取时给每份知识文档生成一句话摘要。

摘要是"先看目录再看正文"这套选材的燃料(ADR-0001):目录要足够小,又要
足够让模型判断"这份该不该翻开"。摘要在摄取时算一次并落盘,不在每次提问时现算。
"""

from __future__ import annotations

from collections.abc import Callable

from .llm import LlmDriver
from .model import Document

_SUMMARY_HEAD_CHARS = 1200

PROMPT_TEMPLATE = """你在为一个采购部的知识库编目录。

下面是一份知识文档的开头。请用一句中文(不超过 50 字)概括它讲的是什么,
好让别人光看这一句就知道该不该翻开它。只输出这一句话,不要任何前缀或解释。

文件名:{title}
品类:{category}

正文开头:
---
{head}
---"""


def make_summariser(driver: LlmDriver) -> Callable[[Document], str]:
    """返回一个 `Callable[[Document], str]`,交给 `ingest_library(summariser=...)`。"""

    def summarise(doc: Document) -> str:
        return driver.complete(build_summary_prompt(doc)).strip()

    return summarise


def build_summary_prompt(doc: Document) -> str:
    return PROMPT_TEMPLATE.format(
        title=doc.title,
        category=doc.category,
        head=doc.text[:_SUMMARY_HEAD_CHARS],
    )
