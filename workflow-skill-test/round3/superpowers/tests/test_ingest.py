import pytest

from pkbot.ingest import UnreadableError, parse_sections


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


def test_large_sheet_is_split_into_row_ranges(tmp_path):
    from openpyxl import Workbook

    p = tmp_path / "报价.xlsx"
    wb = Workbook()
    ws = wb.active
    ws.title = "报价"
    for i in range(450):
        ws.append([f"料号{i}", i])
    wb.save(p)
    sections = parse_sections(p)
    assert len(sections) == 3
    assert sections[0].locator == "工作表 报价 第 1-200 行"
    assert sections[2].locator == "工作表 报价 第 401-450 行"
