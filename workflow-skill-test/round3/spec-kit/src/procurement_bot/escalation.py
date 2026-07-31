"""转人工与知识缺口(FR-013 ~ FR-016)。

这是领导那个"真正目的"的落地闭环:机器人答不上来的地方,正是知识还留在某个
老采购脑子里、尚未落到库里的地方。所以每一条"不知道"都被当成**知识缺口**记下来,
按被问次数排序,告诉部门最该补哪些文档。

权限不足的提问**单独分组**——它不是知识缺口,而是权限咨询。混在一起会让品类经理
误以为要去补文档(contracts/cli.md C-G2)。
"""

from __future__ import annotations

import json
import re
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .models import (
    Escalation,
    EscalationReason,
    GapReport,
    GapRow,
    Requester,
    Role,
    to_jsonable,
)

FILENAME = "escalations.jsonl"
_PUNCT = re.compile(r"[\s,。,.?？!!、;;::""''\"'()()【】\[\]]+")


def normalize_question(question: str) -> str:
    """归一化,用于把"同一个问题"聚到一起计数。"""
    return _PUNCT.sub("", question).lower()


class EscalationStore:
    def __init__(self, state_dir: Path | str) -> None:
        self.path = Path(state_dir) / FILENAME

    def create(
        self,
        *,
        requester: Requester,
        question: str,
        reason: EscalationReason,
        question_category: str | None,
        routed_to: tuple[Requester, ...],
        now: datetime | None = None,
    ) -> Escalation:
        esc = Escalation(
            escalation_id=uuid.uuid4().hex[:12],
            created_at=now or datetime.now(timezone.utc),
            employee_id=requester.employee_id,
            name=requester.name,
            role=requester.role,
            question=question,
            reason=reason,
            question_category=question_category,
            routed_to=tuple(r.employee_id for r in routed_to),
        )
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(to_jsonable(esc), ensure_ascii=False) + "\n")
        return esc

    def all(self) -> tuple[Escalation, ...]:
        if not self.path.is_file():
            return ()
        out: list[Escalation] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            out.append(
                Escalation(
                    escalation_id=d["escalation_id"],
                    created_at=datetime.fromisoformat(d["created_at"]),
                    employee_id=d["employee_id"],
                    name=d["name"],
                    role=Role(d["role"]),
                    question=d["question"],
                    reason=EscalationReason(d["reason"]),
                    question_category=d["question_category"],
                    routed_to=tuple(d["routed_to"]),
                )
            )
        return tuple(out)

    def gap_report(self, limit: int = 50) -> GapReport:
        gaps = self._aggregate(
            [
                e
                for e in self.all()
                if e.reason
                in (EscalationReason.NO_COVERAGE, EscalationReason.FABRICATION_BLOCKED)
            ],
            limit,
        )
        perms = self._aggregate(
            [e for e in self.all() if e.reason is EscalationReason.PERMISSION_DENIED],
            limit,
        )
        return GapReport(knowledge_gaps=gaps, permission_requests=perms)

    @staticmethod
    def _aggregate(items: list[Escalation], limit: int) -> tuple[GapRow, ...]:
        buckets: dict[str, list[Escalation]] = defaultdict(list)
        for e in items:
            buckets[normalize_question(e.question)].append(e)

        rows = [
            GapRow(
                question=group[-1].question,
                count=len(group),
                last_seen=max(e.created_at for e in group),
                routed_to=group[-1].routed_to,
            )
            for group in buckets.values()
        ]
        # 次数降序;同次数时按最近一次时间降序、再按问题文本保证确定性
        rows.sort(key=lambda r: (-r.count, -r.last_seen.timestamp(), r.question))
        return tuple(rows[:limit] if limit > 0 else rows)
