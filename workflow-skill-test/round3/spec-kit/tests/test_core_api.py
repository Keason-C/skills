"""内核 API 契约(宪法原则 VI / contracts/core-api.md)。"""

from __future__ import annotations

import json
import sys

import pytest

from procurement_bot.core import AskService
from procurement_bot.errors import IndexMissingError, UnknownRequesterError
from procurement_bot.llm.mock import KeywordMockDriver
from procurement_bot.models import AnswerStatus, to_jsonable


def test_ca1_identity_comes_only_from_the_parameter(service, monkeypatch):
    """CA-1:不得从环境变量 / argv 里读身份。"""
    monkeypatch.setenv("USER", "P9000")
    monkeypatch.setenv("PBOT_USER", "P9000")
    monkeypatch.setattr(sys, "argv", ["pbot", "--user", "P9000"])
    answer = service.ask("电解铜的采购单价是多少", "P1001")
    assert answer.status is AnswerStatus.DENIED  # 仍然按参数里的 P1001 判定


def test_ca2_ask_prints_nothing(service, capsys):
    service.ask("电解铜这个品类归谁管", "P1001")
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""


def test_ca3_answer_is_json_serialisable(service):
    answer = service.ask("电解铜这个品类归谁管", "P1001")
    blob = json.dumps(to_jsonable(answer), ensure_ascii=False)
    assert json.loads(blob)["status"] == "answered"


def test_ca4_ask_is_idempotent(service):
    a = service.ask("电解铜这个品类归谁管", "P1001")
    b = service.ask("电解铜这个品类归谁管", "P1001")
    assert (a.status, a.text) == (b.status, b.text)
    assert [c.passage_id for c in a.citations] == [c.passage_id for c in b.citations]


def test_ca6_unknown_employee_raises_instead_of_downgrading(service):
    with pytest.raises(UnknownRequesterError):
        service.ask("电解铜这个品类归谁管", "P0000")


def test_missing_index_raises_a_clear_error(tmp_path, corpus, roster_path):
    with pytest.raises(IndexMissingError) as exc:
        AskService.load(corpus, roster_path, tmp_path / "nope", KeywordMockDriver())
    assert "pbot ingest" in str(exc.value)


def test_core_is_channel_agnostic(service):
    """完全不经 CLI,直接用内核跑通"提问 → 答案 → 缺口清单"全流程。

    这是"以后能接企业微信"这句承诺的可执行版本(analyze 发现 E4 相邻的 T060)。
    """
    ok = service.ask("电解铜这个品类归谁管", "P1001")
    assert ok.status is AnswerStatus.ANSWERED

    miss = service.ask("钛合金紧固件的规格要求是什么", "P1001")
    assert miss.status is AnswerStatus.UNKNOWN

    report = service.gaps()
    assert report.knowledge_gaps[0].question == "钛合金紧固件的规格要求是什么"
    assert service.rejected() == ()
    assert len(service.audit_tail(50)) == 2


def test_build_index_report_counts(corpus, tmp_path):
    report = AskService.build_index(corpus, tmp_path / "state")
    assert report.documents == 9
    assert report.internal_docs == 6
    assert report.restricted_docs == 3
    assert report.restricted_by_category == {"(未归品类)": 1, "电解铜": 1, "紧固件": 1}
    assert report.rejected == ()
