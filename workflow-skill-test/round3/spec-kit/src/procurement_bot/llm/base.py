"""LLM 驱动接口(宪法原则 IV / contracts/llm-driver.md)。

业务逻辑只依赖这里的三个 dataclass 和一个 Protocol,不 import 任何厂商 SDK。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True)
class PassageView:
    """交给模型看的片段。模型引用时必须原样回填 ``passage_id``。"""

    passage_id: str
    source_label: str
    text: str


@dataclass(frozen=True)
class LLMRequest:
    question: str
    passages: tuple[PassageView, ...]


@dataclass(frozen=True)
class LLMResponse:
    answer_text: str
    cited_passage_ids: tuple[str, ...]
    sufficient: bool


@runtime_checkable
class LLMDriver(Protocol):
    name: str

    def generate(self, request: LLMRequest) -> LLMResponse: ...
