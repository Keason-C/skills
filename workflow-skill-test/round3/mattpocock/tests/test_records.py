"""知识缺口清单与访问记录 —— 交给领导的第二产物,以及出事能查的那本账。"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from procurement_qa.ingest import ingest_library
from procurement_qa.model import Answer, Asker, Citation, Handover, Role
from procurement_qa.records import RecordStore, gaps_by_category

BUYER = Asker("1001", "李强", Role.BUYER)
MANAGER = Asker("2001", "王敏", Role.CATEGORY_MANAGER, ("金属",))
AT = dt.datetime(2026, 7, 31, 9, 0, 0)

ABSTAINED = Answer(
    text="我不知道",
    abstained=True,
    abstain_reason="no_documents_selected",
    handover=Handover("王敏", "wm@example.com", "金属"),
)
ANSWERED = Answer(
    text="双供应商策略。",
    citations=(Citation("金属/金属品类策略.docx", "本品类采用双供应商策略"),),
)


def test_弃答记一条知识缺口成功作答不记(tmp_path: Path, knowledge_root: Path) -> None:
    library = ingest_library(knowledge_root)
    store = RecordStore(tmp_path / "runtime")

    store.log_ask(question="金属的账期?", asker=BUYER, answer=ABSTAINED, library=library, at=AT)
    store.log_ask(question="金属策略?", asker=BUYER, answer=ANSWERED, library=library, at=AT)

    gaps = store.gaps()
    assert len(gaps) == 1
    assert gaps[0]["question"] == "金属的账期?"
    assert gaps[0]["category"] == "金属"
    assert gaps[0]["handed_to"] == "王敏"
    assert gaps[0]["asked_by"] == "李强"


def test_缺口按品类分组并能看出重复次数(tmp_path: Path, knowledge_root: Path) -> None:
    library = ingest_library(knowledge_root)
    store = RecordStore(tmp_path / "runtime")

    for _ in range(3):
        store.log_ask(question="金属的账期?", asker=BUYER, answer=ABSTAINED, library=library, at=AT)
    store.log_ask(
        question="包材怎么验收?",
        asker=BUYER,
        answer=Answer(text="", abstained=True, handover=Handover("赵磊", "", "包材")),
        library=library,
        at=AT,
    )

    grouped = gaps_by_category(store.gaps())

    assert set(grouped) == {"金属", "包材"}
    assert grouped["金属"][0] == ("金属的账期?", 3)
    assert grouped["包材"][0] == ("包材怎么验收?", 1)


def test_每次提问都记一条访问记录并标出是否触及保密(tmp_path: Path, knowledge_root: Path) -> None:
    library = ingest_library(knowledge_root)
    store = RecordStore(tmp_path / "runtime")
    restricted_answer = Answer(
        text="报价 4820。",
        citations=(Citation("保密/金属/2024金属供应商报价单.xlsx", "4820"),),
    )

    store.log_ask(question="策略?", asker=BUYER, answer=ANSWERED, library=library, at=AT)
    store.log_ask(question="报价?", asker=MANAGER, answer=restricted_answer, library=library, at=AT)

    audit = store.audit()
    assert len(audit) == 2
    assert audit[0]["asked_by"] == "李强"
    assert audit[0]["touched_restricted"] is False
    assert audit[1]["asked_by"] == "王敏"
    assert audit[1]["touched_restricted"] is True
    assert audit[1]["at"] == "2026-07-31T09:00:00"


def test_记录是追加写目录不存在时自动创建(tmp_path: Path, knowledge_root: Path) -> None:
    library = ingest_library(knowledge_root)
    runtime = tmp_path / "深" / "一点" / "runtime"

    store = RecordStore(runtime)
    store.log_ask(question="一", asker=BUYER, answer=ABSTAINED, library=library, at=AT)
    RecordStore(runtime).log_ask(question="二", asker=BUYER, answer=ABSTAINED, library=library, at=AT)

    assert [g["question"] for g in RecordStore(runtime).gaps()] == ["一", "二"]
    assert (runtime / "gaps.jsonl").exists()
    assert (runtime / "audit.jsonl").exists()


def test_没有记录时读出来是空列表而不是报错(tmp_path: Path) -> None:
    store = RecordStore(tmp_path / "空的")

    assert store.gaps() == []
    assert store.audit() == []
