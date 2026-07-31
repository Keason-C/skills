"""防幻觉校验器(宪法原则 I / research.md D-05)。

核心思想:**假定模型会说谎,用确定性代码去验。**

我们能验的:引用的片段是否真的存在于本次提供的材料里。
我们验不了的:模型是否正确理解了那段材料。后者的缓解手段是把原文摘录与答案
并排展示让人一眼可核 —— 这个残余风险在 README 的"能力边界"里对用户明说了,
不假装已经解决(spec FR-004)。
"""

from __future__ import annotations

from dataclasses import dataclass

from .llm.base import LLMRequest, LLMResponse


@dataclass(frozen=True)
class VerifyResult:
    ok: bool
    reason: str = ""
    fabrication_blocked: bool = False
    cited_ids: tuple[str, ...] = ()


def check(request: LLMRequest, response: LLMResponse) -> VerifyResult:
    if not response.sufficient:
        # 即使模型顺手写了正文,也一律丢弃(LD-2)
        return VerifyResult(ok=False, reason="模型声明材料不足")

    if not response.cited_passage_ids:
        return VerifyResult(ok=False, reason="答案没有引用任何来源")

    if not response.answer_text.strip():
        return VerifyResult(ok=False, reason="答案正文为空")

    allowed = {pv.passage_id for pv in request.passages}
    unknown = [pid for pid in response.cited_passage_ids if pid not in allowed]
    if unknown:
        # 这才是真正危险的情况:模型编了一个来源。
        return VerifyResult(
            ok=False,
            reason=f"引用了不存在的来源:{', '.join(sorted(unknown))}",
            fabrication_blocked=True,
        )

    # 去重但保持模型给出的顺序
    seen: set[str] = set()
    ordered: list[str] = []
    for pid in response.cited_passage_ids:
        if pid not in seen:
            seen.add(pid)
            ordered.append(pid)
    return VerifyResult(ok=True, cited_ids=tuple(ordered))
