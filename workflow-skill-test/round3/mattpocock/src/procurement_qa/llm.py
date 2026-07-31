"""模型驱动 seam。

接口只有一个方法:prompt 字符串进,文本出。系统其余部分对"背后是哪个驱动"
一无所知。两个 adapter:

- `AnthropicDriver` —— 真实实现,**写了但从不在测试里跑**(ADR-0004)。
- `ScriptedDriver` —— 确定性假驱动,测试全用它,并记录收到的每一条 prompt,
  好让"保密内容有没有进过 prompt"这种断言可以直接落在字符串上(ADR-0002)。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LlmDriver(Protocol):
    def complete(self, prompt: str) -> str: ...


class DriverError(Exception):
    """驱动调用失败。上层一律收敛到弃答(ADR-0003)。"""


class ScriptedDriver:
    """按预设脚本返回,并录下所有 prompt。"""

    def __init__(self, responses: list[str] | None = None, *, default: str | None = None) -> None:
        self._responses = list(responses or [])
        self._default = default
        self.prompts: list[str] = []

    def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if self._responses:
            return self._responses.pop(0)
        if self._default is not None:
            return self._default
        raise AssertionError("ScriptedDriver 的脚本用完了,但又被调用了一次")


class AnthropicDriver:
    """真实的 Claude 调用。

    写了,但**测试永不执行它** —— 本项目的测试必须全部离线可跑(ADR-0004)。
    体积刻意压到最小:它只做一件事,把字符串换成字符串。
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "claude-opus-5",
        max_tokens: int = 16000,
    ) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._api_key = api_key
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - 只在真跑时才可能触发
                raise DriverError(
                    "没装 anthropic SDK。装它:uv sync --extra llm"
                ) from exc
            self._client = (
                anthropic.Anthropic(api_key=self._api_key)
                if self._api_key
                else anthropic.Anthropic()
            )
        return self._client

    def complete(self, prompt: str) -> str:  # pragma: no cover - 从不在测试中执行
        client = self._ensure_client()
        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
        except Exception as exc:
            raise DriverError(f"调用模型失败:{exc}") from exc

        if getattr(response, "stop_reason", None) == "refusal":
            raise DriverError("模型拒绝回答该请求")

        return "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
