"""LLM 边界。

真实调用在 anthropic_driver.py,本文件只提供确定性实现,
让全部测试都能离线跑,并且让"引用校验闸门"这类保障可以被真正验证
(靠模型自觉的保障在没有真模型的测试里根本测不出来)。
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMDriver(Protocol):
    def complete(self, system: str, user: str) -> str:
        """给定 system / user 文本,返回模型的原始文本输出。"""
        ...


class MockDriver:
    """按序返回预设响应并记录调用,供单测断言。"""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        assert self._responses, "MockDriver 预设响应已用完,但又被调用了一次"
        return self._responses.pop(0)


class ScriptedDriver:
    """按关键词匹配返回响应,供离线演示使用——不联网、结果可复现。

    match_after 给定时,只在该标记之后的文本里找关键词。
    没有它的话,塞进 user 的资料正文会误触发规则(演示时踩过这个坑)。
    """

    def __init__(
        self,
        rules: list[tuple[str, str]],
        default: str,
        match_after: str | None = None,
    ) -> None:
        self._rules = list(rules)
        self._default = default
        self._match_after = match_after
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        haystack = user
        if self._match_after and self._match_after in user:
            haystack = user.rsplit(self._match_after, 1)[1]
        for keyword, response in self._rules:
            if keyword in haystack:
                return response
        return self._default
