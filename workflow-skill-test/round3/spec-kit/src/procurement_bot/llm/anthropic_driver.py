"""真实模型驱动 —— **只写不跑**(宪法原则 IV)。

- 本模块 **MUST NOT** 被任何自动化测试导入执行。`tests/test_constitution.py`
  会断言除本文件外的源码不出现厂商 SDK 的 import。
- `anthropic` 的 import 放在函数内部,这样即使没装 SDK,核心也能正常导入。

**重要**:下面提示词里对模型的约束是**第二道防线**。第一道防线是
`verifier.check` 的确定性校验 —— 它不依赖模型是否听话。
"""

from __future__ import annotations

import json
import os

from .base import LLMRequest, LLMResponse

SYSTEM_PROMPT = """你是采购部的知识助手。请严格遵守:
1. 只能使用【参考材料】中的内容作答,不得使用任何常识或推测补充。
2. 如果材料不足以回答问题,把 sufficient 设为 false,不要勉强作答。
3. citations 必须是【参考材料】中给出的 passage_id 原文,不得编造。
4. 不要在 answer 里书写"出处""来源"等字样——出处由系统自动附加。

只输出一个 JSON 对象,不要任何其他文字:
{"sufficient": true/false, "answer": "……", "citations": ["<passage_id>", ...]}
"""

DEFAULT_MODEL = "claude-sonnet-4-6"


def _render_passages(request: LLMRequest) -> str:
    blocks = [
        f"<材料 passage_id=\"{pv.passage_id}\" 出处=\"{pv.source_label}\">\n"
        f"{pv.text}\n</材料>"
        for pv in request.passages
    ]
    return "\n\n".join(blocks)


class AnthropicDriver:
    name = "anthropic"

    def __init__(
        self, model: str = DEFAULT_MODEL, api_key: str | None = None, max_tokens: int = 1024
    ) -> None:
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.max_tokens = max_tokens

    def generate(self, request: LLMRequest) -> LLMResponse:
        import anthropic  # 延迟导入:核心模块不依赖 SDK 是否安装

        client = anthropic.Anthropic(api_key=self.api_key)
        message = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"【问题】\n{request.question}\n\n"
                        f"【参考材料】\n{_render_passages(request)}"
                    ),
                }
            ],
        )
        text = "".join(
            block.text for block in message.content if getattr(block, "type", "") == "text"
        ).strip()

        try:
            data = json.loads(_strip_fence(text))
        except json.JSONDecodeError:
            # 模型没按格式回 → 当作"材料不足",由 verifier 降级为"不知道"。
            # 宁可漏答,不可错答。
            return LLMResponse(answer_text="", cited_passage_ids=(), sufficient=False)

        return LLMResponse(
            answer_text=str(data.get("answer", "")),
            cited_passage_ids=tuple(str(c) for c in data.get("citations", []) or ()),
            sufficient=bool(data.get("sufficient", False)),
        )


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines)
    return stripped
