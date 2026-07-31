"""seam 3:`cli.main(argv)` —— 少量端到端冒烟测试,证明"命令行里真的能用"。

全程离线:用排练驱动,不碰网络。
"""

from __future__ import annotations

import csv
from pathlib import Path

import pytest

from procurement_qa.cli import main


@pytest.fixture
def workspace(tmp_path: Path, knowledge_root: Path) -> Path:
    roster = tmp_path / "roster.csv"
    with roster.open("w", encoding="utf-8", newline="") as fh:
        csv.writer(fh).writerows(
            [
                ["工号", "姓名", "角色", "负责品类", "联系方式"],
                ["1001", "李强", "采购员", "", "lq@example.com"],
                ["2001", "王敏", "品类经理", "金属", "wm@example.com"],
                ["9001", "陈总", "品类经理", "", "cz@example.com"],
            ]
        )
    (tmp_path / "pqa.toml").write_text(
        f'knowledge_root = "{knowledge_root.as_posix()}"\n'
        f'roster = "{roster.as_posix()}"\n'
        f'runtime = "{(tmp_path / ".runtime").as_posix()}"\n'
        'fallback_employee_id = "9001"\n',
        encoding="utf-8",
    )
    return tmp_path


def _run(workspace: Path, *args: str) -> int:
    return main(["--config", str(workspace / "pqa.toml"), *args])


def test_ingest_打印摄取报告并退出码为零(workspace: Path, capsys) -> None:
    code = _run(workspace, "ingest", "--driver", "rehearsal")

    out = capsys.readouterr().out
    assert code == 0
    assert "读入 7 份" in out
    assert "未读入 2 份" in out
    assert "扫描合同.pdf" in out  # 没读进去的必须逐个列名


def test_whoami_打印角色与负责品类(workspace: Path, capsys) -> None:
    code = _run(workspace, "whoami", "--as", "2001")

    out = capsys.readouterr().out
    assert code == 0
    assert "王敏" in out and "品类经理" in out and "金属" in out


def test_采购员问公开问题能拿到带出处的回答(workspace: Path, capsys) -> None:
    _run(workspace, "ingest", "--driver", "rehearsal")
    capsys.readouterr()

    code = _run(workspace, "ask", "--as", "1001", "--driver", "rehearsal", "金属品类采用什么策略?")

    out = capsys.readouterr().out
    assert code == 0
    assert "双供应商" in out
    assert "出处" in out
    assert "金属/金属品类策略.docx" in out


def test_采购员问报价被明确挡下并告知找谁(workspace: Path, capsys) -> None:
    _run(workspace, "ingest", "--driver", "rehearsal")
    capsys.readouterr()

    code = _run(workspace, "ask", "--as", "1001", "--driver", "rehearsal", "金属供应商的报价是多少?")

    out = capsys.readouterr().out
    assert code == 0
    assert "保密" in out
    assert "王敏" in out
    assert "4820" not in out  # 报价数字一个字都不能露


def test_品类经理问同一个问题拿得到答案(workspace: Path, capsys) -> None:
    _run(workspace, "ingest", "--driver", "rehearsal")
    capsys.readouterr()

    code = _run(workspace, "ask", "--as", "2001", "--driver", "rehearsal", "金属供应商的报价单价是多少?")

    out = capsys.readouterr().out
    assert code == 0
    assert "4820" in out


def test_答不上来的问题进知识缺口清单(workspace: Path, capsys) -> None:
    _run(workspace, "ingest", "--driver", "rehearsal")
    _run(workspace, "ask", "--as", "1001", "--driver", "rehearsal", "钛合金的付款账期是多久?")
    capsys.readouterr()

    code = _run(workspace, "gaps")

    out = capsys.readouterr().out
    assert code == 0
    assert "钛合金的付款账期是多久?" in out


def test_audit_记下谁问了什么(workspace: Path, capsys) -> None:
    _run(workspace, "ingest", "--driver", "rehearsal")
    _run(workspace, "ask", "--as", "1001", "--driver", "rehearsal", "请购流程第一步?")
    capsys.readouterr()

    code = _run(workspace, "audit")

    out = capsys.readouterr().out
    assert code == 0
    assert "李强" in out and "请购流程第一步?" in out


def test_doctor_列出没读进来的文件(workspace: Path, capsys) -> None:
    _run(workspace, "ingest", "--driver", "rehearsal")
    capsys.readouterr()

    code = _run(workspace, "doctor")

    out = capsys.readouterr().out
    assert code == 0
    assert "扫描合同.pdf" in out
    assert "旧系统导出.dat" in out


def test_没先ingest就提问会被明确提示而不是崩溃(workspace: Path, capsys) -> None:
    code = _run(workspace, "ask", "--as", "1001", "--driver", "rehearsal", "随便问问")

    err = capsys.readouterr().err
    assert code == 2
    assert "ingest" in err


def test_工号不在名单里给出明确错误(workspace: Path, capsys) -> None:
    _run(workspace, "ingest", "--driver", "rehearsal")
    capsys.readouterr()

    code = _run(workspace, "ask", "--as", "7777", "--driver", "rehearsal", "随便问问")

    err = capsys.readouterr().err
    assert code == 2
    assert "7777" in err
