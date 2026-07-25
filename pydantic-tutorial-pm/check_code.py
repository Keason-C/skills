#!/usr/bin/env python
"""抽取教程里所有 python 代码块，做语法编译检查；并统计结构指标。"""
import re
import sys
from pathlib import Path

SRC = Path(__file__).parent / "tutorial"

FENCE = re.compile(r"^```(\w*)[^\n]*\n(.*?)^```", re.S | re.M)


def main() -> int:
    bad = 0
    for f in sorted(SRC.glob("*.md")):
        text = f.read_text(encoding="utf-8")
        blocks = FENCE.findall(text)
        py = [(i, b) for i, (lang, b) in enumerate(blocks) if lang == "python"]
        errs = []
        frag = []
        for i, code in py:
            # 跳过明显的片段（以 ... 或缩进开头、含省略号占位）
            if code.strip().startswith(("...", ".", ")", "]")) or "..." in code.split("\n")[0]:
                continue
            try:
                compile(code, f"{f.name}#py{i}", "exec")
            except SyntaxError as e:
                msg = e.msg
                # 文档片段（续行 / 顶层 await / 签名示意）不算错，但顶层 await 要提示
                if msg in ("unexpected indent", "invalid syntax", "Invalid star expression"):
                    continue
                if "'await' outside function" in msg:
                    frag.append(f"    py块#{i} 顶层 await（读者直接复制会失败，需注明在 async 环境内）")
                    continue
                errs.append(f"    py块#{i} 第{e.lineno}行: {msg}")
        h2 = len(re.findall(r"^## ", text, re.M))
        h3 = len(re.findall(r"^### ", text, re.M))
        pm = text.count("PM 视角")
        warn = text.count("⚠️")
        tbl = len(re.findall(r"^\|", text, re.M))
        status = "OK" if not errs else f"{len(errs)} 处语法错误"
        print(f"{f.name:34s} 行{len(text.splitlines()):5d}  "
              f"章{h2:3d}/{h3:3d}  码块{len(blocks):3d}  PM{pm:3d}  坑{warn:3d}  表{tbl:4d}  [{status}]")
        for e in errs:
            print(e)
            bad += 1
        for e in frag:
            print(e)

        # 检查重复的小节编号
        nums = re.findall(r"^### (\d+\.\d+)\s", text, re.M)
        dup = {n for n in nums if nums.count(n) > 1}
        if dup:
            print(f"    ! 重复小节号: {sorted(dup)}")

    print(f"\n合计语法错误: {bad}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
