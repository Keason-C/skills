"""五种格式的解析器(FR-017 / US4)。"""

from __future__ import annotations

from pathlib import Path

import pytest

from procurement_bot.errors import ParseError, UnsupportedFormatError
from procurement_bot.ingest.parsers import parse


def test_markdown_headings_become_locators(tmp_path: Path):
    p = tmp_path / "a.md"
    p.write_text("# 手册\n\n## 品类归属\n\n负责人张伟\n", encoding="utf-8")
    sections = parse(p)
    assert sections[0].heading_path == ("手册", "品类归属")
    assert "§ 手册 / 品类归属" == sections[0].locator


def test_markdown_sibling_headings_do_not_nest(tmp_path: Path):
    p = tmp_path / "a.md"
    p.write_text("## 甲\n\n内容甲\n\n## 乙\n\n内容乙\n", encoding="utf-8")
    paths = [s.heading_path for s in parse(p)]
    assert paths == [("甲",), ("乙",)]


def test_txt_is_one_section(tmp_path: Path):
    p = tmp_path / "a.txt"
    p.write_text("第一行\n第二行", encoding="utf-8")
    sections = parse(p)
    assert len(sections) == 1 and sections[0].locator == "正文"


def test_docx_headings_and_tables(tmp_path: Path):
    docx = pytest.importorskip("docx")
    p = tmp_path / "a.docx"
    d = docx.Document()
    d.add_heading("流程说明", level=1)
    d.add_heading("审批", level=2)
    d.add_paragraph("审批共三级。")
    table = d.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "供应商"
    table.cell(0, 1).text = "编码"
    table.cell(1, 0).text = "江铜国贸"
    table.cell(1, 1).text = "SUP-0101"
    d.save(str(p))

    sections = parse(p)
    assert any(s.heading_path == ("流程说明", "审批") for s in sections)
    assert any("SUP-0101" in s.text and s.locator.startswith("表格") for s in sections)


def test_xlsx_locator_names_the_worksheet(tmp_path: Path):
    openpyxl = pytest.importorskip("openpyxl")
    p = tmp_path / "a.xlsx"
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    ws = wb.create_sheet("合格供应商")
    ws.append(["供应商名称", "编码"])
    ws.append(["江铜国贸", "SUP-0101"])
    ws2 = wb.create_sheet("备选供应商")
    ws2.append(["供应商名称"])
    ws2.append(["中原有色"])
    wb.save(str(p))

    sections = parse(p)
    locators = {s.locator for s in sections}
    assert locators == {"工作表:合格供应商", "工作表:备选供应商"}
    body = next(s.text for s in sections if "合格" in s.locator)
    assert "供应商名称: 江铜国贸" in body


def test_pdf_locator_is_page_number(tmp_path: Path):
    pytest.importorskip("pypdf")
    from pdf_helper import make_pdf  # noqa: PLC0415

    p = tmp_path / "a.pdf"
    p.write_bytes(make_pdf(["Category Ownership Matrix", "Fasteners - Wang Fang"]))
    sections = parse(p)
    assert sections[0].locator == "第 1 页"
    assert "Fasteners" in sections[0].text


def test_scanned_pdf_without_text_is_rejected(tmp_path: Path):
    pytest.importorskip("pypdf")
    from pdf_helper import make_pdf  # noqa: PLC0415

    p = tmp_path / "empty.pdf"
    p.write_bytes(make_pdf([]))
    with pytest.raises(ParseError):
        parse(p)


def test_corrupt_pdf_raises_parse_error(tmp_path: Path):
    p = tmp_path / "bad.pdf"
    p.write_bytes(b"%PDF-1.4 not really a pdf")
    with pytest.raises(ParseError):
        parse(p)


def test_unknown_extension_raises(tmp_path: Path):
    p = tmp_path / "a.bin"
    p.write_bytes(b"\x00\x01")
    with pytest.raises(UnsupportedFormatError):
        parse(p)
