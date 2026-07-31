"""语料导入:遍历目录 → 判密级 → 判品类 → 解析 → 切片 → 算 IDF。

两条不可动摇的规则:

1. **密级由路径判定**(FR-008)。位于保密目录下的整份文件都是 restricted。
   绝不按内容关键词猜——需求方原话:"猜错一次就是事故"。
2. **任何单个文件的失败都不能中断整批导入**(FR-018),失败文件进
   ``RejectedFile`` 清单,让人看得见。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from ..errors import CorpusNotFoundError, ProcurementBotError
from ..models import (
    DateConfidence,
    Document,
    Passage,
    RejectedFile,
    Sensitivity,
    to_jsonable,
)
from ..retrieval import build_idf, tokenize
from .parsers import RawSection, parse
from .versioning import extract_version_info

DEFAULT_SECRET_DIR = "保密"
MAX_PASSAGE_CHARS = 1500
INDEX_FILENAME = "index.json"

# 标题里的"版本噪声"词:比较两份文档是否同一主题时要先剥掉这些
_NOISE = re.compile(
    r"(旧版|新版|最终版?|终版|修订版?|定稿|old|new|final|draft|v\d+(\.\d+)*|rev\d*|"
    r"(19|20)\d{2}(年)?(\d{1,2}月?)?)",
    re.I,
)


@dataclass(frozen=True)
class IndexData:
    built_at: datetime
    corpus_root: str
    documents: tuple[Document, ...]
    passages: tuple[Passage, ...]
    rejected: tuple[RejectedFile, ...]
    idf: dict[str, float]

    @property
    def docs_by_id(self) -> dict[str, Document]:
        return {d.doc_id: d for d in self.documents}


def _title_tokens(filename: str) -> tuple[str, ...]:
    stem = Path(filename).stem
    stem = _NOISE.sub(" ", stem)
    stem = re.sub(r"[-_—–()()【】\[\]]+", " ", stem)
    return tuple(sorted(set(tokenize(stem))))


def _classify(rel_parts: tuple[str, ...], secret_dir: str) -> tuple[Sensitivity, str | None]:
    """按相对路径判定密级与品类(FR-008 / FR-008a)。"""
    if rel_parts and rel_parts[0] == secret_dir:
        # 保密/<品类>/文件  → 有品类;保密/文件 → 无品类(仅采购负责人可见)
        category = rel_parts[1] if len(rel_parts) >= 3 else None
        return Sensitivity.RESTRICTED, category
    return Sensitivity.INTERNAL, None


def _chunk(sections: list[RawSection], doc_id: str) -> list[Passage]:
    passages: list[Passage] = []
    n = 0
    for sec in sections:
        text = sec.text.strip()
        if not text:
            continue
        pieces: list[str] = []
        if len(text) <= MAX_PASSAGE_CHARS:
            pieces = [text]
        else:
            buf = ""
            for para in text.split("\n"):
                if len(buf) + len(para) + 1 > MAX_PASSAGE_CHARS and buf:
                    pieces.append(buf)
                    buf = para
                else:
                    buf = f"{buf}\n{para}" if buf else para
            if buf:
                pieces.append(buf)
        for piece in pieces:
            if not piece.strip():
                continue
            passages.append(
                Passage(
                    passage_id=f"{doc_id}#{n}",
                    doc_id=doc_id,
                    locator=sec.locator,
                    text=piece.strip(),
                    heading_path=sec.heading_path,
                )
            )
            n += 1
    return passages


def build_index(
    corpus_root: Path | str, *, secret_dir_name: str = DEFAULT_SECRET_DIR
) -> IndexData:
    root = Path(corpus_root)
    if not root.is_dir():
        raise CorpusNotFoundError(f"语料目录不存在:{root}")

    now = datetime.now(timezone.utc)
    documents: list[Document] = []
    passages: list[Passage] = []
    rejected: list[RejectedFile] = []

    # 排序保证幂等(INV-I1)
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root)
        doc_id = rel.as_posix()
        if path.name.startswith("~$") or path.name.startswith("."):
            continue  # Office 临时文件 / 隐藏文件,不算语料也不算失败

        try:
            sections = parse(path)
        except ProcurementBotError as exc:
            rejected.append(
                RejectedFile(
                    path=doc_id,
                    reason=_human_reason(exc, path),
                    detail=f"{type(exc).__name__}: {exc}",
                    found_at=now,
                )
            )
            continue
        except Exception as exc:  # noqa: BLE001 - 兜底,绝不让一个坏文件炸掉整批
            rejected.append(
                RejectedFile(
                    path=doc_id,
                    reason="文件损坏或无法读取",
                    detail=f"{type(exc).__name__}: {exc}",
                    found_at=now,
                )
            )
            continue

        doc_passages = _chunk(sections, doc_id)
        if not doc_passages:
            rejected.append(
                RejectedFile(
                    path=doc_id,
                    reason="内容为空,没有可检索的文字",
                    detail="parser returned no non-empty sections",
                    found_at=now,
                )
            )
            continue

        sensitivity, category = _classify(rel.parts, secret_dir_name)
        body = "\n".join(p.text for p in doc_passages)
        eff_date, version, confidence = extract_version_info(body, path.name)

        documents.append(
            Document(
                doc_id=doc_id,
                filename=path.name,
                fmt=path.suffix.lower().lstrip("."),
                sensitivity=sensitivity,
                category=category,
                effective_date=eff_date,
                version=version,
                date_confidence=confidence,
                ingested_at=now,
                title_tokens=_title_tokens(path.name),
            )
        )
        passages.extend(doc_passages)

    return IndexData(
        built_at=now,
        corpus_root=str(root),
        documents=tuple(documents),
        passages=tuple(passages),
        rejected=tuple(rejected),
        idf=build_idf(passages),
    )


def _human_reason(exc: Exception, path: Path) -> str:
    from ..errors import ParseError, UnsupportedFormatError

    if isinstance(exc, UnsupportedFormatError):
        return f"不支持的格式({path.suffix or '无扩展名'})"
    if isinstance(exc, ParseError):
        msg = str(exc)
        if "扫描件" in msg or "没有可抽取的文字" in msg:
            return "PDF 中没有文字(可能是扫描件),无法纳入"
        return "文件损坏或加密,无法读取"
    return "无法读取"


# ---------------------------------------------------------------------------
# 持久化
# ---------------------------------------------------------------------------


def save_index(index: IndexData, state_dir: Path | str) -> Path:
    state = Path(state_dir)
    state.mkdir(parents=True, exist_ok=True)
    target = state / INDEX_FILENAME
    target.write_text(
        json.dumps(to_jsonable(index), ensure_ascii=False, indent=2, sort_keys=False),
        encoding="utf-8",
    )
    return target


def load_index(state_dir: Path | str) -> IndexData:
    from datetime import date as _date

    from ..errors import IndexMissingError

    target = Path(state_dir) / INDEX_FILENAME
    if not target.is_file():
        raise IndexMissingError(
            f"索引不存在:{target}。请先运行 `pbot ingest`。"
        )
    raw = json.loads(target.read_text(encoding="utf-8"))

    documents = tuple(
        Document(
            doc_id=d["doc_id"],
            filename=d["filename"],
            fmt=d["fmt"],
            sensitivity=Sensitivity(d["sensitivity"]),
            category=d["category"],
            effective_date=_date.fromisoformat(d["effective_date"])
            if d["effective_date"]
            else None,
            version=d["version"],
            date_confidence=DateConfidence(d["date_confidence"]),
            ingested_at=datetime.fromisoformat(d["ingested_at"]),
            title_tokens=tuple(d["title_tokens"]),
        )
        for d in raw["documents"]
    )
    passages = tuple(
        Passage(
            passage_id=p["passage_id"],
            doc_id=p["doc_id"],
            locator=p["locator"],
            text=p["text"],
            heading_path=tuple(p["heading_path"]),
        )
        for p in raw["passages"]
    )
    rejected = tuple(
        RejectedFile(
            path=r["path"],
            reason=r["reason"],
            detail=r["detail"],
            found_at=datetime.fromisoformat(r["found_at"]),
        )
        for r in raw["rejected"]
    )
    return IndexData(
        built_at=datetime.fromisoformat(raw["built_at"]),
        corpus_root=raw["corpus_root"],
        documents=documents,
        passages=passages,
        rejected=rejected,
        idf={k: float(v) for k, v in raw["idf"].items()},
    )
