"""知识缺口台账:记录每次提问、出周报、把人工补答回填成新文档进库。

这是"知识落在库里、不落在人手里"这句话的技术落点:
光有库不够,还得看得见库缺什么,并且补上去的东西能自动变成库的一部分。
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import ROLE_ADMIN, ROLE_CATEGORY_MANAGER, User

LOG_FILENAME = "questions.jsonl"
UNANSWERED_STATUSES = {"no_answer", "denied"}
BACKFILL_ROLES = {ROLE_CATEGORY_MANAGER, ROLE_ADMIN}


@dataclass(frozen=True)
class Report:
    total: int
    unanswered: list[dict]
    resolved: int


def _log_path(state_dir: Path) -> Path:
    return state_dir / LOG_FILENAME


def record_question(
    state_dir: Path,
    user: User,
    question: str,
    status: str,
    category_hint: str | None = None,
    now: datetime | None = None,
) -> str:
    """记录每一次提问(不只是失败的),这样周报才能说出"问了多少"。"""
    state_dir.mkdir(parents=True, exist_ok=True)
    gap_id = uuid.uuid4().hex[:8]
    entry = {
        "id": gap_id,
        "ts": (now or datetime.now(timezone.utc)).isoformat(),
        "employee_id": user.employee_id,
        "name": user.name,
        "question": question,
        "status": status,
        "category_hint": category_hint,
        "resolved": False,
    }
    with _log_path(state_dir).open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return gap_id


def load_entries(state_dir: Path) -> list[dict]:
    path = _log_path(state_dir)
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _rewrite(state_dir: Path, entries: list[dict]) -> None:
    with _log_path(state_dir).open("w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def weekly_report(state_dir: Path, days: int = 7, now: datetime | None = None) -> Report:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    entries = [
        e for e in load_entries(state_dir) if datetime.fromisoformat(e["ts"]) >= cutoff
    ]
    unanswered = [
        e for e in entries if e["status"] in UNANSWERED_STATUSES and not e["resolved"]
    ]
    resolved = sum(1 for e in entries if e["resolved"])
    return Report(len(entries), unanswered, resolved)


def _slug(text: str) -> str:
    cleaned = re.sub(r'[\\/:*?"<>|\s]+', "-", text).strip("-")
    return cleaned[:30] or "问题"


def _validate_category(category: str) -> str:
    """品类名会被拼进路径,必须挡住目录穿越。

    代码审查 C1:`--category "../../.."` 曾能把文件写到文档库之外。
    """
    name = category.strip()
    if not name or name in {".", ".."} or any(sep in name for sep in ("/", "\\")):
        raise ValueError(f"品类名 '{category}' 不合法:不能为空,也不能包含路径分隔符。")
    return name


def _check_backfill_permission(
    author: User, confidential: bool, category: str | None
) -> None:
    """写权限必须与读权限对称。

    代码审查 C2:此前任何人(包括采购员)都能往任意保密品类目录里写文档,
    等于绕过整套权限模型向知识库注入内容。
    """
    if author.role not in BACKFILL_ROLES:
        raise PermissionError(
            f"{author.name} 的角色是{author.role},没有补答入库的权限。"
            f"请转给品类经理或管理员。"
        )
    if author.role == ROLE_ADMIN:
        return
    if confidential and category not in author.categories:
        raise PermissionError(
            f"{author.name} 只负责 {'、'.join(author.categories) or '(无)'},"
            f"不能往「{category}」的保密资料里补答。"
        )


def resolve_gap(
    state_dir: Path,
    library_root: Path,
    gap_id: str,
    answer_text: str,
    author: User,
    confidential: bool = False,
    category: str | None = None,
    now: datetime | None = None,
) -> Path:
    """人工补答 → 生成新文档进库,并把台账条目标记为已解决。

    默认写进公开 faq;补答人认为敏感时可标为保密,但必须指明品类,
    否则会变成"未分类保密文档",除管理员外谁都看不到——等于白补。
    """
    if confidential and not category:
        raise ValueError("标记为保密的补答必须指定品类,否则除管理员外没人能看到它。")
    if confidential:
        category = _validate_category(category or "")
    _check_backfill_permission(author, confidential, category)

    entries = load_entries(state_dir)
    target = next((e for e in entries if e["id"] == gap_id), None)
    if target is None:
        raise KeyError(f"待人工清单里没有编号 {gap_id} 的问题。")

    if confidential:
        folder = library_root / "confidential" / category / "faq"
    else:
        folder = library_root / "public" / "faq"
    folder.mkdir(parents=True, exist_ok=True)

    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%d")
    path = folder / f"{gap_id}-{_slug(target['question'])}.md"
    path.write_text(
        f"# {target['question']}\n\n"
        f"{answer_text.strip()}\n\n"
        f"---\n\n"
        f"本条由 {author.name}({author.employee_id})于 {stamp} 补充,"
        f"来源:{target['name']} 的提问(编号 {gap_id})。\n",
        encoding="utf-8",
    )

    target["resolved"] = True
    target["resolved_by"] = author.employee_id
    target["resolved_doc"] = str(path)
    _rewrite(state_dir, entries)
    return path
