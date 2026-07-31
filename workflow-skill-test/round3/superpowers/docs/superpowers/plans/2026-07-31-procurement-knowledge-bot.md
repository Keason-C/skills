# 采购品类知识问答机器人 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
> 本轮采用 executing-plans(内联执行),原因见 REFLECTION.md 的适配说明。

**Goal:** 一个命令行采购知识问答机器人:按文件夹判定密级、按名单判定身份、确定性检索 + 上下文预算装载、
模型答案必须通过引用校验闸门,答不上来记入待人工清单并可回填成新文档。

**Architecture:** 分层单元,LLM 藏在 `LLMDriver` 协议后面。检索与权限全部是确定性纯函数(可完整单测);
模型只负责"读给定材料、组织语言、报出引用",系统侧校验引用是否指向本次真实装载的文档,不合格一律降级为无答案。

**Tech Stack:** Python 3.11 + uv;`python-docx` / `pypdf` / `openpyxl` 解析;`argparse` CLI(不引入 typer);
`pytest` 测试;`reportlab` 仅用于测试期生成 PDF fixture;`anthropic` SDK 仅在真实 driver 中 import(测试从不触发)。

## Global Constraints

- Python 3.11,依赖用 `uv` 管理(`pyproject.toml` + `uv run`)。
- **所有测试必须离线可跑。** 真实 LLM 调用只存在于 `AnthropicDriver`,测试从不实例化它。
- 真实模型 ID 为 `claude-opus-5`;不传 `temperature` / `top_p` / `top_k`(该模型会 400);不传 `thinking`(默认即自适应)。
- 不引入向量库 / embedding / 任何检索模型(需求方明确否决)。
- 密级按整份文档算,由文件夹决定,机器人不猜密级。
- 品类经理只能看自己负责品类的保密文档;未分类保密文档仅管理员可见。
- 名单里没有的工号 → 拒绝服务,不降级为最低权限。
- 回答必须带出处;引用校验不通过一律降级为 `no_answer`。
- 所有用户可见文案用中文。
- 本地 git commit,绝不 push。

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `pyproject.toml` | 依赖与 pytest 配置 |
| `src/pkbot/models.py` | 所有数据结构(frozen dataclass)+ token 估算 |
| `src/pkbot/identity.py` | 读 `roster.csv` → `User`;未知工号抛 `UnknownUserError` |
| `src/pkbot/ingest.py` | 单文件 → `tuple[Section, ...]`;不认识/读不了 → `UnreadableFile` |
| `src/pkbot/library.py` | 扫目录 → `Library`(可读文档 + 读不了清单);密级/品类由路径决定 |
| `src/pkbot/access.py` | 纯函数:(User, Library) → (可见文档, 不可见文档) |
| `src/pkbot/retrieval.py` | 纯函数:关键词打分 + 上下文预算装载 → `ContextPack` |
| `src/pkbot/drivers.py` | `LLMDriver` 协议 + `MockDriver` / `ScriptedDriver` |
| `src/pkbot/anthropic_driver.py` | 真实调用,只写不跑,单独文件便于测试断言它未被 import 使用 |
| `src/pkbot/answering.py` | 组 prompt → 解析 JSON → **引用校验闸门** → `Answer` |
| `src/pkbot/gaps.py` | 提问日志 / 周报 / 人工补答回填新文档 |
| `src/pkbot/cli.py` | argparse 命令组装 |
| `tests/conftest.py` | 生成真实 .docx/.xlsx/.pdf fixture + 演示库 |
| `tests/test_*.py` | 与上述模块一一对应 |
| `demo/` | 演示文档库(随仓库提交) |
| `README.md` | 使用说明 + 演示路径 |

---

### Task 1: 项目骨架与数据模型

**Files:**
- Create: `pyproject.toml`, `src/pkbot/__init__.py`, `src/pkbot/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: 无
- Produces: `Section(locator: str, text: str)`; `Document(doc_id, title, path, classification, category, sections)`;
  `UnreadableFile(path, reason)`; `Library(documents, unreadable)`; `User(employee_id, name, role, categories)`;
  `LoadedDoc(doc_id, title, sections, partial)`; `ContextPack(docs, skipped_oversized)`;
  `Citation(doc_id, locator)`; `Answer(status, text, citations, notes)`; `estimate_tokens(text) -> int`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_models.py
from pathlib import Path
from pkbot.models import Document, Section, estimate_tokens, ContextPack, LoadedDoc

def test_estimate_tokens_counts_characters():
    assert estimate_tokens("不锈钢紧固件") == 6
    assert estimate_tokens("") == 0

def test_document_token_estimate_sums_sections():
    doc = Document(
        doc_id="public/a.md", title="A", path=Path("/x/a.md"),
        classification="public", category=None,
        sections=(Section("第 1 节", "abc"), Section("第 2 节", "de")),
    )
    assert doc.token_estimate == 5
    assert doc.full_text == "abc\nde"

def test_context_pack_doc_ids():
    pack = ContextPack(
        docs=(LoadedDoc("a", "A", (Section("全文", "x"),), False),),
        skipped_oversized=("大文件",),
    )
    assert pack.doc_ids == {"a"}
```

- [ ] **Step 2: 运行确认失败**

Run: `cd <project> && uv run pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pkbot'`

- [ ] **Step 3: 写最小实现**

`pyproject.toml`:

```toml
[project]
name = "pkbot"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["python-docx>=1.1", "pypdf>=4.0", "openpyxl>=3.1"]

[project.optional-dependencies]
llm = ["anthropic>=0.40"]

[dependency-groups]
dev = ["pytest>=8.0", "reportlab>=4.0"]

[project.scripts]
pkbot = "pkbot.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pkbot"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
```

`src/pkbot/models.py`:

```python
"""所有跨模块共享的数据结构。全部 frozen,便于在纯函数之间安全传递。"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

PUBLIC = "public"
CONFIDENTIAL = "confidential"

ROLE_BUYER = "采购员"
ROLE_CATEGORY_MANAGER = "品类经理"
ROLE_ADMIN = "管理员"


def estimate_tokens(text: str) -> int:
    """确定性 token 估算:中文一字约一 token,英文偏保守。够用且可测。"""
    return len(text)


@dataclass(frozen=True)
class Section:
    locator: str   # 人类可读的出处,例如 "第 3 页" / "工作表 报价 第 1-200 行"
    text: str

    @property
    def token_estimate(self) -> int:
        return estimate_tokens(self.text)


@dataclass(frozen=True)
class Document:
    doc_id: str            # 相对 library 根目录的 posix 路径,稳定且人类可读
    title: str
    path: Path
    classification: str    # PUBLIC | CONFIDENTIAL
    category: str | None   # 仅保密文档有;None 表示未分类
    sections: tuple[Section, ...]

    @property
    def token_estimate(self) -> int:
        return sum(s.token_estimate for s in self.sections)

    @property
    def full_text(self) -> str:
        return "\n".join(s.text for s in self.sections)


@dataclass(frozen=True)
class UnreadableFile:
    path: Path
    reason: str


@dataclass(frozen=True)
class Library:
    documents: tuple[Document, ...]
    unreadable: tuple[UnreadableFile, ...]


@dataclass(frozen=True)
class User:
    employee_id: str
    name: str
    role: str
    categories: tuple[str, ...]


@dataclass(frozen=True)
class LoadedDoc:
    doc_id: str
    title: str
    sections: tuple[Section, ...]
    partial: bool          # True 表示只装载了部分小节


@dataclass(frozen=True)
class ContextPack:
    docs: tuple[LoadedDoc, ...]
    skipped_oversized: tuple[str, ...]   # 因太大完全没读的文档标题

    @property
    def doc_ids(self) -> set[str]:
        return {d.doc_id for d in self.docs}


@dataclass(frozen=True)
class Citation:
    doc_id: str
    locator: str


@dataclass(frozen=True)
class Answer:
    status: str            # answered | no_answer | denied
    text: str
    citations: tuple[Citation, ...] = ()
    notes: tuple[str, ...] = ()
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS(3 passed)

- [ ] **Step 5: 提交**

```bash
git add pyproject.toml src/pkbot/__init__.py src/pkbot/models.py tests/test_models.py
git commit -m "feat: project skeleton and core data models"
```

---

### Task 2: 身份识别(名单文件)

**Files:**
- Create: `src/pkbot/identity.py`
- Test: `tests/test_identity.py`

**Interfaces:**
- Consumes: `models.User`, `ROLE_*` 常量
- Produces: `load_roster(path: Path) -> dict[str, User]`;`get_user(roster, employee_id) -> User`;
  异常 `UnknownUserError(Exception)`、`RosterError(Exception)`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_identity.py
import pytest
from pkbot.identity import load_roster, get_user, UnknownUserError, RosterError
from pkbot.models import ROLE_CATEGORY_MANAGER

ROSTER = "工号,姓名,角色,负责品类\nG0042,李四,采购员,\nG0007,王五,品类经理,紧固件;电子元器件\n"

def test_load_roster_parses_categories(tmp_path):
    p = tmp_path / "roster.csv"
    p.write_text(ROSTER, encoding="utf-8")
    roster = load_roster(p)
    assert roster["G0007"].role == ROLE_CATEGORY_MANAGER
    assert roster["G0007"].categories == ("紧固件", "电子元器件")
    assert roster["G0042"].categories == ()

def test_unknown_employee_is_rejected(tmp_path):
    p = tmp_path / "roster.csv"
    p.write_text(ROSTER, encoding="utf-8")
    roster = load_roster(p)
    with pytest.raises(UnknownUserError) as exc:
        get_user(roster, "G9999")
    assert "管理员" in str(exc.value)

def test_bad_role_rejected(tmp_path):
    p = tmp_path / "roster.csv"
    p.write_text("工号,姓名,角色,负责品类\nG1,张三,老板,\n", encoding="utf-8")
    with pytest.raises(RosterError):
        load_roster(p)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_identity.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pkbot.identity'`

