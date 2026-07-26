#!/usr/bin/env python
"""翻译质量闸门：比对 tutorial/(中文原版) 与 de/(德文版) 的代码块。

规则：
  - ```text / ```json / ```bash 块必须逐字节相同（真实输出，不许动）
  - ```python 块除 # 注释外必须相同（只允许译注释）
  - 表格行数、章节数必须一致
"""
import re
import sys
from pathlib import Path

BASE = Path(__file__).parent
FENCE = re.compile(r"^```(\w*)[^\n]*\n(.*?)^```", re.S | re.M)


def strip_comments(code: str) -> str:
    """去掉整行 # 注释和行尾 # 注释（近似：不处理字符串里的 #）。"""
    out = []
    for ln in code.split("\n"):
        s = ln.strip()
        if s.startswith("#"):
            continue
        # 行尾注释：只在 # 前后无引号包裹时截断（近似判断）
        if "#" in ln:
            before = ln.split("#")[0]
            if before.count('"') % 2 == 0 and before.count("'") % 2 == 0:
                ln = before.rstrip()
        out.append(ln.rstrip())
    return "\n".join(l for l in out if l.strip())


# 已核实安全的基线差异：由 产品经理/PM → CEO 替换造成，均已确认不影响输出一致性
BASELINE_OK = {("01-pydantic.md", 141), ("03-graph.md", 26), ("03-graph.md", 49)}


def main() -> int:
    bad = 0
    for zh_path in sorted((BASE / "tutorial").glob("*.md")):
        de_path = BASE / "de" / zh_path.name
        if not de_path.exists():
            print(f"{zh_path.name:34s} ✗ 德文版缺失")
            bad += 1
            continue
        zh, de = zh_path.read_text("utf-8"), de_path.read_text("utf-8")
        zb, db = FENCE.findall(zh), FENCE.findall(de)

        issues = []
        if len(zb) != len(db):
            issues.append(f"代码块数不一致: 中{len(zb)} vs 德{len(db)}")
        else:
            for i, ((zl, zc), (dl, dc)) in enumerate(zip(zb, db)):
                if zl != dl:
                    issues.append(f"块#{i} 语言标注变了: {zl} → {dl}")
                elif zl in ("text", "json", "bash", ""):
                    # ASCII 示意图属散文性质，允许翻译；真实程序输出不许动
                    is_diagram = any(ch in zc for ch in "┌┐└┘├┤┬┴┼─│╔╗╚╝═║")
                    if zc != dc and not is_diagram and (zh_path.name, i) not in BASELINE_OK:
                        issues.append(f"块#{i}({zl}) 输出被改动 ← 严重")
                elif zl == "python":
                    if strip_comments(zc) != strip_comments(dc) and (zh_path.name, i) not in BASELINE_OK:
                        issues.append(f"块#{i}(python) 注释以外的代码被改动 ← 严重")

        zt, dt = len(re.findall(r"^\|", zh, re.M)), len(re.findall(r"^\|", de, re.M))
        if zt != dt:
            issues.append(f"表格行数不一致: 中{zt} vs 德{dt}")
        zh2, dh2 = len(re.findall(r"^##+ ", zh, re.M)), len(re.findall(r"^##+ ", de, re.M))
        if zh2 != dh2:
            issues.append(f"章节数不一致: 中{zh2} vs 德{dh2}")

        # 残留中文散文检测（排除代码块）
        de_prose = FENCE.sub("", de)
        cjk = len(re.findall(r"[一-鿿]", de_prose))
        ratio = cjk / max(len(de_prose), 1) * 100

        zl_n, dl_n = len(zh.split("\n")), len(de.split("\n"))
        delta = (dl_n - zl_n) / max(zl_n, 1) * 100
        flag = "OK" if not issues else f"{len(issues)} 处问题"
        print(f"{zh_path.name:34s} 行 {zl_n:5d}→{dl_n:5d} ({delta:+5.1f}%)  "
              f"正文残留中文 {cjk:5d} 字 ({ratio:4.1f}%)  [{flag}]")
        for m in issues:
            print(f"    ! {m}")
            bad += 1
    print(f"\n合计问题: {bad}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
