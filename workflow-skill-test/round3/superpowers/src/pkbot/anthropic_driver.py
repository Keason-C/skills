"""真实 LLM 调用。**只写不跑**。

测试从不实例化本类(tests/test_drivers.py 里有一条断言守着 anthropic 不被 import),
CLI 也需要显式 `--driver anthropic` 才会走到这里。

启用方式:
    uv sync --extra llm
    export ANTHROPIC_API_KEY=...
    uv run pkbot ask "..." --user G0042 --driver anthropic
"""

from __future__ import annotations

DEFAULT_MODEL = "claude-opus-5"


class AnthropicDriver:
    def __init__(self, model: str = DEFAULT_MODEL, max_tokens: int = 4096) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            import anthropic  # 延迟导入:没装 SDK 时不影响其余功能

            self._client = anthropic.Anthropic()
        return self._client

    def complete(self, system: str, user: str) -> str:
        client = self._ensure_client()
        # claude-opus-5 不接受 temperature / top_p / top_k(会 400);
        # thinking 默认即自适应,无需显式传入。
        response = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if response.stop_reason == "refusal":
            # 交给上层的引用校验闸门统一降级为"答不上来",不把拒答当答案。
            return ""
        return "".join(block.text for block in response.content if block.type == "text")
