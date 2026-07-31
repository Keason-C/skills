"""命令行端到端(contracts/cli.md)。"""

from __future__ import annotations

import json
import time

from procurement_bot.cli import EXIT_ENV, EXIT_NO_INDEX, EXIT_OK, EXIT_USAGE, main

from conftest import SECRET_PRICE


def _args(corpus, roster, state, *rest):
    return [
        *rest,
        "--corpus", str(corpus),
        "--roster", str(roster),
        "--state", str(state),
    ]


def test_ingest_reports_documents_and_rejects(corpus, roster_path, tmp_path, capsys):
    (corpus / "坏的.pdf").write_bytes(b"%PDF-1.4 broken")
    state = tmp_path / "state"
    code = main(_args(corpus, roster_path, state, "ingest"))
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "已导入" in out
    assert "未纳入知识库 1 个文件" in out
    assert "坏的.pdf" in out


def test_ingest_summary_does_not_name_restricted_files(
    corpus, roster_path, tmp_path, capsys
):
    """C-I4:摘要里只出现受限文档的计数与品类,不出现文件名。"""
    main(_args(corpus, roster_path, tmp_path / "state", "ingest"))
    out = capsys.readouterr().out
    assert "成本构成说明" not in out
    assert "受限:3 份" in out


def test_ask_prints_answer_and_sources(corpus, roster_path, tmp_path, capsys):
    state = tmp_path / "state"
    main(_args(corpus, roster_path, state, "ingest"))
    capsys.readouterr()
    code = main(_args(corpus, roster_path, state, "ask", "电解铜这个品类归谁管",
                      "--user", "P1001"))
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "【答案】" in out and "【出处】" in out
    assert "张伟" in out


def test_ask_without_coverage_says_so_and_exits_zero(
    corpus, roster_path, tmp_path, capsys
):
    """C-A3:"不知道"是正常业务结果,退出码 0。"""
    state = tmp_path / "state"
    main(_args(corpus, roster_path, state, "ingest"))
    capsys.readouterr()
    code = main(_args(corpus, roster_path, state, "ask", "钛合金紧固件的规格要求",
                      "--user", "P1001"))
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "资料里没有查到相关内容" in out
    assert "已转人工:请联系 王芳" in out


def test_ask_denied_output_has_no_restricted_content(
    corpus, roster_path, tmp_path, capsys
):
    state = tmp_path / "state"
    main(_args(corpus, roster_path, state, "ingest"))
    capsys.readouterr()
    code = main(_args(corpus, roster_path, state, "ask", "电解铜的采购单价是多少",
                      "--user", "P1001"))
    out = capsys.readouterr().out
    assert code == EXIT_OK
    assert "权限无法查看" in out
    assert SECRET_PRICE not in out
    assert "成本构成说明" not in out
    assert "请联系 张伟" in out


def test_ask_json_output(corpus, roster_path, tmp_path, capsys):
    state = tmp_path / "state"
    main(_args(corpus, roster_path, state, "ingest"))
    capsys.readouterr()
    main(_args(corpus, roster_path, state, "ask", "电解铜这个品类归谁管",
               "--user", "P1001", "--json"))
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "answered"
    assert payload["citations"][0]["doc_name"] == "品类管理手册-电解铜.md"


def test_gaps_and_rejected_and_audit(corpus, roster_path, tmp_path, capsys):
    state = tmp_path / "state"
    (corpus / "未知.bin").write_bytes(b"\x00")
    main(_args(corpus, roster_path, state, "ingest"))
    main(_args(corpus, roster_path, state, "ask", "钛合金紧固件的规格要求",
               "--user", "P1001"))
    capsys.readouterr()

    assert main(_args(corpus, roster_path, state, "gaps")) == EXIT_OK
    gaps_out = capsys.readouterr().out
    assert "知识缺口清单" in gaps_out and "钛合金" in gaps_out

    assert main(_args(corpus, roster_path, state, "rejected")) == EXIT_OK
    assert "未知.bin" in capsys.readouterr().out

    assert main(_args(corpus, roster_path, state, "audit")) == EXIT_OK
    audit_out = capsys.readouterr().out
    assert "P1001" in audit_out
    assert "成本构成说明" not in audit_out


def test_unknown_user_exits_with_usage_error(corpus, roster_path, tmp_path, capsys):
    state = tmp_path / "state"
    main(_args(corpus, roster_path, state, "ingest"))
    capsys.readouterr()
    code = main(_args(corpus, roster_path, state, "ask", "任何问题", "--user", "P0000"))
    assert code == EXIT_USAGE
    assert "不在人员名单" in capsys.readouterr().err


def test_missing_index_exit_code(corpus, roster_path, tmp_path, capsys):
    code = main(_args(corpus, roster_path, tmp_path / "nope", "ask", "问题",
                      "--user", "P1001"))
    assert code == EXIT_NO_INDEX
    assert "pbot ingest" in capsys.readouterr().err


def test_missing_corpus_exit_code(tmp_path, roster_path, capsys):
    code = main(_args(tmp_path / "nope", roster_path, tmp_path / "s", "ingest"))
    assert code == EXIT_ENV
    assert "语料目录不存在" in capsys.readouterr().err


def test_roster_template_is_utf8_with_bom(capsysbinary):
    assert main(["roster-template"]) == EXIT_OK
    raw = capsysbinary.readouterr().out
    assert raw.startswith(b"\xef\xbb\xbf"), "Excel 双击打开需要 BOM(C-R1)"
    assert "负责品类" in raw.decode("utf-8-sig")


def test_mock_path_is_fast(corpus, roster_path, tmp_path, capsys):
    """SC-005 的离线可测代理(analyze 发现 E1 补的用例)。

    真实驱动的延迟取决于模型服务,不在离线验收范围内 —— README 里已声明。
    """
    state = tmp_path / "state"
    main(_args(corpus, roster_path, state, "ingest"))
    start = time.perf_counter()
    main(_args(corpus, roster_path, state, "ask", "电解铜这个品类归谁管",
               "--user", "P1001"))
    elapsed = time.perf_counter() - start
    capsys.readouterr()
    assert elapsed < 2.0, f"mock 路径不该慢:{elapsed:.2f}s"
