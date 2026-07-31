import json

import pytest

from pkbot.cli import ask, main
from pkbot.drivers import MockDriver
from pkbot.gaps import weekly_report

ROSTER = (
    "工号,姓名,角色,负责品类\n"
    "G0042,李四,采购员,\n"
    "G0007,王五,品类经理,紧固件\n"
    "G0001,赵六,管理员,\n"
)


@pytest.fixture
def workspace(tmp_path):
    lib = tmp_path / "library"
    (lib / "public").mkdir(parents=True)
    (lib / "confidential" / "紧固件").mkdir(parents=True)
    (lib / "public" / "紧固件采购规范.md").write_text(
        "# 规格要求\n螺栓须符合 GB/T 5783。\n", encoding="utf-8"
    )
    (lib / "confidential" / "紧固件" / "2025谈判纪要.md").write_text(
        "# 谈判结果\n供应商甲报价每件 12 元。\n", encoding="utf-8"
    )
    (lib / "public" / "扫描件.wps").write_bytes(b"\x00")
    (lib / "roster.csv").write_text(ROSTER, encoding="utf-8")
    return tmp_path


def _ok(answer, doc_id, locator):
    return json.dumps(
        {
            "status": "answered",
            "answer": answer,
            "citations": [{"doc_id": doc_id, "locator": locator}],
        },
        ensure_ascii=False,
    )


_NO_ANSWER = json.dumps({"status": "no_answer", "answer": "", "citations": []})


def test_buyer_gets_public_answer_with_citation(workspace):
    driver = MockDriver([_ok("须符合 GB/T 5783。", "public/紧固件采购规范.md", "规格要求")])
    ans = ask(
        workspace / "library", workspace / "state", "G0042", "螺栓规格要求是什么", driver
    )
    assert ans.status == "answered"
    assert ans.citations[0].locator == "规格要求"


def test_buyer_asking_confidential_is_denied_and_told_who_to_find(workspace):
    driver = MockDriver([_NO_ANSWER])
    ans = ask(
        workspace / "library", workspace / "state", "G0042", "供应商甲报价多少", driver
    )
    assert ans.status == "denied"
    assert "保密" in ans.text and "王五" in ans.text
    assert "12 元" not in ans.text  # 绝不泄露正文


def test_manager_can_see_own_category_confidential(workspace):
    driver = MockDriver(
        [_ok("每件 12 元。", "confidential/紧固件/2025谈判纪要.md", "谈判结果")]
    )
    ans = ask(
        workspace / "library", workspace / "state", "G0007", "供应商甲报价多少", driver
    )
    assert ans.status == "answered" and "12" in ans.text


def test_denied_and_unanswered_land_in_gap_ledger(workspace):
    driver = MockDriver([_NO_ANSWER])
    ask(workspace / "library", workspace / "state", "G0042", "供应商甲报价多少", driver)
    rep = weekly_report(workspace / "state")
    assert rep.total == 1 and len(rep.unanswered) == 1


def test_unknown_employee_is_refused(workspace):
    with pytest.raises(SystemExit):
        main(
            [
                "ask",
                "问题",
                "--user",
                "G9999",
                "--library",
                str(workspace / "library"),
                "--state",
                str(workspace / "state"),
            ]
        )