- [ ] **Step 3: 写最小实现**

```python
# src/pkbot/identity.py
"""从管理员维护的 CSV 名单解析身份。名单里没有的工号一律拒绝服务。"""
from __future__ import annotations

import csv
from pathlib import Path

from .models import ROLE_ADMIN, ROLE_BUYER, ROLE_CATEGORY_MANAGER, User

VALID_ROLES = {ROLE_BUYER, ROLE_CATEGORY_MANAGER, ROLE_ADMIN}
REQUIRED_COLUMNS = ["工号", "姓名", "角色", "负责品类"]


class RosterError(Exception):
    """名单文件本身有问题(缺列、角色非法)。"""


class UnknownUserError(Exception):
    """工号不在名单里。"""


def load_roster(path: Path) -> dict[str, User]:
    if not path.exists():
        raise RosterError(f"找不到名单文件:{path}。请管理员创建后再使用。")
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        missing = [c for c in REQUIRED_COLUMNS if c not in (reader.fieldnames or [])]
        if missing:
            raise RosterError(f"名单文件缺少列:{'、'.join(missing)}")
        roster: dict[str, User] = {}
        for row in reader:
            emp = (row["工号"] or "").strip()
            if not emp:
                continue
            role = (row["角色"] or "").strip()
            if role not in VALID_ROLES:
                raise RosterError(
                    f"工号 {emp} 的角色 '{role}' 不认识,只能是:{'、'.join(sorted(VALID_ROLES))}"
                )
            raw = (row["负责品类"] or "").strip()
            categories = tuple(c.strip() for c in raw.split(";") if c.strip())
            roster[emp] = User(emp, (row["姓名"] or "").strip(), role, categories)
    return roster


def get_user(roster: dict[str, User], employee_id: str) -> User:
    user = roster.get(employee_id.strip())
    if user is None:
        raise UnknownUserError(
            f"工号 {employee_id} 不在名单里,无法确认你的身份和权限。请联系管理员把你加进名单。"
        )
    return user
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_identity.py -v`
Expected: PASS(3 passed)

- [ ] **Step 5: 提交**

```bash
git add src/pkbot/identity.py tests/test_identity.py
git commit -m "feat: roster-based identity with hard rejection of unknown employees"
```

---

### Task 3: 文档解析(含读不了的诚实报告)

**Files:**
- Create: `src/pkbot/ingest.py`
- Test: `tests/test_ingest.py`, `tests/conftest.py`

**Interfaces:**
- Consumes: `models.Section`
- Produces: `parse_sections(path: Path) -> tuple[Section, ...]`;异常 `UnreadableError(Exception)`;
  常量 `SUPPORTED_SUFFIXES: set[str]`;`MAX_ROWS_PER_SECTION = 200`

- [ ] **Step 1: 写失败测试(含真实 fixture 文件生成)**

```python
# tests/conftest.py
import pytest
from docx import Document as DocxDocument
from openpyxl import Workbook
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas


@pytest.fixture
def docx_file(tmp_path):
    p = tmp_path / "谈判纪要.docx"
    d = DocxDocument()
    d.add_heading("一、背景", level=1)
    d.add_paragraph("2025 年度紧固件年框谈判。")
    d.add_heading("二、结论", level=1)
    d.add_paragraph("单价下降 3%。")
    d.save(p)
    return p


@pytest.fixture
def xlsx_file(tmp_path):
    p = tmp_path / "对照表.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "品类负责人"
    ws.append(["品类", "负责人", "工号"])
    ws.append(["紧固件", "王五", "G0007"])
    wb.save(p)
    return p


@pytest.fixture
def pdf_file(tmp_path):
    # PDF fixture 内容用 ASCII,避免依赖 CJK 字体;解析器是格式级的,内容语言无关。
    p = tmp_path / "tender.pdf"
    c = canvas.Canvas(str(p), pagesize=A4)
    c.drawString(72, 720, "SECTION 3 TECHNICAL SPEC")
    c.drawString(72, 700, "Bolt M8x30 GB/T 5783")
    c.showPage()
    c.drawString(72, 720, "SECTION 4 DELIVERY TERMS")
    c.showPage()
    c.save()
    return p
```

```python
# tests/test_ingest.py
import pytest
from pkbot.ingest import parse_sections, UnreadableError

def test_markdown_split_by_headings(tmp_path):
    p = tmp_path / "流程.md"
    p.write_text("# 采购流程\n请款前先立项。\n## 审批\n三级审批。\n", encoding="utf-8")
    sections = parse_sections(p)
    assert [s.locator for s in sections] == ["采购流程", "审批"]
    assert "请款前先立项" in sections[0].text

def test_plain_text_single_section(tmp_path):
    p = tmp_path / "notes.txt"
    p.write_text("随手记的一段话", encoding="utf-8")
    sections = parse_sections(p)
    assert len(sections) == 1
    assert sections[0].locator == "全文"

def test_docx_headings_become_sections(docx_file):
    sections = parse_sections(docx_file)
    assert [s.locator for s in sections] == ["一、背景", "二、结论"]
    assert "单价下降 3%" in sections[1].text

def test_xlsx_sheet_becomes_section(xlsx_file):
    sections = parse_sections(xlsx_file)
    assert sections[0].locator.startswith("工作表 品类负责人")
    assert "紧固件" in sections[0].text and "王五" in sections[0].text

def test_pdf_one_section_per_page(pdf_file):
    sections = parse_sections(pdf_file)
    assert len(sections) == 2
    assert sections[0].locator == "第 1 页"
    assert "M8x30" in sections[0].text

def test_unknown_format_is_reported_not_guessed(tmp_path):
    p = tmp_path / "扫描件.wps"
    p.write_bytes(b"\x00\x01binary")
    with pytest.raises(UnreadableError) as exc:
        parse_sections(p)
    assert ".wps" in str(exc.value)

def test_empty_file_is_reported(tmp_path):
    p = tmp_path / "空的.txt"
    p.write_text("   \n", encoding="utf-8")
    with pytest.raises(UnreadableError) as exc:
        parse_sections(p)
    assert "没有可提取的文字" in str(exc.value)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_ingest.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pkbot.ingest'`

- [ ] **Step 3: 写最小实现**

