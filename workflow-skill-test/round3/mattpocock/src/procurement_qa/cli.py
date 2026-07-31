"""命令行前端 —— 薄壳。

只做三件事:解析参数、调核心、把结果渲染成人话。所有判断都在核心模块里,
这里一行业务逻辑都没有。以后接企业微信时,换的就是这一层。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .answering import answer_question
from .config import DEFAULT_CONFIG, Config, ConfigError, load_config, load_library, save_library
from .ingest import ingest_library
from .llm import AnthropicDriver
from .model import Answer, Library
from .people import RosterError, load_roster
from .records import RecordStore, gaps_by_category
from .rehearsal import RehearsalDriver
from .summarise import make_summariser

DRIVERS = ("anthropic", "rehearsal")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pqa", description="采购品类知识问答机器人"
    )
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="配置文件路径(默认 pqa.toml)")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest_cmd = sub.add_parser("ingest", help="读一遍知识库,建知识目录,打印摄取报告")
    ingest_cmd.add_argument("--driver", choices=DRIVERS, default="anthropic")

    ask_cmd = sub.add_parser("ask", help="提问")
    ask_cmd.add_argument("question", help="要问的问题")
    ask_cmd.add_argument("--as", dest="employee_id", required=True, help="提问人的工号")
    ask_cmd.add_argument("--driver", choices=DRIVERS, default="anthropic")

    who_cmd = sub.add_parser("whoami", help="看看某个工号是谁、能看什么")
    who_cmd.add_argument("--as", dest="employee_id", required=True)

    sub.add_parser("gaps", help="按品类打印知识缺口清单")
    sub.add_parser("audit", help="打印访问记录")
    sub.add_parser("doctor", help="列出没读进知识库的文件")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        config = load_config(args.config)
        return _dispatch(args, config)
    except (ConfigError, RosterError) as exc:
        print(f"错误:{exc}", file=sys.stderr)
        return 2


def _dispatch(args, config: Config) -> int:
    if args.command == "ingest":
        return _cmd_ingest(args, config)
    if args.command == "ask":
        return _cmd_ask(args, config)
    if args.command == "whoami":
        return _cmd_whoami(args, config)
    if args.command == "gaps":
        return _cmd_gaps(config)
    if args.command == "audit":
        return _cmd_audit(config)
    return _cmd_doctor(config)


def _driver(name: str):
    return RehearsalDriver() if name == "rehearsal" else AnthropicDriver()


def _cmd_ingest(args, config: Config) -> int:
    library = ingest_library(
        config.knowledge_root,
        restricted_dir=config.restricted_dir,
        summariser=make_summariser(_driver(args.driver)),
    )
    save_library(library, config.library_path)

    report = library.report
    print(f"知识库:{config.knowledge_root}")
    print(f"读入 {report.ingested_count} 份,未读入 {report.skipped_count} 份。")
    restricted = sum(1 for d in library.documents if d.restricted)
    print(f"其中保密文档 {restricted} 份(位于「{config.restricted_dir}」文件夹下)。")
    if report.skipped:
        print("\n没读进来的文件:")
        _print_skipped(library)
    print(f"\n知识目录已存到 {config.library_path}")
    return 0


def _cmd_doctor(config: Config) -> int:
    library = load_library(config.library_path)
    if not library.report.skipped:
        print("所有文件都读进来了。")
        return 0
    print("没读进知识库的文件:")
    _print_skipped(library)
    return 0


def _print_skipped(library: Library) -> None:
    for skipped in library.report.skipped:
        print(f"  - {skipped.path}\n      原因:{skipped.detail}")


def _cmd_whoami(args, config: Config) -> int:
    roster = load_roster(config.roster, fallback_employee_id=config.fallback_employee_id)
    asker = roster.find(args.employee_id)
    categories = "、".join(asker.categories) if asker.categories else "(无)"
    print(f"工号 {asker.employee_id}:{asker.name}")
    print(f"角色:{asker.role.value}")
    print(f"负责品类:{categories}")
    print(f"联系方式:{asker.contact or '(未填)'}")
    if asker.role.value == "采购员":
        print("可见范围:全部非保密文档。")
    else:
        print("可见范围:全部非保密文档 + 上述品类的保密文档。")
    return 0


def _cmd_ask(args, config: Config) -> int:
    library = load_library(config.library_path)
    roster = load_roster(config.roster, fallback_employee_id=config.fallback_employee_id)
    asker = roster.find(args.employee_id)

    answer = answer_question(
        question=args.question,
        asker=asker,
        library=library,
        driver=_driver(args.driver),
        roster=roster,
    )
    RecordStore(config.runtime).log_ask(
        question=args.question, asker=asker, answer=answer, library=library
    )
    _print_answer(answer, library)
    return 0


def _print_answer(answer: Answer, library: Library) -> None:
    print(answer.text)
    if answer.citations:
        print("\n出处:")
        for citation in answer.citations:
            doc = library.by_id(citation.document_id)
            title = doc.title if doc else citation.document_id
            print(f"  - {title}({citation.document_id})")
            print(f"      原文:{citation.quote.strip()}")
    if answer.restricted_notice:
        print(f"\n[权限] {answer.restricted_notice}")
    if answer.handover:
        target = answer.handover
        suffix = "(该品类暂无人认领,按兜底规则)" if target.is_fallback else ""
        contact = f" {target.to_contact}" if target.to_contact else ""
        print(f"\n[转人工] 已记录,请联系 {target.to_name}{contact}{suffix}")


def _cmd_gaps(config: Config) -> int:
    grouped = gaps_by_category(RecordStore(config.runtime).gaps())
    if not grouped:
        print("暂无知识缺口记录。")
        return 0
    print("知识缺口清单(按品类,次数多的在前):\n")
    for category, questions in grouped.items():
        print(f"【{category}】")
        for question, count in questions:
            print(f"  - {question}  ×{count}")
        print()
    return 0


def _cmd_audit(config: Config) -> int:
    records = RecordStore(config.runtime).audit()
    if not records:
        print("暂无访问记录。")
        return 0
    print("访问记录(只存本地):\n")
    for record in records:
        flags = []
        if record.get("touched_restricted"):
            flags.append("触及保密")
        if record.get("restricted_blocked"):
            flags.append("被权限挡下")
        if record.get("abstained"):
            flags.append("弃答")
        suffix = f"  [{'/'.join(flags)}]" if flags else ""
        print(f"{record['at']}  {record['asked_by']}({record['role']})  {record['question']}{suffix}")
    return 0


def run() -> None:  # pragma: no cover - 打包入口
    raise SystemExit(main())