def test_library_status_lists_unreadable_files(workspace, capsys):
    code = main(
        [
            "library",
            "status",
            "--user",
            "G0001",
            "--library",
            str(workspace / "library"),
            "--state",
            str(workspace / "state"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0 and "扫描件.wps" in out and "不支持的格式" in out


def test_whoami_reports_role_and_categories(workspace, capsys):
    code = main(
        [
            "whoami",
            "--user",
            "G0007",
            "--library",
            str(workspace / "library"),
            "--state",
            str(workspace / "state"),
        ]
    )
    out = capsys.readouterr().out
    assert code == 0 and "品类经理" in out and "紧固件" in out


def test_gaps_answer_creates_document_that_becomes_answerable(workspace):
    driver = MockDriver([_NO_ANSWER])
    ask(workspace / "library", workspace / "state", "G0042", "紧固件退货怎么走", driver)
    gap_id = weekly_report(workspace / "state").unanswered[0]["id"]

    code = main(
        [
            "gaps",
            "answer",
            gap_id,
            "--text",
            "填退货单后走两级审批。",
            "--user",
            "G0007",
            "--library",
            str(workspace / "library"),
            "--state",
            str(workspace / "state"),
        ]
    )
    assert code == 0
    faq = list((workspace / "library" / "public" / "faq").glob("*.md"))
    assert len(faq) == 1 and "两级审批" in faq[0].read_text(encoding="utf-8")

    driver2 = MockDriver(
        [_ok("填退货单后走两级审批。", f"public/faq/{faq[0].name}", "紧固件退货怎么走")]
    )
    ans = ask(
        workspace / "library", workspace / "state", "G0042", "紧固件退货怎么走", driver2
    )
    assert ans.status == "answered"


def test_gaps_report_prints_pending_questions(workspace, capsys):
    driver = MockDriver([_NO_ANSWER])
    ask(workspace / "library", workspace / "state", "G0042", "紧固件退货怎么走", driver)
    code = main(["gaps", "report", "--state", str(workspace / "state")])
    out = capsys.readouterr().out
    assert code == 0 and "紧固件退货怎么走" in out and "1 个没答上来" in out


def test_denied_response_never_leaks_confidential_paths_or_titles(workspace):
    """采购员越权提问时,只能知道"存在保密资料"和该找谁,别的一律不给。"""
    fabricated = json.dumps(
        {
            "status": "answered",
            "answer": "每件 12 元。",
            "citations": [
                {"doc_id": "confidential/紧固件/2025谈判纪要.md", "locator": "谈判结果"}
            ],
        },
        ensure_ascii=False,
    )
    driver = MockDriver([fabricated])
    ans = ask(
        workspace / "library", workspace / "state", "G0042", "供应商甲报价多少", driver
    )
    assert ans.status == "denied"
    joined = ans.text + " ".join(ans.notes)
    assert "confidential" not in joined
    assert "谈判纪要" not in joined
    assert "12 元" not in joined


def test_denied_response_drops_internal_diagnostics(workspace):
    """越权提示不该再跟一句"疑似编造"——那是内部诊断,对采购员是噪音。

    问题里同时含"螺栓"(命中公开文档,保证驱动被真正调用)与
    "供应商甲报价"(强命中保密文档,触发 denied 分支)。
    """
    fabricated = json.dumps(
        {
            "status": "answered",
            "answer": "每件 12 元。",
            "citations": [{"doc_id": "confidential/紧固件/2025谈判纪要.md", "locator": "x"}],
        },
        ensure_ascii=False,
    )
    driver = MockDriver([fabricated])
    ans = ask(
        workspace / "library",
        workspace / "state",
        "G0042",
        "螺栓的供应商甲报价多少",
        driver,
    )
    assert driver.calls, "这条测试必须真的走到模型调用,否则等于没测"
    assert ans.status == "denied"
    assert not any("编造" in n for n in ans.notes)


def test_weak_lexical_overlap_does_not_falsely_claim_confidential_material(workspace):
    """只因一个通用词沾边就说"涉及保密资料"会误导人、也会弄脏统计。"""
    (workspace / "library" / "confidential" / "紧固件" / "2025谈判纪要.md").write_text(
        "# 谈判结果\n成本构成中原材料约占 62%。\n", encoding="utf-8"
    )
    driver = MockDriver([_NO_ANSWER])
    ans = ask(
        workspace / "library",
        workspace / "state",
        "G0042",
        "包装材料的验收标准是什么",
        driver,
    )
    assert ans.status == "no_answer"
    assert "保密" not in ans.text


def test_strong_overlap_still_claims_confidential_material(workspace):
    driver = MockDriver([_NO_ANSWER])
    ans = ask(
        workspace / "library", workspace / "state", "G0042", "供应商甲报价多少", driver
    )
    assert ans.status == "denied"


def test_cli_reports_backfill_permission_error_cleanly(workspace, capsys):
    """越权补答要给一句人话,而不是抛栈。"""
    driver = MockDriver([_NO_ANSWER])
    ask(workspace / "library", workspace / "state", "G0042", "紧固件退货怎么走", driver)
    gap_id = weekly_report(workspace / "state").unanswered[0]["id"]
    with pytest.raises(SystemExit):
        main(
            [
                "gaps",
                "answer",
                gap_id,
                "--text",
                "随便写点什么",
                "--user",
                "G0042",  # 采购员,无补答权限
                "--library",
                str(workspace / "library"),
                "--state",
                str(workspace / "state"),
            ]
        )
    assert "没有补答入库的权限" in capsys.readouterr().err
