"""确定性的离线驱动。演示与全部自动化测试都跑在这上面(宪法原则 IV)。

``KeywordMockDriver`` 不是玩具:它让整个系统在没有网络、没有 API key 的情况下
端到端可跑、可演示、可断言精确输出。真实驱动只是把它换掉。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..retrieval import tokenize
from .base import LLMRequest, LLMResponse, PassageView

_SENTENCE_SPLIT = re.compile(r"(?<=[。!?;\n])|(?<=[.!?])\s+")


def _sentences(text: str) -> list[str]:
    parts = [s.strip() for s in _SENTENCE_SPLIT.split(text) if s and s.strip()]
    return parts or [text.strip()]


class KeywordMockDriver:
    """按 contracts/llm-driver.md 的四条规则作答。无随机性。"""

    name = "mock"

    def generate(self, request: LLMRequest) -> LLMResponse:
        q_tokens = set(tokenize(request.question))
        if not q_tokens or not request.passages:
            return LLMResponse(answer_text="", cited_passage_ids=(), sufficient=False)

        best: tuple[int, str, PassageView] | None = None
        for pv in request.passages:
            # 出处标签里含章节标题,和内核的"标题命中加权"保持一致
            haystack = set(tokenize(pv.text)) | set(tokenize(pv.source_label))
            overlap = len(q_tokens & haystack)
            if overlap == 0:
                continue
            # 平分时按 passage_id 字典序取小 —— 保证确定性
            key = (-overlap, pv.passage_id)
            if best is None or key < (-best[0], best[1]):
                best = (overlap, pv.passage_id, pv)

        if best is None:
            return LLMResponse(answer_text="", cited_passage_ids=(), sufficient=False)

        _, _, pv = best
        sentences = _sentences(pv.text)
        scored = sorted(
            enumerate(sentences),
            key=lambda item: (-len(q_tokens & set(tokenize(item[1]))), item[0]),
        )
        answer = scored[0][1].strip()
        if not answer:
            return LLMResponse(answer_text="", cited_passage_ids=(), sufficient=False)
        return LLMResponse(
            answer_text=answer, cited_passage_ids=(pv.passage_id,), sufficient=True
        )


@dataclass
class ScriptedDriver:
    """测试专用:按问题子串匹配返回预设响应。

    可以用来构造一个**会说谎的模型** —— 返回不存在的引用 ID,
    用来验证 verifier 真的拦得住(D-05)。
    """

    name: str = "scripted"
    script: dict[str, LLMResponse] = field(default_factory=dict)
    default: LLMResponse | None = None
    calls: list[LLMRequest] = field(default_factory=list)

    def generate(self, request: LLMRequest) -> LLMResponse:
        self.calls.append(request)
        for needle, response in self.script.items():
            if needle in request.question:
                return response
        if self.default is not None:
            return self.default
        return LLMResponse(answer_text="", cited_passage_ids=(), sufficient=False)


class ExplodingDriver:
    """总是抛异常的驱动,用来验证 CA-7(驱动异常降级为 unknown,而不是崩)。"""

    name = "exploding"

    def generate(self, request: LLMRequest) -> LLMResponse:  # noqa: ARG002
        raise RuntimeError("模型服务不可用")
