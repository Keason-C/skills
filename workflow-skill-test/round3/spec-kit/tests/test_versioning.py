"""生效日期 / 版本号抽取(FR-005a 的基础,research.md D-07)。"""

from __future__ import annotations

from datetime import date

from procurement_bot.ingest.versioning import extract_version_info
from procurement_bot.models import DateConfidence


def test_dash_date():
    d, _, conf = extract_version_info("生效日期:2024-03-01\n正文")
    assert (d, conf) == (date(2024, 3, 1), DateConfidence.BODY)


def test_slash_date():
    d, _, conf = extract_version_info("发布日期: 2023/7/9")
    assert (d, conf) == (date(2023, 7, 9), DateConfidence.BODY)


def test_chinese_date():
    d, _, conf = extract_version_info("生效日期:2022年11月5日")
    assert (d, conf) == (date(2022, 11, 5), DateConfidence.BODY)


def test_english_date_label():
    d, _, conf = extract_version_info("Effective Date: 2025-01-15")
    assert (d, conf) == (date(2025, 1, 15), DateConfidence.BODY)


def test_version_chinese():
    _, v, _ = extract_version_info("版本:V2.1\n生效日期:2024-01-01")
    assert v == "2.1"


def test_version_english():
    _, v, _ = extract_version_info("Version: v3.4")
    assert v == "3.4"


def test_nothing_found():
    d, v, conf = extract_version_info("这份文件什么日期都没写。", "普通文件.md")
    assert (d, v, conf) == (None, None, DateConfidence.NONE)


def test_filename_year_is_only_a_fallback():
    """正文有日期时,文件名里的年份不得覆盖它。"""
    d, _, conf = extract_version_info("生效日期:2024-03-01", "流程-2019旧版.md")
    assert (d.year, conf) == (2024, DateConfidence.BODY)


def test_filename_year_used_when_body_has_none():
    d, _, conf = extract_version_info("正文没有日期", "流程-2019旧版.md")
    assert (d.year, conf) == (2019, DateConfidence.FILENAME)


def test_mtime_is_never_used(tmp_path):
    """明确断言:我们不看文件修改时间(D-07 里论证过它很危险)。"""
    f = tmp_path / "无日期.md"
    f.write_text("正文没有任何日期", encoding="utf-8")
    d, _, conf = extract_version_info(f.read_text(encoding="utf-8"), f.name)
    assert d is None and conf is DateConfidence.NONE
