#!/usr/bin/env python
"""把 tutorial/ 下的 markdown 拼成一本带目录、页码、代码高亮的中文 PDF。"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from markdown_it import MarkdownIt
from pygments import highlight
from pygments.formatters import HtmlFormatter
from pygments.lexers import get_lexer_by_name, TextLexer
from playwright.sync_api import sync_playwright

BASE = Path(__file__).parent
SRC = BASE / "de"
OUT_HTML = BASE / "buch_de.html"
OUT_PDF = BASE / "Pydantic-Komplettkurs-CEO-Perspektive.pdf"
CHROME = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"

# (文件名, 部分标题, 副标题) —— None 表示不另起「部分」大标题
PARTS = [
    ("00-导读.md",                  None, None),
    ("01-pydantic.md",              "Teil I  Pydantic", "Datenvalidierung: das Fundament von allem"),
    ("02a-agent-tools.md",          "Teil II  Pydantic AI", "Das LLM in einen Vertrag einbinden"),
    ("02b-capabilities-harness.md", None, None),
    ("03-graph.md",                 "Teil III  Pydantic Graph", "Wenn ein einzelner Loop nicht mehr reicht"),
    ("04-shizhan.md",               "Teil IV  Praxis", "Alle drei zu einem echten System verbinden"),
    ("05-fulu.md",                  "Anhang", "Spickzettel · Fallstricke · Entscheidungsbäume"),
]


def slugify(text: str, seen: dict) -> str:
    s = re.sub(r"[^\w一-鿿]+", "-", text.strip()).strip("-").lower() or "sec"
    n = seen.get(s, 0)
    seen[s] = n + 1
    return s if n == 0 else f"{s}-{n}"


def render_code(code: str, lang: str) -> str:
    try:
        lexer = get_lexer_by_name(lang) if lang else TextLexer()
    except Exception:
        lexer = TextLexer()
    fmt = HtmlFormatter(nowrap=False, cssclass="hl")
    return highlight(code, lexer, fmt)


def build_md() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": True, "linkify": False})
    md.enable("table")
    md.enable("strikethrough")

    def fence(self, tokens, idx, options, env):
        tok = tokens[idx]
        lang = (tok.info or "").strip().split()[0] if tok.info else ""
        body = tok.content
        # ASCII 示意图：含制表符号 → 不折行、按内容宽度自动缩字号，避免被拆坏
        if any(ch in body for ch in "┌┐└┘├┤┬┴┼─│╔╗╚╝═║╠╣▼▲"):
            widest = max((sum(2 if ord(c) > 0x2E80 and c not in "─│┌┐└┘├┤┬┴┼" else 1
                              for c in ln) for ln in body.splitlines()), default=60)
            size = 8.4 if widest <= 78 else (7.4 if widest <= 92 else 6.5)
            return (f'<div class="codewrap diagram" style="--dsz:{size}pt">'
                    f"<pre><code>{html.escape(body)}</code></pre></div>")
        return f'<div class="codewrap">{render_code(body, lang)}</div>'

    md.add_render_rule("fence", fence)
    return md


def collect(md: MarkdownIt):
    """返回 (body_html, toc_entries)。toc_entries: [(level, title, anchor)]"""
    seen: dict = {}
    body: list[str] = []
    toc: list[tuple[int, str, str]] = []

    for fname, part_title, part_sub in PARTS:
        p = SRC / fname
        if not p.exists():
            print(f"  ! 缺失（跳过）: {fname}", file=sys.stderr)
            continue
        text = p.read_text(encoding="utf-8")

        if part_title:
            anc = slugify(part_title, seen)
            toc.append((0, part_title, anc))
            body.append(
                f'<section class="partdiv" id="{anc}">'
                f'<h1 class="partlabel">{html.escape(part_title, quote=False)}</h1>'
                f'<div class="partsub">{html.escape(part_sub or "", quote=False)}</div></section>'
            )

        rendered = md.render(text)

        # 给 h2/h3/h4 加锚点并收进目录
        def add_anchor(m):
            lvl = int(m.group(1))
            inner = m.group(2)
            title = html.unescape(re.sub(r"<[^>]+>", "", inner)).strip()
            anc = slugify(title, seen)
            if lvl <= 3:
                toc.append((lvl, title, anc))
            return f'<h{lvl} id="{anc}">{inner}</h{lvl}>'

        rendered = re.sub(r"<h([234])>(.*?)</h\1>", add_anchor, rendered, flags=re.S)

        # 按内容给引用块上色：⚠️坑=橙，💡/📌备注=紫，其余(PM视角)=蓝
        def style_bq(m):
            inner = m.group(1)
            if "⚠" in inner[:400] or "坑" in inner[:120]:
                return f'<blockquote class="warn">{inner}</blockquote>'
            if "💡" in inner[:400] or "📌" in inner[:400]:
                return f'<blockquote class="note">{inner}</blockquote>'
            return f"<blockquote>{inner}</blockquote>"

        rendered = re.sub(r"<blockquote>(.*?)</blockquote>", style_bq, rendered, flags=re.S)
        body.append(f'<section class="chunk">{rendered}</section>')

    return "\n".join(body), toc


def toc_html(toc) -> str:
    rows = []
    for lvl, title, anc in toc:
        cls = {0: "t0", 2: "t2", 3: "t3"}.get(lvl, "t3")
        rows.append(f'<div class="{cls}"><a href="#{anc}">{html.escape(title, quote=False)}</a></div>')
    return "\n".join(rows)


CSS = """
@page { size: A4; margin: 18mm 16mm 18mm 16mm; }
* { box-sizing: border-box; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body {
  font-family: "Noto Sans CJK SC", "Noto Sans CJK", sans-serif;
  font-size: 10.2pt; line-height: 1.75; color: #1c1e21; margin: 0;
  word-wrap: break-word;
}
code, pre, .hl, .codewrap {
  font-family: "Noto Sans Mono CJK SC", "DejaVu Sans Mono", monospace;
}

/* ---------- 封面 ---------- */
.cover { height: 252mm; display: flex; flex-direction: column; justify-content: center;
         page-break-after: always; text-align: center; }
.cover .kicker { font-size: 11pt; letter-spacing: .35em; color: #6b7280; margin-bottom: 14mm; }
.cover h1 { font-size: 30pt; font-weight: 700; margin: 0 0 6mm; letter-spacing: .02em; line-height:1.3; }
.cover .sub { font-size: 13pt; color: #374151; margin-bottom: 18mm; }
.cover .chain { font-size: 12pt; color: #111827; margin-bottom: 4mm; }
.cover .chain b { color:#2563eb; }
.cover .meta { font-size: 9.5pt; color: #6b7280; line-height: 2; margin-top: 16mm; }
.cover hr { width: 46mm; border: none; border-top: 2px solid #2563eb; margin: 10mm auto; }

/* ---------- 目录 ---------- */
.toc { page-break-after: always; }
.toc h2 { font-size: 18pt; border: none; margin: 0 0 8mm; padding: 0; }
.toc a { color: #1c1e21; text-decoration: none; }
.toc .t0 { font-size: 11.5pt; font-weight: 700; margin: 5mm 0 2mm; color: #2563eb;
           border-bottom: 1px solid #e5e7eb; padding-bottom: 1.5mm; }
.toc .t2 { font-size: 9.8pt; margin: 1.2mm 0 1.2mm 4mm; font-weight: 600; }
.toc .t3 { font-size: 9pt; margin: .8mm 0 .8mm 11mm; color: #4b5563; }

/* ---------- 部分分隔页 ---------- */
.partdiv { page-break-before: always; height: 150mm; display: flex; flex-direction: column;
           justify-content: center; text-align: center; }
.partlabel { font-size: 26pt; font-weight: 700; color: #111827; letter-spacing:.02em;
             margin: 0; border: none; padding: 0; }
.partsub { font-size: 12.5pt; color: #6b7280; margin-top: 6mm; }

/* ---------- 正文标题 ---------- */
h2 { font-size: 16pt; font-weight: 700; margin: 11mm 0 4mm; padding-bottom: 2mm;
     border-bottom: 2px solid #2563eb; page-break-after: avoid; page-break-before: auto; }
h3 { font-size: 12.6pt; font-weight: 700; margin: 7mm 0 2.5mm; color: #1e40af;
     page-break-after: avoid; }
h4 { font-size: 10.8pt; font-weight: 700; margin: 5mm 0 2mm; color: #374151;
     page-break-after: avoid; }
p { margin: 2.4mm 0; }
ul, ol { margin: 2.4mm 0; padding-left: 7mm; }
li { margin: 1.1mm 0; }
strong { font-weight: 700; color: #111827; }
a { color: #2563eb; }
hr { border:none; border-top:1px solid #e5e7eb; margin: 6mm 0; }

/* ---------- 行内代码 ---------- */
p code, li code, td code, h2 code, h3 code, h4 code, strong code {
  background: #f1f3f5; padding: .4mm 1.4mm; border-radius: 2.4px;
  font-size: 9.1pt; color: #b91c1c; border: 1px solid #e6e8eb;
}

/* ---------- 代码块 ---------- */
.codewrap { margin: 3mm 0; page-break-inside: avoid; }
.codewrap pre { background: #f8f9fb; border: 1px solid #e3e6ea; border-left: 3px solid #2563eb;
  border-radius: 4px; padding: 3mm 3.5mm; margin: 0; font-size: 8.6pt; line-height: 1.6;
  white-space: pre-wrap; word-break: break-all; overflow-wrap: anywhere; }
.codewrap pre code { background: none; border: none; padding: 0; color: inherit; font-size: inherit; }
/* ASCII 示意图：整块不折行，按内容宽度缩字号 */
.codewrap.diagram pre { white-space: pre; word-break: normal; overflow-wrap: normal;
  font-size: var(--dsz, 7.6pt); line-height: 1.45; background:#fcfcfd; border-left-color:#94a3b8; }

/* ---------- 引用块：PM 视角 / 坑 / 普通 ---------- */
blockquote { margin: 3mm 0; padding: 2.6mm 4mm; border-radius: 4px;
  background: #eff6ff; border-left: 3.5px solid #2563eb; page-break-inside: avoid; }
blockquote p { margin: 1.2mm 0; }
blockquote.warn { background: #fff7ed; border-left-color: #ea580c; }
blockquote.note { background: #f5f3ff; border-left-color: #7c3aed; }

/* ---------- 表格 ---------- */
/* 长表允许跨页（表头自动重复），避免整表被推走留下大片空白 */
table { border-collapse: collapse; width: 100%; margin: 3.5mm 0; font-size: 9pt; }
thead { display: table-header-group; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid #dfe3e8; padding: 1.8mm 2.4mm; text-align: left;
         vertical-align: top; word-break: break-word; }
th { background: #f1f5f9; font-weight: 700; }
tr:nth-child(even) td { background: #fbfcfd; }

.chunk { page-break-before: auto; }
"""


def main() -> int:
    md = build_md()
    body, toc = collect(md)
    pyg = HtmlFormatter(cssclass="hl").get_style_defs(".hl")

    page = f"""<!DOCTYPE html><html lang="de"><head><meta charset="utf-8">
<title>Pydantic Komplettkurs · CEO-Perspektive</title>
<style>{CSS}
{pyg}
</style></head><body>
<div class="cover">
  <div class="kicker">Ein Technik-Handbuch für CEOs</div>
  <h1>Pydantic Komplettkurs</h1>
  <div class="sub">Von Datenvalidierung über AI-Agenten bis zu Graph-Workflows</div>
  <hr>
  <div class="chain"><b>Pydantic</b> &nbsp;→&nbsp; <b>Pydantic AI</b> &nbsp;→&nbsp; <b>Pydantic Graph</b></div>
  <div class="meta">
    Referenzversionen: pydantic 2.13.4 · pydantic-ai 2.17.0 (v2) · pydantic-graph 2.17.0 · pydantic-ai-harness 0.10.0<br>
    Sämtlicher Code wurde in diesen Versionen tatsächlich ausgeführt und verifiziert
  </div>
</div>
<div class="toc"><h2>Inhaltsverzeichnis</h2>
{toc_html(toc)}
</div>
{body}
</body></html>"""

    OUT_HTML.write_text(page, encoding="utf-8")
    print(f"HTML 生成: {OUT_HTML}  ({len(page)/1024:.0f} KB)")

    with sync_playwright() as p:
        b = p.chromium.launch(executable_path=CHROME,
                              args=["--no-sandbox", "--disable-dev-shm-usage", "--font-render-hinting=none"])
        pg = b.new_page()
        pg.goto(OUT_HTML.as_uri(), wait_until="load")
        pg.emulate_media(media="print")
        pg.pdf(path=str(OUT_PDF), format="A4", print_background=True,
               outline=True, tagged=True,   # PDF 书签大纲 + 无障碍标签
               display_header_footer=True,
               header_template='<div></div>',
               footer_template=('<div style="font-size:8pt;width:100%;text-align:center;'
                                'color:#9ca3af;font-family:sans-serif;padding-top:4mm">'
                                '<span class="pageNumber"></span></div>'),
               margin={"top": "18mm", "bottom": "16mm", "left": "16mm", "right": "16mm"})
        b.close()

    from pypdf import PdfReader
    r = PdfReader(str(OUT_PDF))
    print(f"PDF 生成: {OUT_PDF}")
    print(f"  页数: {len(r.pages)}   大小: {OUT_PDF.stat().st_size/1024/1024:.2f} MB")
    txt = "".join((r.pages[i].extract_text() or "") for i in range(min(6, len(r.pages))))
    umlaut = sum(txt.count(c) for c in "äöüÄÖÜß")
    print(f"  德语字符校验: {'OK' if umlaut > 20 else '失败!!'}  (变音符共 {umlaut} 处)")
    print(f"  CJK 代码字面量渲染: {'OK' if any('一' <= c <= '鿿' for c in ''.join((r.pages[i].extract_text() or '') for i in range(40, min(60, len(r.pages))))) else '(该区间无CJK)'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
