"""从文档正文里抽取生效日期与版本号(research.md D-07)。

**刻意不做的事:不用文件 mtime 兜底。**
共享盘上一次复制粘贴就能把 2019 年的老文件变成"最新",然后 FR-005a 会用它去
压制真正的新版本。宁可退化成"并列展示、请自行核实",也不能错误裁决。
"""

from __future__ import annotations

import re
from datetime import date

from ..models import DateConfidence

_DATE_LABEL = r"(?:生效日期|发布日期|实施日期|Effective\s*Date|Version\s*Date|Issued)"
_DATE_PATTERNS = [
    re.compile(_DATE_LABEL + r"\s*[::]?\s*(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})", re.I),
]
_VERSION_PATTERNS = [
    re.compile(r"(?:版本|版本号|Version|Rev\.?)\s*[::]?\s*[Vv]?(\d+(?:\.\d+)*)", re.I),
]
_FILENAME_YEAR = re.compile(r"(19|20)\d{2}")

# 只看正文开头这么多字符 —— 生效日期总在抬头,不在正文深处
_HEAD_CHARS = 600


def extract_version_info(
    text: str, filename: str = ""
) -> tuple[date | None, str | None, DateConfidence]:
    head = text[:_HEAD_CHARS]

    version: str | None = None
    for pat in _VERSION_PATTERNS:
        m = pat.search(head)
        if m:
            version = m.group(1)
            break

    for pat in _DATE_PATTERNS:
        m = pat.search(head)
        if m:
            try:
                d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                continue
            return d, version, DateConfidence.BODY

    # 正文抽不到才回退到文件名里的年份,并降低置信度
    m = _FILENAME_YEAR.search(filename)
    if m:
        return date(int(m.group(0)), 1, 1), version, DateConfidence.FILENAME

    return None, version, DateConfidence.NONE
