"""扫描磁盘上的文档库。

密级完全由所在文件夹决定,不做任何内容推断——需求方明确否决了"让机器人自己猜哪个是报价"。
"""

from __future__ import annotations

from pathlib import Path

from .ingest import UnreadableError, parse_sections
from .models import CONFIDENTIAL, PUBLIC, Document, Library, UnreadableFile

ROSTER_FILENAME = "roster.csv"
SKIP_NAMES = {ROSTER_FILENAME, ".gitkeep", ".DS_Store"}


def classify_path(rel: Path) -> tuple[str, str | None]:
    """相对 library 根目录的路径 → (密级, 品类)。

    confidential/<品类>/... → 该品类的保密文档
    confidential/xxx.md     → 未分类保密文档(仅管理员可见)
    其余(public/、registry/、faq/…) → 公开
    """
    parts = rel.parts
    if parts and parts[0] == "confidential":
        category = parts[1] if len(parts) > 2 else None
        return CONFIDENTIAL, category
    return PUBLIC, None


def scan_library(root: Path) -> Library:
    documents: list[Document] = []
    unreadable: list[UnreadableFile] = []
    if not root.exists():
        return Library((), ())
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.name in SKIP_NAMES or path.name.startswith("."):
            continue
        rel = path.relative_to(root)
        classification, category = classify_path(rel)
        try:
            sections = parse_sections(path)
        except UnreadableError as exc:
            unreadable.append(UnreadableFile(path, str(exc)))
            continue
        documents.append(
            Document(
                doc_id=rel.as_posix(),
                title=path.stem,
                path=path,
                classification=classification,
                category=category,
                sections=sections,
            )
        )
    return Library(tuple(documents), tuple(unreadable))
