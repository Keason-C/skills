"""命令行 —— 内核之上的一层**薄**适配器(宪法原则 VI / contracts/cli.md)。

这里只做三件事:解析参数、调内核、把 Answer 渲染成人话。
任何业务判断都不应该出现在这个文件里。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .errors import (
    CorpusNotFoundError,
    IndexMissingError,
    ProcurementBotError,
    RosterFormatError,
    UnknownRequesterError,
)
from .core import AskService
from .ingest.loader import DEFAULT_SECRET_DIR
from .models import Answer, AnswerStatus, GapReport, to_jsonable
from .roster import TEMPLATE as ROSTER_TEMPLATE

EXIT_OK = 0
EXIT_USAGE = 2
EXIT_ENV = 3
EXIT_NO_INDEX = 4


def _driver(name: str):
    if name == "mock":
        from .llm.mock import KeywordMockDriver

        return KeywordMockDriver()
    if name == "anthropic":
        # 真实驱动:延迟导入,核心与测试都不碰它(宪法原则 IV)
        from .llm.anthropic_driver import AnthropicDriver

        return AnthropicDriver()
    raise ProcurementBotError(f"未知的驱动:{name}")


def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--corpus", default="./corpus", help="语料根目录(共享盘上的固定文件夹)")
    p.add_argument("--roster", default=None, help="人员名单 CSV,默认 <corpus>/../roster.csv")
    p.add_argument("--state", default="./.pbot", help="索引与日志存放目录")
    p.add_argument("--secret-dir", default=DEFAULT_SECRET_DIR, help="保密文件夹的目录名")


def _roster_path(args) -> Path:
    if args.roster:
        return Path(args.roster)
    return Path(args.corpus).parent / "roster.csv"


def _service(args) -> AskService:
    return AskService.load(
        corpus_root=Path(args.corpus),
        roster_path=_roster_path(args),
        state_dir=Path(args.state),
        driver=_driver(getattr(args, "driver", "mock")),
        secret_dir_name=args.secret_dir,
        top_k=getattr(args, "top_k", 12),
    )


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------


def render_answer(answer: Answer) -> str:
    lines = ["【答案】", answer.text, ""]

    if answer.citations:
        lines.append("【出处】")
        for i, c in enumerate(answer.citations, start=1):
            lines.append(f"  [{i}] {c.doc_name} — {c.locator}")
            excerpt = c.excerpt.replace("\n", " ").strip()
            lines.append(f'      "{excerpt}"')
        lines.append("")

    for notice in answer.notices:
        mark = "⚠" if notice.startswith("资料不一致") else "ℹ"
        lines.append(f"{mark} {notice}")
    if answer.notices:
        lines.append("")

    if answer.status is not AnswerStatus.ANSWERED and answer.contacts:
        who = "、".join(f"{c.name}(工号 {c.employee_id})" for c in answer.contacts)
        arrow = "→ 已转人工:请联系" if answer.status is AnswerStatus.UNKNOWN else "→ 请联系"
        lines.append(f"{arrow} {who}")
        if answer.escalation_id:
            lines.append(f"   本次提问已记入清单(编号 {answer.escalation_id})。")

    return "\n".join(lines).rstrip() + "\n"


def render_gaps(report: GapReport) -> str:
    out: list[str] = ["知识缺口清单(按被提问次数降序)"]
    if not report.knowledge_gaps:
        out.append("  (暂无)")
    for row in report.knowledge_gaps:
        out.append(
            f"  {row.count:>3} 次  {row.last_seen.date()}  {row.question}"
            f"   → {'、'.join(row.routed_to)}"
        )
    out.append("")
    out.append("权限咨询(不是知识缺口,不需要补文档)")
    if not report.permission_requests:
        out.append("  (暂无)")
    for row in report.permission_requests:
        out.append(
            f"  {row.count:>3} 次  {row.last_seen.date()}  {row.question}"
            f"   → {'、'.join(row.routed_to)}"
        )
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# 子命令
# ---------------------------------------------------------------------------


def cmd_ingest(args) -> int:
    report = AskService.build_index(
        Path(args.corpus), Path(args.state), secret_dir_name=args.secret_dir
    )
    if args.json:
        print(json.dumps(to_jsonable(report), ensure_ascii=False, indent=2))
        return EXIT_OK

    print(f"已导入 {report.documents} 份文档,共 {report.passages} 个片段。")
    cats = "、".join(f"{k} {v}" for k, v in report.restricted_by_category.items())
    print(
        f"  普通:{report.internal_docs} 份    "
        f"受限:{report.restricted_docs} 份" + (f"(品类:{cats})" if cats else "")
    )
    if report.rejected:
        print(f"未纳入知识库 {len(report.rejected)} 个文件:")
        width = max(len(r.path) for r in report.rejected)
        for r in report.rejected:
            print(f"  - {r.path.ljust(width)}   {r.reason}")
    else:
        print("所有文件都已纳入知识库。")
    print(f"索引已写入 {report.index_path}")
    return EXIT_OK


def cmd_ask(args) -> int:
    svc = _service(args)
    answer = svc.ask(args.question, args.user)
    if args.json:
        print(json.dumps(to_jsonable(answer), ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(render_answer(answer))
    return EXIT_OK  # "不知道"和"权限不足"都是正常业务结果(C-A3)


def cmd_gaps(args) -> int:
    svc = _service(args)
    report = svc.gaps(args.limit)
    if args.json:
        print(json.dumps(to_jsonable(report), ensure_ascii=False, indent=2))
    else:
        sys.stdout.write(render_gaps(report))
    return EXIT_OK


def cmd_rejected(args) -> int:
    svc = _service(args)
    items = svc.rejected()
    if args.json:
        print(json.dumps(to_jsonable(items), ensure_ascii=False, indent=2))
        return EXIT_OK
    if not items:
        print("没有未纳入知识库的文件。")
        return EXIT_OK
    print(f"未纳入知识库的文件({len(items)} 个):")
    for r in items:
        print(f"  - {r.path}\n      原因:{r.reason}\n      细节:{r.detail}")
    return EXIT_OK


def cmd_audit(args) -> int:
    svc = _service(args)
    records = svc.audit_tail(args.limit)
    if args.json:
        print(json.dumps(to_jsonable(records), ensure_ascii=False, indent=2))
        return EXIT_OK
    if not records:
        print("暂无审计记录。")
        return EXIT_OK
    for r in records:
        flag = "命中受限" if r.restricted_hit else "-"
        print(
            f"{r.at.isoformat(timespec='seconds')}  {r.employee_id}({r.role.value})  "
            f"[{r.status.value}] {r.question}  命中:{','.join(r.visible_hit_doc_ids) or '-'}"
            f"  {flag}"
        )
    return EXIT_OK


def cmd_roster_template(args) -> int:  # noqa: ARG001
    # UTF-8 with BOM:让 Excel 双击打开中文不乱码(C-R1)
    sys.stdout.buffer.write(b"\xef\xbb\xbf" + ROSTER_TEMPLATE.encode("utf-8"))
    return EXIT_OK


# ---------------------------------------------------------------------------
# 入口
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pbot", description="采购 Commodity Know-How 问答机器人"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("ingest", help="扫描语料目录,建立索引")
    _add_common(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ingest)

    p = sub.add_parser("ask", help="提问")
    p.add_argument("question")
    p.add_argument("--user", required=True, help="工号")
    p.add_argument("--driver", default="mock", choices=["mock", "anthropic"])
    p.add_argument("--top-k", type=int, default=12, dest="top_k")
    _add_common(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_ask)

    p = sub.add_parser("gaps", help="知识缺口清单")
    p.add_argument("--limit", type=int, default=50)
    _add_common(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_gaps)

    p = sub.add_parser("rejected", help="未纳入知识库的文件")
    _add_common(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_rejected)

    p = sub.add_parser("audit", help="审计日志")
    p.add_argument("--limit", type=int, default=50)
    _add_common(p)
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("roster-template", help="打印人员名单模板(Excel 可直接打开)")
    p.set_defaults(func=cmd_roster_template)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except UnknownRequesterError as exc:
        print(f"错误:{exc}", file=sys.stderr)
        return EXIT_USAGE
    except IndexMissingError as exc:
        print(f"错误:{exc}", file=sys.stderr)
        return EXIT_NO_INDEX
    except (CorpusNotFoundError, RosterFormatError) as exc:
        print(f"错误:{exc}", file=sys.stderr)
        return EXIT_ENV
    except ProcurementBotError as exc:
        print(f"错误:{exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
