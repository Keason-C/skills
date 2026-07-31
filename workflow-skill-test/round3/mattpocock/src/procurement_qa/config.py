"""配置与知识库落盘。

`ingest` 把整个知识库(含正文与摘要)存成一个 JSON,`ask` 直接加载它 ——
否则每问一次都要重新摄取、重新生成摘要,既慢又烧钱。
"""

from __future__ import annotations

import datetime as dt
import json
import tomllib
from dataclasses import dataclass
from pathlib import Path

from .model import Document, IngestReport, Library, SkippedFile

LIBRARY_FILE = "library.json"
DEFAULT_CONFIG = "pqa.toml"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Config:
    knowledge_root: Path
    roster: Path
    runtime: Path
    fallback_employee_id: str
    restricted_dir: str = "保密"

    @property
    def library_path(self) -> Path:
        return self.runtime / LIBRARY_FILE


def load_config(path: Path | str) -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"找不到配置文件 {path}(可以用 --config 指定)")
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    base = path.parent

    def resolve(key: str, default: str | None = None) -> Path:
        raw = data.get(key, default)
        if raw is None:
            raise ConfigError(f"配置文件 {path} 缺少 {key}")
        candidate = Path(raw)
        return candidate if candidate.is_absolute() else (base / candidate).resolve()

    fallback = data.get("fallback_employee_id")
    if not fallback:
        raise ConfigError(f"配置文件 {path} 缺少 fallback_employee_id(兜底接收人的工号)")

    return Config(
        knowledge_root=resolve("knowledge_root"),
        roster=resolve("roster"),
        runtime=resolve("runtime", ".runtime"),
        fallback_employee_id=str(fallback),
        restricted_dir=str(data.get("restricted_dir", "保密")),
    )


def save_library(library: Library, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "documents": [
            {
                "document_id": d.document_id,
                "title": d.title,
                "category": d.category,
                "restricted": d.restricted,
                "text": d.text,
                "source_path": d.source_path,
                "effective_date": d.effective_date.isoformat() if d.effective_date else None,
                "summary": d.summary,
            }
            for d in library.documents
        ],
        "report": {
            "ingested": list(library.report.ingested),
            "skipped": [
                {"path": s.path, "reason": s.reason, "detail": s.detail}
                for s in library.report.skipped
            ],
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_library(path: Path) -> Library:
    if not path.exists():
        raise ConfigError(f"还没有知识库快照({path})。先跑一次 `pqa ingest`。")
    data = json.loads(path.read_text(encoding="utf-8"))
    documents = tuple(
        Document(
            document_id=d["document_id"],
            title=d["title"],
            category=d["category"],
            restricted=d["restricted"],
            text=d["text"],
            source_path=d["source_path"],
            effective_date=dt.date.fromisoformat(d["effective_date"])
            if d["effective_date"]
            else None,
            summary=d.get("summary", ""),
        )
        for d in data["documents"]
    )
    report = IngestReport(
        ingested=tuple(data["report"]["ingested"]),
        skipped=tuple(
            SkippedFile(s["path"], s["reason"], s["detail"]) for s in data["report"]["skipped"]
        ),
    )
    return Library(documents=documents, report=report)
