"""命令行入口。

对话入口(本文件)与问答内核(ask 以下的各模块)分层,
以后接企业微信只需要换掉这一层壳,内核不动。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .access import owners_for_category, partition
from .answering import answer_question, disclosures
from .drivers import LLMDriver, ScriptedDriver
from .gaps import record_question, resolve_gap, weekly_report
from .identity import RosterError, UnknownUserError, get_user, load_roster
from .library import ROSTER_FILENAME, scan_library
from .models import Answer, User
from .retrieval import build_context, matched_term_count, rank

# 断言"库里有保密资料与这个问题相关"至少要命中这么多个不同的词。
# 单个词沾边就声称涉密会误导同事、误派给错的品类经理,也会弄脏统计。
MIN_HIDDEN_TERM_HITS = 2

DEFAULT_LIBRARY = Path("demo/library")
DEFAULT_STATE = Path("demo/state")

_NO_ANSWER_JSON = '{"status": "no_answer", "answer": "", "citations": []}'


def _demo_driver() -> ScriptedDriver:
    """离线演示驱动:按关键词回放固定答案,不联网、结果可复现。

    真实使用请加 --driver anthropic。
    """
    return ScriptedDriver(
        rules=[
            (
                "螺栓",
                '{"status": "answered", "answer": "螺栓须符合 GB/T 5783,'
                '材质为 304 不锈钢。", "citations": [{"doc_id": '
                '"public/不锈钢紧固件采购规范.md", "locator": "二、规格要求"}]}',
            ),
            (
                "归谁管",
                '{"status": "answered", "answer": "不锈钢紧固件由王五(工号 G0007)'
                '负责。", "citations": [{"doc_id": "registry/品类负责人对照表.csv", '
                '"locator": "表格 第 1-4 行"}]}',
            ),
            (
                "报价",
                '{"status": "answered", "answer": "2025 年度谈判后,供应商甲的'
                '不锈钢螺栓单价为每件 12 元。", "citations": [{"doc_id": '
                '"confidential/紧固件/2025年度谈判纪要.md", "locator": "三、谈判结果"}]}',
            ),
        ],
        default=_NO_ANSWER_JSON,
        match_after="【问题】",
    )


def _load_user(library_root: Path, employee_id: str) -> tuple[User, dict[str, User]]:
    roster = load_roster(library_root / ROSTER_FILENAME)
    return get_user(roster, employee_id), roster


def ask(
    library_root: Path,
    state_dir: Path,
    employee_id: str,
    question: str,
    driver: LLMDriver,
) -> Answer:
    """一次完整问答:认人 → 权限过滤 → 检索装载 → 模型 → 引用校验 → 记台账。"""
    user, roster = _load_user(library_root, employee_id)
    library = scan_library(library_root)
    visibility = partition(user, library)

    pack = build_context(question, list(visibility.visible))
    answer = answer_question(driver, question, pack)

    category_hint: str | None = None
    if answer.status != "answered":
        # 公开资料答不上来,但保密区里有相关资料 → 明确告知涉密并指出该找谁。
        # 只暴露"存在保密资料"和负责人姓名,绝不暴露标题或正文。
        hidden_hits = rank(question, list(visibility.hidden))
        if hidden_hits and (
            matched_term_count(question, hidden_hits[0][0]) >= MIN_HIDDEN_TERM_HITS
        ):
            category_hint = hidden_hits[0][0].category
            owners = owners_for_category(roster, category_hint)
            who = "、".join(owners) if owners else "对应的品类经理"
            answer = Answer(
                status="denied",
                text=(
                    f"这个问题涉及保密资料,你的权限看不到。"
                    f"已经记录下来,会转给{who}跟进。"
                ),
                citations=(),
                # 只保留"没读全"这类对用户有用的提示;
                # 内部诊断(格式不合法/疑似编造)对采购员是噪音,丢掉。
                notes=tuple(disclosures(pack)),
            )

    record_question(state_dir, user, question, answer.status, category_hint)
    return answer


def _print_answer(answer: Answer) -> None:
    print(answer.text)
    if answer.citations:
        print("\n依据:")
        for c in answer.citations:
            print(f"  - {c.doc_id} · {c.locator}")
    for note in answer.notes:
        print(f"\n{note}")


def _cmd_ask(args: argparse.Namespace) -> int:
    driver: LLMDriver
    if args.driver == "anthropic":
        from .anthropic_driver import AnthropicDriver

        driver = AnthropicDriver()
    else:
        driver = _demo_driver()
    _print_answer(ask(args.library, args.state, args.user, args.question, driver))
    return 0


def _cmd_whoami(args: argparse.Namespace) -> int:
    user, _ = _load_user(args.library, args.user)
    cats = "、".join(user.categories) if user.categories else "(无)"
    print(f"{user.name}({user.employee_id})· 角色:{user.role} · 负责品类:{cats}")
    return 0


def _cmd_library_status(args: argparse.Namespace) -> int:
    user, _ = _load_user(args.library, args.user)
    library = scan_library(args.library)
    visibility = partition(user, library)
    print(
        f"库里共有 {len(library.documents)} 份可读文档,"
        f"你能看到 {len(visibility.visible)} 份。"
    )
    if library.unreadable:
        print(f"\n有 {len(library.unreadable)} 份文件读不了(内容没进库):")
        for item in library.unreadable:
            # reason 已自带文件名,这里不再重复前缀
            print(f"  - {item.reason}")
    else:
        print("\n所有文件都能正常读取。")
    return 0


def _cmd_gaps_report(args: argparse.Namespace) -> int:
    rep = weekly_report(args.state, days=args.days)
    print(
        f"最近 {args.days} 天:共提问 {rep.total} 次,"
        f"其中 {len(rep.unanswered)} 个没答上来,已补答 {rep.resolved} 个。"
    )
    for entry in rep.unanswered:
        print(f"  [{entry['id']}] {entry['name']}:{entry['question']}")
    if not rep.unanswered:
        print("  (没有待处理的问题)")
    return 0


def _cmd_gaps_answer(args: argparse.Namespace) -> int:
    user, _ = _load_user(args.library, args.user)
    path = resolve_gap(
        args.state,
        args.library,
        args.gap_id,
        args.text,
        author=user,
        confidential=args.confidential,
        category=args.category,
    )
    print(f"已补答并入库:{path}")
    return 0


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--user", required=True, help="你的工号")
    parser.add_argument("--library", type=Path, default=DEFAULT_LIBRARY, help="文档库目录")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE, help="台账目录")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pkbot", description="采购品类知识问答机器人")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ask = sub.add_parser("ask", help="提一个问题")
    p_ask.add_argument("question")
    p_ask.add_argument(
        "--driver",
        choices=["demo", "anthropic"],
        default="demo",
        help="demo=离线演示驱动(默认);anthropic=真实模型",
    )
    _add_common(p_ask)
    p_ask.set_defaults(func=_cmd_ask)

    p_who = sub.add_parser("whoami", help="看看机器人认为你是谁")
    _add_common(p_who)
    p_who.set_defaults(func=_cmd_whoami)

    p_lib = sub.add_parser("library", help="文档库相关")
    lib_sub = p_lib.add_subparsers(dest="subcommand", required=True)
    p_status = lib_sub.add_parser("status", help="库里有什么、哪些读不了")
    _add_common(p_status)
    p_status.set_defaults(func=_cmd_library_status)

    p_gaps = sub.add_parser("gaps", help="知识缺口台账")
    gaps_sub = p_gaps.add_subparsers(dest="subcommand", required=True)

    p_rep = gaps_sub.add_parser("report", help="出周报")
    p_rep.add_argument("--days", type=int, default=7)
    p_rep.add_argument("--state", type=Path, default=DEFAULT_STATE)
    p_rep.set_defaults(func=_cmd_gaps_report)

    p_ans = gaps_sub.add_parser("answer", help="人工补答并回填成新文档")
    p_ans.add_argument("gap_id")
    p_ans.add_argument("--text", required=True, help="补充的答案正文")
    p_ans.add_argument("--confidential", action="store_true", help="标记这条按保密算")
    p_ans.add_argument("--category", help="标为保密时必须指明品类")
    _add_common(p_ans)
    p_ans.set_defaults(func=_cmd_gaps_answer)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (
        UnknownUserError,
        RosterError,
        PermissionError,
        ValueError,
        KeyError,
    ) as exc:
        print(f"错误:{exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    raise SystemExit(main())