```python
# src/pkbot/ingest.py
"""把各种格式的文件变成带出处标记的文本小节。读不了就明说,绝不猜内容。"""
from __future__ import annotations

import csv
from pathlib import Path

from .models import Section

MAX_ROWS_PER_SECTION = 200


class UnreadableError(Exception):
    """这份文件读不了,附带人类看得懂的原因。"""


def _sections_from_markdown(text: str) -> tuple[Section, ...]:
    lines = text.splitlines()
    sections: list[Section] = []
    title = "全文"
    buf: list[str] = []
    for line in lines:
        if line.startswith("#"):
            if buf and any(b.strip() for b in buf):
                sections.append(Section(title, "\n".join(buf).strip()))
            title = line.lstrip("#").strip() or "全文"
            buf = []
        else:
            buf.append(line)
    if buf and any(b.strip() for b in buf):
        sections.append(Section(title, "\n".join(buf).strip()))
    return tuple(sections)


def _parse_text(path: Path) -> tuple[Section, ...]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.strip():
        return ()
    if path.suffix.lower() == ".md":
        sections = _sections_from_markdown(text)
        if sections:
            return sections
    return (Section("全文", text.strip()),)


def _parse_docx(path: Path) -> tuple[Section, ...]:
    from docx import Document as DocxDocument

    doc = DocxDocument(str(path))
    sections: list[Section] = []
    title = "全文"
    buf: list[str] = []

    def flush() -> None:
        if buf and any(b.strip() for b in buf):
            sections.append(Section(title, "\n".join(buf).strip()))

    for para in doc.paragraphs:
        style = (para.style.name or "") if para.style is not None else ""
        is_heading = style.startswith("Heading") or style.startswith("标题")
        if is_heading and para.text.strip():
            flush()
            title = para.text.strip()
            buf = []
        elif para.text.strip():
            buf.append(para.text)
    flush()

    for idx, table in enumerate(doc.tables, start=1):
        rows = ["\t".join(cell.text.strip() for cell in row.cells) for row in table.rows]
        body = "\n".join(r for r in rows if r.strip())
        if body:
            sections.append(Section(f"表格 {idx}", body))
    return tuple(sections)


def _rows_to_sections(label: str, rows: list[list[str]]) -> list[Section]:
    out: list[Section] = []
    for start in range(0, len(rows), MAX_ROWS_PER_SECTION):
        chunk = rows[start : start + MAX_ROWS_PER_SECTION]
        body = "\n".join("\t".join(c for c in row) for row in chunk if any(c.strip() for c in row))
        if body:
            out.append(Section(f"{label} 第 {start + 1}-{start + len(chunk)} 行", body))
    return out


def _parse_xlsx(path: Path) -> tuple[Section, ...]:
    from openpyxl import load_workbook

    wb = load_workbook(str(path), read_only=True, data_only=True)
    sections: list[Section] = []
    for ws in wb.worksheets:
        rows = [
            ["" if c is None else str(c) for c in row]
            for row in ws.iter_rows(values_only=True)
        ]
        sections.extend(_rows_to_sections(f"工作表 {ws.title}", rows))
    wb.close()
    return tuple(sections)


def _parse_csv(path: Path) -> tuple[Section, ...]:
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = [list(r) for r in csv.reader(fh)]
    return tuple(_rows_to_sections("表格", rows))


def _parse_pdf(path: Path) -> tuple[Section, ...]:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted:
            raise UnreadableError(f"{path.name}:PDF 已加密,打不开。")
        sections: list[Section] = []
        for idx, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                sections.append(Section(f"第 {idx} 页", text))
        return tuple(sections)
    except UnreadableError:
        raise
    except (PdfReadError, OSError, ValueError) as exc:
        raise UnreadableError(f"{path.name}:PDF 解析失败({exc})。") from exc


_PARSERS = {
    ".md": _parse_text,
    ".txt": _parse_text,
    ".docx": _parse_docx,
    ".xlsx": _parse_xlsx,
    ".csv": _parse_csv,
    ".pdf": _parse_pdf,
}

SUPPORTED_SUFFIXES = set(_PARSERS)


def parse_sections(path: Path) -> tuple[Section, ...]:
    parser = _PARSERS.get(path.suffix.lower())
    if parser is None:
        raise UnreadableError(
            f"{path.name}:不支持的格式 {path.suffix or '(无扩展名)'},"
            f"目前只认 {'、'.join(sorted(SUPPORTED_SUFFIXES))}。"
        )
    try:
        sections = parser(path)
    except UnreadableError:
        raise
    except Exception as exc:  # 解析库五花八门,统一转成人话
        raise UnreadableError(f"{path.name}:读取失败({type(exc).__name__}: {exc})。") from exc
    if not sections:
        raise UnreadableError(
            f"{path.name}:没有可提取的文字(可能是扫描件或空文件)。"
        )
    return sections
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_ingest.py -v`
Expected: PASS(7 passed)

- [ ] **Step 5: 提交**

```bash
git add src/pkbot/ingest.py tests/test_ingest.py tests/conftest.py
git commit -m "feat: multi-format document ingestion with honest unreadable reporting"
```

---

### Task 4: 文档库扫描与密级判定

**Files:**
- Create: `src/pkbot/library.py`
- Test: `tests/test_library.py`

**Interfaces:**
- Consumes: `ingest.parse_sections`、`ingest.UnreadableError`、`models.Document/UnreadableFile/Library`
- Produces: `scan_library(root: Path) -> Library`;`classify_path(rel: Path) -> tuple[str, str | None]`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_library.py
from pathlib import Path
from pkbot.library import scan_library, classify_path
from pkbot.models import PUBLIC, CONFIDENTIAL

