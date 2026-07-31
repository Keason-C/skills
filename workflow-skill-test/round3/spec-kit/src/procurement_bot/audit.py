"""审计日志(FR-021)。JSONL 追加写,人可以直接用文本编辑器看。

**硬约束(INV-U1)**:审计记录只记 ``restricted_hit: bool``,绝不记受限文档的
名称或正文。有测试断言这一点。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .models import AnswerStatus, AuditRecord, Role, to_jsonable

FILENAME = "audit.jsonl"


class AuditLog:
    def __init__(self, state_dir: Path | str) -> None:
        self.path = Path(state_dir) / FILENAME

    def append(self, record: AuditRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(to_jsonable(record), ensure_ascii=False) + "\n")

    def all(self) -> tuple[AuditRecord, ...]:
        if not self.path.is_file():
            return ()
        out: list[AuditRecord] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            out.append(
                AuditRecord(
                    at=datetime.fromisoformat(d["at"]),
                    employee_id=d["employee_id"],
                    role=Role(d["role"]),
                    question=d["question"],
                    status=AnswerStatus(d["status"]),
                    visible_hit_doc_ids=tuple(d["visible_hit_doc_ids"]),
                    restricted_hit=bool(d["restricted_hit"]),
                    fabrication_blocked=bool(d["fabrication_blocked"]),
                    partial_context=bool(d["partial_context"]),
                    escalation_id=d["escalation_id"],
                )
            )
        return tuple(out)

    def tail(self, limit: int = 50) -> tuple[AuditRecord, ...]:
        records = self.all()
        return records[-limit:] if limit > 0 else records
