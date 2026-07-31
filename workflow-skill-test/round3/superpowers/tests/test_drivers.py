import sys

import pytest

from pkbot.drivers import LLMDriver, MockDriver, ScriptedDriver


def test_mock_driver_returns_in_order_and_records_calls():
    d = MockDriver(["一", "二"])
    assert d.complete("sys", "u1") == "一"
    assert d.complete("sys", "u2") == "二"
    assert [c[1] for c in d.calls] == ["u1", "u2"]


def test_mock_driver_raises_when_exhausted():
    d = MockDriver(["只有一条"])
    d.complete("s", "u")
    with pytest.raises(AssertionError):
        d.complete("s", "u")


def test_scripted_driver_matches_keyword_else_default():
    d = ScriptedDriver([("紧固件", "命中")], default="兜底")
    assert d.complete("s", "问紧固件的事") == "命中"
    assert d.complete("s", "别的问题") == "兜底"


def test_mock_and_scripted_satisfy_protocol():
    assert isinstance(MockDriver([]), LLMDriver)
    assert isinstance(ScriptedDriver([], "x"), LLMDriver)


def test_anthropic_sdk_is_never_imported_during_tests():
    """工程红线:真实 LLM 调用只写不跑。测试进程里不允许出现 anthropic 模块。"""
    assert "anthropic" not in sys.modules


def test_scripted_driver_can_restrict_matching_to_text_after_marker():
    """演示驱动必须只按"问题"匹配,否则会被塞进 user 的资料正文误触发。"""
    d = ScriptedDriver([("螺栓", "规格答案")], default="兜底", match_after="【问题】")
    payload = "【资料】\n螺栓须符合 GB/T 5783。\n\n【问题】\n不锈钢紧固件归谁管"
    assert d.complete("s", payload) == "兜底"
    payload2 = "【资料】\n无关内容\n\n【问题】\n螺栓规格是什么"
    assert d.complete("s", payload2) == "规格答案"