def _write(root: Path, rel: str, text: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")

def test_classify_path_rules():
    assert classify_path(Path("public/a.md")) == (PUBLIC, None)
    assert classify_path(Path("registry/b.csv")) == (PUBLIC, None)
    assert classify_path(Path("confidential/紧固件/c.md")) == (CONFIDENTIAL, "紧固件")
    assert classify_path(Path("confidential/d.md")) == (CONFIDENTIAL, None)

def test_scan_collects_documents_and_unreadables(tmp_path):
    _write(tmp_path, "public/流程.md", "# 流程\n先立项。")
    _write(tmp_path, "confidential/紧固件/纪要.md", "# 纪要\n单价下降。")
    (tmp_path / "public" / "扫描件.wps").write_bytes(b"\x00")
    (tmp_path / "roster.csv").write_text("工号,姓名,角色,负责品类\n", encoding="utf-8")

    lib = scan_library(tmp_path)
    ids = {d.doc_id for d in lib.documents}
    assert ids == {"public/流程.md", "confidential/紧固件/纪要.md"}
    assert [u.path.name for u in lib.unreadable] == ["扫描件.wps"]

def test_roster_file_is_not_a_document(tmp_path):
    (tmp_path / "roster.csv").write_text("工号,姓名,角色,负责品类\n", encoding="utf-8")
    _write(tmp_path, "public/a.md", "# A\nhello")
    lib = scan_library(tmp_path)
    assert all("roster" not in d.doc_id for d in lib.documents)
    assert all("roster" not in u.path.name for u in lib.unreadable)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_library.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pkbot.library'`

- [ ] **Step 3: 写最小实现**

```python
# src/pkbot/library.py
"""扫描磁盘上的文档库。密级完全由所在文件夹决定,不做任何内容推断。"""
from __future__ import annotations

from pathlib import Path

from .ingest import UnreadableError, parse_sections
from .models import CONFIDENTIAL, PUBLIC, Document, Library, UnreadableFile

ROSTER_FILENAME = "roster.csv"
SKIP_NAMES = {ROSTER_FILENAME, ".gitkeep", ".DS_Store"}


def classify_path(rel: Path) -> tuple[str, str | None]:
    """相对 library 根目录的路径 → (密级, 品类)。"""
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
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_library.py -v`
Expected: PASS(3 passed)

- [ ] **Step 5: 提交**

```bash
git add src/pkbot/library.py tests/test_library.py
git commit -m "feat: library scan with folder-derived classification"
```

---

### Task 5: 权限闸门

**Files:**
- Create: `src/pkbot/access.py`
- Test: `tests/test_access.py`

**Interfaces:**
- Consumes: `models.Document/Library/User`、`ROLE_*`、`CONFIDENTIAL`
- Produces: `partition(user: User, library: Library) -> Visibility`,其中
  `Visibility(visible: tuple[Document, ...], hidden: tuple[Document, ...])`;
  `owners_for_category(roster: dict[str, User], category: str | None) -> tuple[str, ...]`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_access.py
from pathlib import Path
from pkbot.access import partition, owners_for_category
from pkbot.models import (CONFIDENTIAL, PUBLIC, ROLE_ADMIN, ROLE_BUYER,
                          ROLE_CATEGORY_MANAGER, Document, Library, Section, User)

def _doc(doc_id, classification, category=None):
    return Document(doc_id, doc_id, Path(doc_id), classification, category,
                    (Section("全文", "内容"),))

LIB = Library(
    documents=(
        _doc("public/流程.md", PUBLIC),
        _doc("confidential/紧固件/纪要.md", CONFIDENTIAL, "紧固件"),
        _doc("confidential/电子元器件/报价.md", CONFIDENTIAL, "电子元器件"),
        _doc("confidential/未分类.md", CONFIDENTIAL, None),
    ),
    unreadable=(),
)

def test_buyer_sees_only_public():
    v = partition(User("G1", "李四", ROLE_BUYER, ()), LIB)
    assert {d.doc_id for d in v.visible} == {"public/流程.md"}
    assert len(v.hidden) == 3

def test_manager_sees_only_own_categories():
    v = partition(User("G2", "王五", ROLE_CATEGORY_MANAGER, ("紧固件",)), LIB)
    assert {d.doc_id for d in v.visible} == {"public/流程.md", "confidential/紧固件/纪要.md"}
    assert {d.doc_id for d in v.hidden} == {
        "confidential/电子元器件/报价.md", "confidential/未分类.md"}

def test_uncategorised_confidential_is_admin_only():
    admin = partition(User("G3", "赵六", ROLE_ADMIN, ()), LIB)
    assert len(admin.visible) == 4 and admin.hidden == ()

def test_owners_for_category():
    roster = {
        "G2": User("G2", "王五", ROLE_CATEGORY_MANAGER, ("紧固件",)),
        "G1": User("G1", "李四", ROLE_BUYER, ()),
    }
    assert owners_for_category(roster, "紧固件") == ("王五",)
    assert owners_for_category(roster, "不存在的品类") == ()
    assert owners_for_category(roster, None) == ()
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_access.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pkbot.access'`

- [ ] **Step 3: 写最小实现**

```python
# src/pkbot/access.py
"""唯一的权限闸门。前置于一切检索——不可见的文档从不进入打分和上下文。"""
from __future__ import annotations

from dataclasses import dataclass

from .models import (CONFIDENTIAL, ROLE_ADMIN, ROLE_CATEGORY_MANAGER,
                     Document, Library, User)


@dataclass(frozen=True)
class Visibility:
    visible: tuple[Document, ...]
    hidden: tuple[Document, ...]


def _can_see(user: User, doc: Document) -> bool:
    if doc.classification != CONFIDENTIAL:
        return True
    if user.role == ROLE_ADMIN:
        return True
    if user.role == ROLE_CATEGORY_MANAGER and doc.category is not None:
        return doc.category in user.categories
    return False


def partition(user: User, library: Library) -> Visibility:
    visible = tuple(d for d in library.documents if _can_see(user, d))
    hidden = tuple(d for d in library.documents if not _can_see(user, d))
    return Visibility(visible, hidden)


def owners_for_category(roster: dict[str, User], category: str | None) -> tuple[str, ...]:
    """找出负责某品类的品类经理姓名,用于'转给谁'提示。"""
    if not category:
        return ()
    return tuple(
        u.name for u in roster.values()
        if u.role == ROLE_CATEGORY_MANAGER and category in u.categories
    )
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_access.py -v`
Expected: PASS(4 passed)

- [ ] **Step 5: 提交**

```bash
git add src/pkbot/access.py tests/test_access.py
git commit -m "feat: access control gate with per-category manager isolation"
```

---

### Task 6: 确定性检索与上下文预算

**Files:**
- Create: `src/pkbot/retrieval.py`
- Test: `tests/test_retrieval.py`

**Interfaces:**
- Consumes: `models.Document/Section/LoadedDoc/ContextPack/estimate_tokens`
- Produces: `tokenize(text: str) -> list[str]`;`score_document(terms, doc, corpus_size, df) -> float`;
  `rank(question: str, docs) -> list[tuple[Document, float]]`;
  `build_context(question: str, docs, budget: int = 100_000) -> ContextPack`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_retrieval.py
from pathlib import Path
from pkbot.retrieval import tokenize, rank, build_context
from pkbot.models import PUBLIC, Document, Section

def _doc(doc_id, sections):
    return Document(doc_id, doc_id, Path(doc_id), PUBLIC, None, tuple(sections))

def test_tokenize_handles_cjk_bigrams_and_latin():
    toks = tokenize("紧固件 M8x30")
    assert "紧固" in toks and "固件" in toks and "m8x30" in toks

def test_rank_puts_matching_document_first():
    docs = [
        _doc("a.md", [Section("全文", "办公用品采购流程说明")]),
        _doc("b.md", [Section("全文", "不锈钢紧固件规格与供应商")]),
    ]
    ranked = rank("紧固件供应商有哪些", docs)
    assert ranked[0][0].doc_id == "b.md"
    assert ranked[0][1] > 0

def test_unrelated_documents_score_zero_and_are_dropped():
    docs = [_doc("a.md", [Section("全文", "办公用品采购流程")])]
    pack = build_context("电子元器件价格", docs, budget=1000)
    assert pack.docs == ()

def test_oversized_document_falls_back_to_matching_sections():
    big = _doc("big.md", [
        Section("第 1 章", "无关内容" * 200),
        Section("第 9 章", "紧固件技术规格要求" * 5),
    ])
    pack = build_context("紧固件技术规格", [big], budget=200)
    assert len(pack.docs) == 1
    loaded = pack.docs[0]
    assert loaded.partial is True
    assert [s.locator for s in loaded.sections] == ["第 9 章"]

def test_document_too_big_for_any_section_is_reported_as_skipped():
    huge = _doc("huge.md", [Section("全文", "紧固件" * 500)])
    pack = build_context("紧固件", [huge], budget=100)
    assert pack.docs == ()
    assert pack.skipped_oversized == ("huge.md",)

def test_full_document_loaded_when_it_fits():
    doc = _doc("small.md", [Section("全文", "紧固件供应商:甲乙丙")])
    pack = build_context("紧固件供应商", [doc], budget=10_000)
    assert pack.docs[0].partial is False
    assert pack.doc_ids == {"small.md"}
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_retrieval.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pkbot.retrieval'`

- [ ] **Step 3: 写最小实现**

```python
# src/pkbot/retrieval.py
"""确定性检索:关键词打分 + 上下文预算装载。不含任何模型调用,可完整单测。"""
from __future__ import annotations

import math
import re
from collections import Counter

from .models import ContextPack, Document, LoadedDoc, Section, estimate_tokens

DEFAULT_BUDGET = 100_000
_LATIN = re.compile(r"[a-zA-Z0-9_./x-]+")
_CJK = re.compile(r"[一-鿿]")


def tokenize(text: str) -> list[str]:
    """中文取相邻二字组合,英文/编号取单词。纯字符串处理,结果稳定。"""
    tokens = [m.group(0).lower() for m in _LATIN.finditer(text)]
    cjk = [ch for ch in text if _CJK.match(ch)]
    # 连续中文的二元组;单字也保留,便于单字品类词命中
    runs: list[str] = []
    current: list[str] = []
    for ch in text:
        if _CJK.match(ch):
            current.append(ch)
        elif current:
            runs.append("".join(current))
            current = []
    if current:
        runs.append("".join(current))
    for run in runs:
        tokens.extend(run[i : i + 2] for i in range(len(run) - 1))
        if len(run) == 1:
            tokens.append(run)
    if not runs and cjk:
        tokens.extend(cjk)
    return tokens


def _term_freq(text: str) -> Counter[str]:
    return Counter(tokenize(text))


def score_document(
    query_terms: set[str], tf: Counter[str], corpus_size: int, df: Counter[str]
) -> float:
    score = 0.0
    for term in query_terms:
        freq = tf.get(term, 0)
        if freq == 0:
            continue
        idf = math.log(1 + corpus_size / (1 + df.get(term, 0)))
        score += (1 + math.log(freq)) * idf
    return score


def rank(question: str, docs: list[Document]) -> list[tuple[Document, float]]:
    query_terms = set(tokenize(question))
    if not query_terms or not docs:
        return []
    tfs = {d.doc_id: _term_freq(d.full_text) for d in docs}
    df: Counter[str] = Counter()
    for tf in tfs.values():
        df.update(set(tf))
    scored = [
        (d, score_document(query_terms, tfs[d.doc_id], len(docs), df)) for d in docs
    ]
    scored = [(d, s) for d, s in scored if s > 0]
    scored.sort(key=lambda pair: (-pair[1], pair[0].doc_id))
    return scored


def _rank_sections(query_terms: set[str], sections: tuple[Section, ...]) -> list[Section]:
    scored: list[tuple[float, int, Section]] = []
    for idx, sec in enumerate(sections):
        tf = _term_freq(sec.text)
        hits = sum(tf.get(t, 0) for t in query_terms)
        if hits:
            scored.append((float(hits), idx, sec))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [s for _, _, s in scored]


def build_context(
    question: str, docs: list[Document], budget: int = DEFAULT_BUDGET
) -> ContextPack:
    """按相关度装载:装得下整篇就整篇,装不下就只装命中的小节,再装不下就如实跳过。"""
    query_terms = set(tokenize(question))
    ranked = rank(question, docs)
    remaining = budget
    loaded: list[LoadedDoc] = []
    skipped: list[str] = []

    for doc, _score in ranked:
        if doc.token_estimate <= remaining:
            loaded.append(LoadedDoc(doc.doc_id, doc.title, doc.sections, partial=False))
            remaining -= doc.token_estimate
            continue
        picked: list[Section] = []
        for sec in _rank_sections(query_terms, doc.sections):
            if sec.token_estimate <= remaining:
                picked.append(sec)
                remaining -= sec.token_estimate
        if picked:
            ordered = tuple(s for s in doc.sections if s in picked)
            loaded.append(LoadedDoc(doc.doc_id, doc.title, ordered, partial=True))
        else:
            skipped.append(doc.title)
    return ContextPack(tuple(loaded), tuple(skipped))
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_retrieval.py -v`
Expected: PASS(6 passed)

- [ ] **Step 5: 提交**

```bash
git add src/pkbot/retrieval.py tests/test_retrieval.py
git commit -m "feat: deterministic keyword retrieval with context budgeting"
```

---

### Task 7: LLM driver 接口与离线实现

**Files:**
- Create: `src/pkbot/drivers.py`, `src/pkbot/anthropic_driver.py`
- Test: `tests/test_drivers.py`

**Interfaces:**
- Consumes: 无
- Produces: `LLMDriver` Protocol,方法 `complete(self, system: str, user: str) -> str`;
  `MockDriver(responses: list[str])`(按序返回,记录 `calls`);
  `ScriptedDriver(rules: list[tuple[str, str]], default: str)`(按关键词匹配,离线演示用);
  `anthropic_driver.AnthropicDriver(model: str = "claude-opus-5", max_tokens: int = 4096)`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_drivers.py
import sys
import pytest
from pkbot.drivers import LLMDriver, MockDriver, ScriptedDriver

def test_mock_driver_returns_in_order_and_records_calls():
    d = MockDriver(["一", "二"])
    assert d.complete("sys", "u1") == "一"
    assert d.complete("sys", "u2") == "二"
    assert [c[1] for c in d.calls] == ["u1", "u2"]

def test_mock_driver_raises_when_exhausted():
    d = MockDriver(["只有一条"])
    d.complete("s", "u")
    with pytest.raises(AssertionError):
        d.complete("s", "u")

def test_scripted_driver_matches_keyword_else_default():
    d = ScriptedDriver([("紧固件", "命中")], default="兜底")
    assert d.complete("s", "问紧固件的事") == "命中"
    assert d.complete("s", "别的问题") == "兜底"

def test_mock_and_scripted_satisfy_protocol():
    assert isinstance(MockDriver([]), LLMDriver)
    assert isinstance(ScriptedDriver([], "x"), LLMDriver)

def test_anthropic_sdk_is_never_imported_during_tests():
    """工程红线:真实 LLM 调用只写不跑。测试进程里不允许出现 anthropic 模块。"""
    assert "anthropic" not in sys.modules
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_drivers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pkbot.drivers'`

- [ ] **Step 3: 写最小实现**

```python
# src/pkbot/drivers.py
"""LLM 边界。真实调用在 anthropic_driver.py,测试只用这里的确定性实现。"""
from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LLMDriver(Protocol):
    def complete(self, system: str, user: str) -> str:
        """给定 system / user 文本,返回模型的原始文本输出。"""
        ...


class MockDriver:
    """按序返回预设响应,并记录调用,供单测断言。"""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        assert self._responses, "MockDriver 预设响应已用完,但又被调用了一次"
        return self._responses.pop(0)


class ScriptedDriver:
    """按关键词匹配返回响应,供离线演示使用——不联网、结果可复现。"""

    def __init__(self, rules: list[tuple[str, str]], default: str) -> None:
        self._rules = list(rules)
        self._default = default
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        for keyword, response in self._rules:
            if keyword in user:
                return response
        return self._default
```

```python
# src/pkbot/anthropic_driver.py
"""真实 LLM 调用。**只写不跑**:测试从不实例化本类,CLI 需显式 --driver anthropic 才会用到。

需要 `uv sync --extra llm` 安装 anthropic SDK,并设置 ANTHROPIC_API_KEY。
"""
from __future__ import annotations


class AnthropicDriver:
    def __init__(self, model: str = "claude-opus-5", max_tokens: int = 4096) -> None:
        self.model = model
        self.max_tokens = max_tokens
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            import anthropic  # 延迟导入:没装 SDK 时不影响其余功能

            self._client = anthropic.Anthropic()
        return self._client

    def complete(self, system: str, user: str) -> str:
        client = self._ensure_client()
        # 注意:claude-opus-5 不接受 temperature / top_p / top_k;thinking 默认开启,无需传。
        response = client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if response.stop_reason == "refusal":
            return ""
        return "".join(b.text for b in response.content if b.type == "text")
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_drivers.py -v`
Expected: PASS(5 passed)

- [ ] **Step 5: 提交**

```bash
git add src/pkbot/drivers.py src/pkbot/anthropic_driver.py tests/test_drivers.py
git commit -m "feat: LLM driver protocol with offline mock and scripted implementations"
```

---

### Task 8: 问答内核与引用校验闸门

**Files:**
- Create: `src/pkbot/answering.py`
- Test: `tests/test_answering.py`

**Interfaces:**
- Consumes: `drivers.LLMDriver`、`models.ContextPack/Answer/Citation`
- Produces: `SYSTEM_PROMPT: str`;`render_context(pack: ContextPack) -> str`;
  `parse_response(raw: str) -> dict | None`;
  `answer_question(driver, question, pack) -> Answer`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_answering.py
import json
from pkbot.answering import answer_question, parse_response, render_context
from pkbot.drivers import MockDriver
from pkbot.models import ContextPack, LoadedDoc, Section

PACK = ContextPack(
    docs=(LoadedDoc("public/规范.md", "不锈钢紧固件采购规范",
                    (Section("第 4 节", "螺栓须符合 GB/T 5783。"),), False),),
    skipped_oversized=(),
)

def _reply(**kw):
    return json.dumps(kw, ensure_ascii=False)

def test_valid_answer_with_good_citation_passes():
    driver = MockDriver([_reply(status="answered", answer="须符合 GB/T 5783。",
                                citations=[{"doc_id": "public/规范.md", "locator": "第 4 节"}])])
    ans = answer_question(driver, "螺栓规格要求是什么", PACK)
    assert ans.status == "answered"
    assert ans.citations[0].doc_id == "public/规范.md"

def test_fabricated_citation_is_downgraded_to_no_answer():
    """闸门核心:引用了没装载的文档,答案再漂亮也作废。"""
    driver = MockDriver([_reply(status="answered", answer="须符合 ISO 9001。",
                                citations=[{"doc_id": "public/根本不存在.md", "locator": "第 1 节"}])])
    ans = answer_question(driver, "螺栓规格要求是什么", PACK)
    assert ans.status == "no_answer"
    assert any("引用" in n for n in ans.notes)

def test_answer_without_citation_is_downgraded():
    driver = MockDriver([_reply(status="answered", answer="我觉得是这样。", citations=[])])
    assert answer_question(driver, "问题", PACK).status == "no_answer"

def test_malformed_json_is_downgraded_not_leaked():
    driver = MockDriver(["这不是 JSON,是模型随口说的一段话"])
    ans = answer_question(driver, "问题", PACK)
    assert ans.status == "no_answer"
    assert "这不是 JSON" not in ans.text

def test_model_says_no_answer_is_respected():
    driver = MockDriver([_reply(status="no_answer", answer="", citations=[])])
    assert answer_question(driver, "问题", PACK).status == "no_answer"

def test_empty_pack_short_circuits_without_calling_model():
    driver = MockDriver([])
    ans = answer_question(driver, "问题", ContextPack((), ()))
    assert ans.status == "no_answer"
    assert driver.calls == []

def test_partial_and_skipped_documents_are_disclosed():
    pack = ContextPack(
        docs=(LoadedDoc("a.md", "招标文件", (Section("第 9 章", "紧固件规格"),), True),),
        skipped_oversized=("超大报价表",),
    )
    driver = MockDriver([_reply(status="answered", answer="见第 9 章。",
                                citations=[{"doc_id": "a.md", "locator": "第 9 章"}])])
    ans = answer_question(driver, "紧固件规格", pack)
    assert any("招标文件" in n and "部分" in n for n in ans.notes)
    assert any("超大报价表" in n for n in ans.notes)

def test_parse_response_strips_code_fence():
    assert parse_response('```json\n{"status": "no_answer"}\n```') == {"status": "no_answer"}

def test_render_context_labels_documents_with_doc_id():
    text = render_context(PACK)
    assert "public/规范.md" in text and "第 4 节" in text
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_answering.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pkbot.answering'`

- [ ] **Step 3: 写最小实现**

```python
# src/pkbot/answering.py
"""问答内核。模型只负责组织语言并报出引用;是否可信由系统侧的引用校验闸门决定。"""
from __future__ import annotations

import json

from .drivers import LLMDriver
from .models import Answer, Citation, ContextPack

SYSTEM_PROMPT = """你是某公司采购部的知识助手,只能依据下面提供的资料回答问题。

铁律:
1. 只能使用【资料】中出现的内容。资料里没有的,一律回答 no_answer,绝不依靠常识或推测补充。
2. 每条回答必须给出引用,引用的 doc_id 必须逐字来自【资料】中标注的 doc_id。
3. 不确定、资料只是沾边、需要跨文档推断才能得出结论时,一律 no_answer。
4. 用简体中文回答,面向没有技术背景的采购员,直接给结论。

只输出一个 JSON 对象,不要有任何其他文字:
{"status": "answered" 或 "no_answer",
 "answer": "回答正文(no_answer 时为空字符串)",
 "citations": [{"doc_id": "资料里的 doc_id", "locator": "资料里的出处标记"}]}
"""

_FAILURE_TEXT = "这个问题我答不上来,已经记录下来,会有人跟进。"


def render_context(pack: ContextPack) -> str:
    blocks: list[str] = []
    for doc in pack.docs:
        parts = [f"<资料 doc_id=\"{doc.doc_id}\" 标题=\"{doc.title}\">"]
        if doc.partial:
            parts.append("(注意:本文档过大,以下仅为与问题相关的部分章节)")
        for sec in doc.sections:
            parts.append(f"[出处:{sec.locator}]\n{sec.text}")
        parts.append("</资料>")
        blocks.append("\n".join(parts))
    return "\n\n".join(blocks)


def parse_response(raw: str) -> dict | None:
    text = raw.strip()
    if text.startswith("```"):
        lines = [ln for ln in text.splitlines() if not ln.strip().startswith("```")]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _disclosures(pack: ContextPack) -> list[str]:
    notes: list[str] = []
    for doc in pack.docs:
        if doc.partial:
            notes.append(f"提示:《{doc.title}》太大,我只读了与问题相关的部分章节。")
    for title in pack.skipped_oversized:
        notes.append(f"提示:《{title}》太大,这次没能读进来。")
    return notes


def _failed(reason: str, pack: ContextPack) -> Answer:
    return Answer("no_answer", _FAILURE_TEXT, (), tuple([reason, *_disclosures(pack)]))


def answer_question(driver: LLMDriver, question: str, pack: ContextPack) -> Answer:
    if not pack.docs:
        return Answer("no_answer", _FAILURE_TEXT, (),
                      ("库里没有找到与这个问题相关的资料。", *_disclosures(pack)))

    user = f"【资料】\n{render_context(pack)}\n\n【问题】\n{question}"
    raw = driver.complete(SYSTEM_PROMPT, user)

    parsed = parse_response(raw)
    if parsed is None:
        return _failed("模型返回的格式不合法,为避免误导已作废。", pack)
    if parsed.get("status") != "answered":
        return _failed("模型判断资料不足以回答。", pack)

    text = (parsed.get("answer") or "").strip()
    raw_citations = parsed.get("citations") or []
    if not text or not isinstance(raw_citations, list) or not raw_citations:
        return _failed("答案缺少正文或出处,已作废。", pack)

    citations: list[Citation] = []
    for item in raw_citations:
        if not isinstance(item, dict):
            return _failed("引用格式不合法,已作废。", pack)
        doc_id = str(item.get("doc_id", ""))
        if doc_id not in pack.doc_ids:
            # 引用校验闸门:引用了本次没装载的文档,视为编造。
            return _failed(f"答案引用了本次未读取的文档({doc_id}),疑似编造,已作废。", pack)
        citations.append(Citation(doc_id, str(item.get("locator", "")).strip() or "未标注"))

    return Answer("answered", text, tuple(citations), tuple(_disclosures(pack)))
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_answering.py -v`
Expected: PASS(9 passed)

- [ ] **Step 5: 提交**

```bash
git add src/pkbot/answering.py tests/test_answering.py
git commit -m "feat: answering core with citation validation gate against fabrication"
```

---

### Task 9: 未答清单、周报与回填

**Files:**
- Create: `src/pkbot/gaps.py`
- Test: `tests/test_gaps.py`

**Interfaces:**
- Consumes: `models.User`
- Produces: `record_question(state_dir, user, question, status, category_hint=None, now=None) -> str`(返回 gap_id);
  `load_entries(state_dir) -> list[dict]`;
  `weekly_report(state_dir, days=7, now=None) -> Report`,其中
  `Report(total: int, unanswered: list[dict], resolved: int)`;
  `resolve_gap(state_dir, library_root, gap_id, answer_text, author, confidential=False, category=None) -> Path`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_gaps.py
from datetime import datetime, timedelta, timezone
import pytest
from pkbot.gaps import record_question, weekly_report, resolve_gap, load_entries
from pkbot.models import ROLE_BUYER, ROLE_CATEGORY_MANAGER, User

BUYER = User("G0042", "李四", ROLE_BUYER, ())
MANAGER = User("G0007", "王五", ROLE_CATEGORY_MANAGER, ("紧固件",))
NOW = datetime(2026, 7, 31, 10, 0, tzinfo=timezone.utc)

def test_report_counts_total_and_unanswered(tmp_path):
    record_question(tmp_path, BUYER, "问题一", "answered", now=NOW)
    record_question(tmp_path, BUYER, "问题二", "no_answer", now=NOW)
    record_question(tmp_path, BUYER, "问题三", "denied", now=NOW)
    rep = weekly_report(tmp_path, now=NOW)
    assert rep.total == 3
    assert [e["question"] for e in rep.unanswered] == ["问题二", "问题三"]

def test_report_window_excludes_old_entries(tmp_path):
    record_question(tmp_path, BUYER, "上个月的", "no_answer", now=NOW - timedelta(days=40))
    record_question(tmp_path, BUYER, "本周的", "no_answer", now=NOW)
    rep = weekly_report(tmp_path, days=7, now=NOW)
    assert rep.total == 1 and rep.unanswered[0]["question"] == "本周的"

def test_resolve_writes_public_faq_document_and_marks_resolved(tmp_path):
    state, lib = tmp_path / "state", tmp_path / "library"
    gap_id = record_question(state, BUYER, "紧固件走什么流程", "no_answer", now=NOW)
    path = resolve_gap(state, lib, gap_id, "走三级审批。", author=MANAGER)
    assert path.is_relative_to(lib / "public" / "faq")
    body = path.read_text(encoding="utf-8")
    assert "紧固件走什么流程" in body and "走三级审批" in body and "王五" in body
    entry = next(e for e in load_entries(state) if e["id"] == gap_id)
    assert entry["resolved"] is True
    assert weekly_report(state, now=NOW).resolved == 1

def test_resolve_can_mark_confidential(tmp_path):
    state, lib = tmp_path / "state", tmp_path / "library"
    gap_id = record_question(state, BUYER, "去年谈到多少钱", "denied", now=NOW)
    path = resolve_gap(state, lib, gap_id, "单价 12 元。", author=MANAGER,
                       confidential=True, category="紧固件")
    assert path.is_relative_to(lib / "confidential" / "紧固件" / "faq")

def test_confidential_resolution_requires_category(tmp_path):
    state, lib = tmp_path / "state", tmp_path / "library"
    gap_id = record_question(state, BUYER, "q", "no_answer", now=NOW)
    with pytest.raises(ValueError):
        resolve_gap(state, lib, gap_id, "a", author=MANAGER, confidential=True)

def test_resolving_unknown_gap_raises(tmp_path):
    with pytest.raises(KeyError):
        resolve_gap(tmp_path / "state", tmp_path / "lib", "nope", "a", author=MANAGER)
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_gaps.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pkbot.gaps'`

- [ ] **Step 3: 写最小实现**

```python
# src/pkbot/gaps.py
"""知识缺口台账:记录每次提问、出周报、把人工补答回填成新文档进库。"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import User

LOG_FILENAME = "questions.jsonl"
UNANSWERED_STATUSES = {"no_answer", "denied"}


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
    entries = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            entries.append(json.loads(line))
    return entries


def _rewrite(state_dir: Path, entries: list[dict]) -> None:
    with _log_path(state_dir).open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")


def weekly_report(state_dir: Path, days: int = 7, now: datetime | None = None) -> Report:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=days)
    entries = [e for e in load_entries(state_dir) if datetime.fromisoformat(e["ts"]) >= cutoff]
    unanswered = [e for e in entries if e["status"] in UNANSWERED_STATUSES and not e["resolved"]]
    resolved = sum(1 for e in entries if e["resolved"])
    return Report(len(entries), unanswered, resolved)


def _slug(text: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\s]+", "-", text).strip("-")
    return cleaned[:30] or "问题"


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
    """人工补答 → 生成新文档进库,并把台账条目标记为已解决。"""
    if confidential and not category:
        raise ValueError("标记为保密的补答必须指定品类,否则没人能看到它。")
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
        f"来源:采购员 {target['name']} 的提问(编号 {gap_id})。\n",
        encoding="utf-8",
    )

    target["resolved"] = True
    target["resolved_by"] = author.employee_id
    target["resolved_doc"] = str(path)
    _rewrite(state_dir, entries)
    return path
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest tests/test_gaps.py -v`
Expected: PASS(6 passed)

- [ ] **Step 5: 提交**

```bash
git add src/pkbot/gaps.py tests/test_gaps.py
git commit -m "feat: knowledge-gap ledger, weekly report, and answer backfill"
```

---

### Task 10: CLI 组装、演示库、README、端到端测试

**Files:**
- Create: `src/pkbot/cli.py`, `README.md`, `demo/library/**`, `tests/test_cli_e2e.py`
- Test: `tests/test_cli_e2e.py`

**Interfaces:**
- Consumes: 前九个任务的全部公开接口
- Produces: `main(argv: list[str] | None = None) -> int`;
  `ask(library_root, state_dir, employee_id, question, driver) -> Answer`(供端到端测试直接调用)

- [ ] **Step 1: 写失败测试**

```python
# tests/test_cli_e2e.py
import json
from pathlib import Path
import pytest
from pkbot.cli import ask, main
from pkbot.drivers import MockDriver
from pkbot.gaps import weekly_report

ROSTER = ("工号,姓名,角色,负责品类\n"
          "G0042,李四,采购员,\n"
          "G0007,王五,品类经理,紧固件\n"
          "G0001,赵六,管理员,\n")

@pytest.fixture
def workspace(tmp_path):
    lib = tmp_path / "library"
    (lib / "public").mkdir(parents=True)
    (lib / "confidential" / "紧固件").mkdir(parents=True)
    (lib / "public" / "紧固件采购规范.md").write_text(
        "# 规格要求\n螺栓须符合 GB/T 5783。\n", encoding="utf-8")
    (lib / "confidential" / "紧固件" / "2025谈判纪要.md").write_text(
        "# 谈判结果\n供应商甲报价每件 12 元。\n", encoding="utf-8")
    (lib / "public" / "扫描件.wps").write_bytes(b"\x00")
    (lib / "roster.csv").write_text(ROSTER, encoding="utf-8")
    return tmp_path

def _ok(answer, doc_id, locator):
    return json.dumps({"status": "answered", "answer": answer,
                       "citations": [{"doc_id": doc_id, "locator": locator}]},
                      ensure_ascii=False)

def test_buyer_gets_public_answer_with_citation(workspace):
    driver = MockDriver([_ok("须符合 GB/T 5783。", "public/紧固件采购规范.md", "规格要求")])
    ans = ask(workspace / "library", workspace / "state", "G0042", "螺栓规格要求是什么", driver)
    assert ans.status == "answered" and ans.citations[0].locator == "规格要求"

def test_buyer_asking_confidential_is_denied_and_told_who_to_find(workspace):
    driver = MockDriver([json.dumps({"status": "no_answer", "answer": "", "citations": []})])
    ans = ask(workspace / "library", workspace / "state", "G0042", "供应商甲报价多少", driver)
    assert ans.status == "denied"
    assert "保密" in ans.text and "王五" in ans.text
    assert "12 元" not in ans.text     # 绝不泄露正文

def test_manager_can_see_own_category_confidential(workspace):
    driver = MockDriver([_ok("每件 12 元。", "confidential/紧固件/2025谈判纪要.md", "谈判结果")])
    ans = ask(workspace / "library", workspace / "state", "G0007", "供应商甲报价多少", driver)
    assert ans.status == "answered" and "12" in ans.text

def test_denied_and_unanswered_land_in_gap_ledger(workspace):
    driver = MockDriver([json.dumps({"status": "no_answer", "answer": "", "citations": []})])
    ask(workspace / "library", workspace / "state", "G0042", "供应商甲报价多少", driver)
    rep = weekly_report(workspace / "state")
    assert rep.total == 1 and len(rep.unanswered) == 1

def test_unknown_employee_is_refused(workspace):
    driver = MockDriver([])
    with pytest.raises(SystemExit):
        main(["ask", "问题", "--user", "G9999", "--library", str(workspace / "library"),
              "--state", str(workspace / "state")])

def test_library_status_lists_unreadable_files(workspace, capsys):
    code = main(["library", "status", "--user", "G0001",
                 "--library", str(workspace / "library"),
                 "--state", str(workspace / "state")])
    out = capsys.readouterr().out
    assert code == 0 and "扫描件.wps" in out and "不支持的格式" in out

def test_gaps_answer_creates_document_that_becomes_answerable(workspace):
    driver = MockDriver([json.dumps({"status": "no_answer", "answer": "", "citations": []})])
    ask(workspace / "library", workspace / "state", "G0042", "紧固件退货怎么走", driver)
    gap_id = weekly_report(workspace / "state").unanswered[0]["id"]
    code = main(["gaps", "answer", gap_id, "--text", "填退货单后走两级审批。",
                 "--user", "G0007", "--library", str(workspace / "library"),
                 "--state", str(workspace / "state")])
    assert code == 0
    faq = list((workspace / "library" / "public" / "faq").glob("*.md"))
    assert len(faq) == 1 and "两级审批" in faq[0].read_text(encoding="utf-8")

    driver2 = MockDriver([_ok("填退货单后走两级审批。",
                              f"public/faq/{faq[0].name}", "紧固件退货怎么走")])
    ans = ask(workspace / "library", workspace / "state", "G0042", "紧固件退货怎么走", driver2)
    assert ans.status == "answered"
```

- [ ] **Step 2: 运行确认失败**

Run: `uv run pytest tests/test_cli_e2e.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pkbot.cli'`

- [ ] **Step 3: 写最小实现**

```python
# src/pkbot/cli.py
"""命令行入口。对话入口与问答内核分层,以后接企业微信只需换掉这一层。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .access import owners_for_category, partition
from .answering import answer_question
from .drivers import LLMDriver, ScriptedDriver
from .gaps import resolve_gap, weekly_report
from .gaps import record_question
from .identity import RosterError, UnknownUserError, get_user, load_roster
from .library import ROSTER_FILENAME, scan_library
from .models import Answer, User
from .retrieval import build_context, rank

DEFAULT_LIBRARY = Path("demo/library")
DEFAULT_STATE = Path("demo/state")

_DEMO_DRIVER = ScriptedDriver(
    rules=[],
    default='{"status": "no_answer", "answer": "", "citations": []}',
)


def _load_user(library_root: Path, employee_id: str) -> tuple[User, dict[str, User]]:
    roster = load_roster(library_root / ROSTER_FILENAME)
    return get_user(roster, employee_id), roster


def ask(
    library_root: Path,
    state_dir: Path,
    employee_id: str,
    question: str,
    driver: LLMDriver,
) -> Answer:
    user, roster = _load_user(library_root, employee_id)
    library = scan_library(library_root)
    visibility = partition(user, library)

    pack = build_context(question, list(visibility.visible))
    answer = answer_question(driver, question, pack)

    category_hint = None
    if answer.status != "answered":
        hidden_hits = rank(question, list(visibility.hidden))
        if hidden_hits:
            top_doc = hidden_hits[0][0]
            category_hint = top_doc.category
            owners = owners_for_category(roster, category_hint)
            who = "、".join(owners) if owners else "对应的品类经理"
            answer = Answer(
                status="denied",
                text=(f"这个问题涉及保密资料,你的权限看不到。已经记录下来,"
                      f"会转给{who}跟进。"),
                citations=(),
                notes=answer.notes,
            )

    record_question(state_dir, user, question, answer.status, category_hint)
    return answer


def _print_answer(answer: Answer) -> None:
    print(answer.text)
    if answer.citations:
        print("\n依据:")
        for c in answer.citations:
            print(f"  - {c.doc_id} · {c.locator}")
    for note in answer.notes:
        print(f"\n{note}")


def _cmd_ask(args: argparse.Namespace) -> int:
    driver: LLMDriver
    if args.driver == "anthropic":
        from .anthropic_driver import AnthropicDriver

        driver = AnthropicDriver()
    else:
        driver = _DEMO_DRIVER
    _print_answer(ask(args.library, args.state, args.user, args.question, driver))
    return 0


def _cmd_whoami(args: argparse.Namespace) -> int:
    user, _ = _load_user(args.library, args.user)
    cats = "、".join(user.categories) if user.categories else "(无)"
    print(f"{user.name}({user.employee_id})· 角色:{user.role} · 负责品类:{cats}")
    return 0


def _cmd_library_status(args: argparse.Namespace) -> int:
    user, _ = _load_user(args.library, args.user)
    library = scan_library(args.library)
    visibility = partition(user, library)
    print(f"库里共有 {len(library.documents)} 份可读文档,你能看到 {len(visibility.visible)} 份。")
    if library.unreadable:
        print(f"\n有 {len(library.unreadable)} 份文件读不了(内容没进库):")
        for item in library.unreadable:
            print(f"  - {item.path.name}:{item.reason}")
    else:
        print("\n所有文件都能正常读取。")
    return 0


def _cmd_gaps_report(args: argparse.Namespace) -> int:
    rep = weekly_report(args.state, days=args.days)
    print(f"最近 {args.days} 天:共提问 {rep.total} 次,"
          f"其中 {len(rep.unanswered)} 个没答上来,已补答 {rep.resolved} 个。")
    for entry in rep.unanswered:
        print(f"  [{entry['id']}] {entry['name']}:{entry['question']}")
    if not rep.unanswered:
        print("  (没有待处理的问题)")
    return 0


def _cmd_gaps_answer(args: argparse.Namespace) -> int:
    user, _ = _load_user(args.library, args.user)
    path = resolve_gap(args.state, args.library, args.gap_id, args.text, author=user,
                       confidential=args.confidential, category=args.category)
    print(f"已补答并入库:{path}")
    return 0


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--user", required=True, help="你的工号")
    parser.add_argument("--library", type=Path, default=DEFAULT_LIBRARY, help="文档库目录")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE, help="台账目录")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pkbot", description="采购品类知识问答机器人")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ask = sub.add_parser("ask", help="提一个问题")
    p_ask.add_argument("question")
    p_ask.add_argument("--driver", choices=["demo", "anthropic"], default="demo",
                       help="demo=离线演示驱动(默认);anthropic=真实模型")
    _add_common(p_ask)
    p_ask.set_defaults(func=_cmd_ask)

    p_who = sub.add_parser("whoami", help="看看机器人认为你是谁")
    _add_common(p_who)
    p_who.set_defaults(func=_cmd_whoami)

    p_lib = sub.add_parser("library", help="文档库相关")
    lib_sub = p_lib.add_subparsers(dest="subcommand", required=True)
    p_status = lib_sub.add_parser("status", help="库里有什么、哪些读不了")
    _add_common(p_status)
    p_status.set_defaults(func=_cmd_library_status)

    p_gaps = sub.add_parser("gaps", help="知识缺口台账")
    gaps_sub = p_gaps.add_subparsers(dest="subcommand", required=True)

    p_rep = gaps_sub.add_parser("report", help="出周报")
    p_rep.add_argument("--days", type=int, default=7)
    p_rep.add_argument("--state", type=Path, default=DEFAULT_STATE)
    p_rep.set_defaults(func=_cmd_gaps_report)

    p_ans = gaps_sub.add_parser("answer", help="人工补答并回填成新文档")
    p_ans.add_argument("gap_id")
    p_ans.add_argument("--text", required=True, help="补充的答案正文")
    p_ans.add_argument("--confidential", action="store_true", help="标记这条按保密算")
    p_ans.add_argument("--category", help="保密时必须指明品类")
    _add_common(p_ans)
    p_ans.set_defaults(func=_cmd_gaps_answer)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (UnknownUserError, RosterError, ValueError, KeyError) as exc:
        print(f"错误:{exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行确认通过**

Run: `uv run pytest -v`
Expected: PASS(全部测试通过,共 40+ 项)

- [ ] **Step 5: 建演示库与 README**

在 `demo/library/` 下放:`roster.csv`(三个人:采购员 G0042 李四、品类经理 G0007 王五、管理员 G0001 赵六);
`public/紧固件采购规范.md`、`public/采购流程制度.md`;`registry/品类负责人对照表.csv`;
`confidential/紧固件/2025年度谈判纪要.md`;`confidential/电子元器件/供应商报价汇总.md`;
以及一份 `public/合同扫描件.wps`(内容为二进制,用来演示"读不了要明说")。

`README.md` 必须包含:一句话说明、文件夹含义表、`roster.csv` 填写说明、
安装与运行(`uv sync --dev` / `uv run pytest` / `uv run pkbot ...`)、演示路径六条命令、
"怎么接真实模型"(`uv sync --extra llm` + `ANTHROPIC_API_KEY` + `--driver anthropic`)、
以及"设计上为什么不用向量库"的一段。

- [ ] **Step 6: 全量测试与提交**

```bash
uv run pytest -v
git add -A
git commit -m "feat: CLI, demo library, README, and end-to-end tests"
```

---

## Self-Review

**1. Spec coverage**

| spec 要求 | 对应任务 |
|---|---|
| 密级按文件夹整份判定 | Task 4 `classify_path` |
| 名单文件身份 + 未知工号拒绝服务 | Task 2 |
| 品类经理按品类隔离 / 未分类仅管理员 | Task 5 |
| 大文件按小节装载、读不动如实说 | Task 6 + Task 8 `_disclosures` |
| 读不了的格式明确列出 | Task 3 + Task 10 `library status` |
| 引用校验闸门防瞎编 | Task 8 |
| 越权提示可见 + 指出找谁 | Task 10 `ask()` 的 denied 分支 |
| 未答清单 + 周报 | Task 9 |
| 人工补答回填新文档(默认公开、可标保密) | Task 9 `resolve_gap` |
| 回答带出处 | Task 8 + Task 10 `_print_answer` |
| 企业微信留口子 | Task 10 CLI 与内核分层 |

**2. Placeholder scan** — 无 TBD / TODO;每个代码步骤都给了完整可运行代码;Task 10 Step 5 的演示库内容
以清单形式明确列出文件名与角色,不是"添加一些示例文档"。

**3. Type consistency** — `Section(locator, text)`、`Document.doc_id`、`ContextPack.doc_ids`、
`Answer(status, text, citations, notes)`、`partition()->Visibility(visible, hidden)`、
`build_context(question, docs, budget)`、`record_question(...)->str`、`resolve_gap(...)->Path`
在定义处与所有调用处一致。`LLMDriver.complete(system, user)` 签名在 Mock/Scripted/Anthropic 三处一致。

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-31-procurement-knowledge-bot.md`.
本轮按外部适配要求采用 **Inline Execution(superpowers:executing-plans)**,
requesting-code-review 阶段由我串行扮演审查者角色,并在 REFLECTION.md 注明。
