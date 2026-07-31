"""知识缺口清单与访问记录。

**知识缺口**是这个项目交给领导的第二产物:每一次弃答都在说"库里缺这块知识",
按品类攒起来就是一张"该催谁补什么"的清单 —— 老采购走之前照着它交接。

访问记录只落本地,不发往任何外部。出事能查,平时没人看。
"""

from __future__ import annotations

import datetime as dt
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .model import Answer, Asker, Library

GAPS_FILE = "gaps.jsonl"
AUDIT_FILE = "audit.jsonl"


@dataclass(frozen=True)
class RecordStore:
    """追加写的本地记录本。两个文件,一行一条 JSON。"""

    root: Path

    def log_ask(
        self,
        *,
        question: str,
        asker: Asker,
        answer: Answer,
        library: Library,
        at: dt.datetime | None = None,
    ) -> None:
        moment = (at or dt.datetime.now()).isoformat(timespec="seconds")
        touched = _touched_restricted(answer, library)

        self._append(
            AUDIT_FILE,
            {
                "at": moment,
                "asked_by": asker.name,
                "employee_id": asker.employee_id,
                "role": asker.role.value,
                "question": question,
                "abstained": answer.abstained,
                "touched_restricted": touched,
                "restricted_blocked": bool(answer.restricted_notice),
            },
        )

        if answer.abstained:
            handover = answer.handover
            self._append(
                GAPS_FILE,
                {
                    "at": moment,
                    "question": question,
                    "category": (handover.category if handover else "") or "未分类",
                    "asked_by": asker.name,
                    "employee_id": asker.employee_id,
                    "handed_to": handover.to_name if handover else "",
                    "reason": answer.abstain_reason,
                },
            )

    def gaps(self) -> list[dict]:
        return self._read(GAPS_FILE)

    def audit(self) -> list[dict]:
        return self._read(AUDIT_FILE)

    def _append(self, filename: str, payload: dict) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        with (self.root / filename).open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(payload, ensure_ascii=False) + "\n")

    def _read(self, filename: str) -> list[dict]:
        path = self.root / filename
        if not path.exists():
            return []
        records = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                records.append(json.loads(line))
        return records


def gaps_by_category(gaps: list[dict]) -> dict[str, list[tuple[str, int]]]:
    """按品类分组,同一个问题问了几次一目了然 —— 问得越多的缺口越该先补。"""
    buckets: dict[str, Counter] = {}
    for gap in gaps:
        buckets.setdefault(gap.get("category") or "未分类", Counter())[gap["question"]] += 1
    return {
        category: counter.most_common() for category, counter in sorted(buckets.items())
    }


def _touched_restricted(answer: Answer, library: Library) -> bool:
    for citation in answer.citations:
        doc = library.by_id(citation.document_id)
        if doc is not None and doc.restricted:
            return True
    return False
