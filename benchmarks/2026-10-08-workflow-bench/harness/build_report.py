"""Build the Chinese HTML report from results.json -> report.html"""
import html, json, math
from pathlib import Path

B = Path(__file__).resolve().parent
R = json.loads((B / "results.json").read_text())
W = R["weights"]
C = ["grill", "pstack", "matt"]
NAME = {"matt": "Matt /implement", "grill": "Grilling → Spec", "pstack": "pstack"}
SUB = {"matt": "/implement → tdd → code-review", "grill": "/grilling → /to-spec → /implement", "pstack": "/pstack:poteto-mode（插件）"}
DIM = [("correctness", "正确性"), ("robustness", "鲁棒性"), ("scalability", "可扩展性"), ("quality", "代码质量"),
       ("tests", "测试质量"), ("efficiency", "效率")]
avg = {c: round((R["py"][c]["total"] + R["ts"][c]["total"]) / 2, 1) for c in C}
e = html.escape


def bar_row(c, task):
    r = R[task][c]
    segs = "".join(
        f'<span class="seg s-{k}" style="width:{r["score"][k]:.2f}%" title="{lab} {r["score"][k]:.1f} / {W[k]}"></span>'
        for k, lab in DIM)
    return (f'<div class="brow"><div class="blab"><span class="dot d-{c}"></span>{e(NAME[c])}</div>'
            f'<div class="btrack">{segs}</div><div class="bval">{r["total"]:.1f}</div></div>')


def dim_table(task):
    head = "".join(f"<th>{lab}<small>/{W[k]}</small></th>" for k, lab in DIM)
    rows = ""
    for c in C:
        r = R[task][c]
        best = {k: max(R[task][x]["score"][k] for x in C) for k, _ in DIM}
        cells = "".join(
            f'<td class="num{" best" if round(r["score"][k], 1) == round(best[k], 1) else ""}">{r["score"][k]:.1f}</td>' for k, _ in DIM)
        rows += f'<tr><th scope="row"><span class="dot d-{c}"></span>{e(NAME[c])}</th>{cells}<td class="num tot">{r["total"]:.1f}</td></tr>'
    return f'<div class="tw"><table><thead><tr><th></th>{head}<th>合计</th></tr></thead><tbody>{rows}</tbody></table></div>'


TS_SCEN = [("independent_20k_c4", "2 万独立任务"), ("chain_5k", "5000 长依赖链"), ("chain_5k_reverse_add", "5000 链反向添加"),
           ("fanout_1_to_10k_fail_cascade", "1 → 1 万级联取消"), ("diamond_layers_200x20", "200×20 钻石依赖")]
PY_SCEN = [("chain_100k", "10 万长链改链首"), ("sum_100k_edits", "10 万格 SUM 内 300 次编辑"),
           ("range_index_2k_formulas", "2000 前缀和下无关编辑"), ("fanout_20k", "2 万扇出改源"),
           ("insert_rows_50k", "5 万格插入/删除行"), ("copy_block_100x50", "复制 100×50 公式块")]


def tv(v):
    v = v[0] if isinstance(v, list) else v
    return None if isinstance(v, str) else float(v)


def scale_chart(task, scen, cap):
    lo, hi = math.log10(30), math.log10(cap)
    out = ""
    for key, lab in scen:
        bars = ""
        for c in C:
            v = tv(R[task][c]["scale"][key])
            if v is None:
                w, txt, cls = 100, f">{cap/1000:.0f} s 超时", " over"
            else:
                w = max(2, (math.log10(max(v, 30)) - lo) / (hi - lo) * 100)
                txt, cls = (f"{v:.0f} ms" if v < 1000 else f"{v/1000:.1f} s"), ""
            bars += (f'<div class="sbar"><span class="dot d-{c}"></span><div class="strack"><span class="sfill f-{c}{cls}" '
                     f'style="width:{w:.1f}%"></span></div><span class="sval{cls}">{txt}</span></div>')
        out += f'<div class="scen"><div class="sname">{lab}</div>{bars}</div>'
    return out


def judge_table(task):
    ks = [("design", "设计"), ("readability", "可读性"), ("maintainability", "可维护性"), ("robustness", "健壮性"),
          ("tests", "测试"), ("docs", "文档"), ("overall", "综合")]
    head = "".join(f"<th>{l}</th>" for _, l in ks)
    rows = ""
    for c in C:
        j = R[task][c]["judge"]
        best = {k: max(R[task][x]["judge"][k] for x in C) for k, _ in ks}
        cells = "".join(f'<td class="num{" best" if j[k] == best[k] else ""}">{j[k]:g}</td>' for k, _ in ks)
        ranks = " ".join(str(x) for x in R[task][c]["judge_ranks"])
        rows += f'<tr><th scope="row"><span class="dot d-{c}"></span>{e(NAME[c])}</th>{cells}<td class="num mono">{ranks}</td></tr>'
    return f'<div class="tw"><table><thead><tr><th></th>{head}<th>4 位裁判排名</th></tr></thead><tbody>{rows}</tbody></table></div>'


def process_table():
    rows = ""
    for task, tl in (("py", "Python"), ("ts", "TS")):
        for c in C:
            r = R[task][c]
            ask = f'拷问 {"22" if task == "py" else "17"} 问 + {r["ask_po"]} 次' if c == "grill" else f'{r["ask_po"]} 次'
            models = " + ".join(m.replace("claude-", "").replace("-5-5", "").replace("-5-1", "").title() for m in r["models"])
            rows += (f'<tr><th scope="row"><span class="dot d-{c}"></span>{e(NAME[c])}<small> · {tl}</small></th>'
                     f'<td class="num">{r["hidden"]}</td><td class="num">{r["fuzz_pct"]:g}%</td>'
                     f'<td class="num">{r["wall_min"]:g} 分</td><td class="num">${r["cost"]:.2f}</td>'
                     f'<td class="num">{r["tool_calls"]}</td><td class="num">{r["own_tests"]}</td>'
                     f'<td class="num">{r["loc_src"]} / {r["loc_tests"]}</td><td>{ask}</td><td>{models}</td></tr>')
    return (f'<div class="tw"><table><thead><tr><th></th><th>隐藏验收</th><th>差分一致</th><th>墙钟</th><th>成本</th>'
            f'<th>工具调用</th><th>自测数</th><th>源码/测试行</th><th>向 PO 提问</th><th>用到的模型</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')


podium = ""
for i, c in enumerate(sorted(C, key=lambda c: -avg[c])):
    podium += (f'<div class="pod p-{c}"><div class="prank">{i + 1}</div><div class="pname">{e(NAME[c])}</div>'
               f'<div class="psub">{e(SUB[c])}</div><div class="pscore">{avg[c]:.1f}</div>'
               f'<div class="pparts">Python {R["py"][c]["total"]:.1f} · TS {R["ts"][c]["total"]:.1f}</div></div>')

legend = "".join(f'<span class="lg"><span class="sw s-{k}"></span>{l} {W[k]}</span>' for k, l in DIM)

page = f"""<title>Claude 工作流基准</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;500;700&family=Noto+Serif+SC:wght@600;900&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
/* Layout: single reading column (max 980px) of report sections; scoreboard podium first, data tables scroll inside their own frames. */
:root {{
  --bg: #f3f5f2; --surface: #ffffff; --ink: #18211d; --muted: #5d6b64; --rule: #d8dfda;
  --accent: #1f6f5c;
  --c-grill: #c2561d; --c-pstack: #3d5aa8; --c-matt: #2b8a72;
  --d1: #1f3d36; --d2: #3f7a6c; --d3: #8fb3a6; --d4: #c98b4a; --d5: #e3b97a; --d6: #9aa59f;
  --good: #1f7a4d; --bad: #b3261e; --best-bg: #e3efe8;
  --f-display: "Noto Serif SC", "Songti SC", serif; --f-body: "Noto Sans SC", "PingFang SC", system-ui, sans-serif;
  --f-mono: "IBM Plex Mono", ui-monospace, Menlo, monospace;
}}
@media (prefers-color-scheme: dark) {{ :root:not([data-theme="light"]) {{
  --bg: #121815; --surface: #1a221e; --ink: #e6ece8; --muted: #9aaba2; --rule: #2e3a34; --accent: #6cc4a8;
  --c-grill: #f08a4b; --c-pstack: #8ea6f0; --c-matt: #5cc3a3;
  --d1: #b9d8cc; --d2: #6ea997; --d3: #3f6d61; --d4: #d79a58; --d5: #a8824e; --d6: #5b6862;
  --good: #6fd19b; --bad: #ff8a80; --best-bg: #23362d; color-scheme: dark; }} }}
:root[data-theme="dark"] {{
  --bg: #121815; --surface: #1a221e; --ink: #e6ece8; --muted: #9aaba2; --rule: #2e3a34; --accent: #6cc4a8;
  --c-grill: #f08a4b; --c-pstack: #8ea6f0; --c-matt: #5cc3a3;
  --d1: #b9d8cc; --d2: #6ea997; --d3: #3f6d61; --d4: #d79a58; --d5: #a8824e; --d6: #5b6862;
  --good: #6fd19b; --bad: #ff8a80; --best-bg: #23362d; color-scheme: dark; }}
* {{ box-sizing: border-box; }}
body {{ background: var(--bg); color: var(--ink); font: 15px/1.75 var(--f-body); margin: 0; }}
.wrap {{ max-width: 980px; margin: 0 auto; padding-inline: 20px; padding-block: 40px 72px; display: grid; gap: 44px; }}
header {{ display: grid; gap: 14px; }}
.eyebrow {{ font: 500 12px/1 var(--f-mono); letter-spacing: .08em; color: var(--muted); text-transform: uppercase; }}
h1 {{ font: 900 clamp(30px, 5vw, 46px)/1.15 var(--f-display); margin: 0; text-wrap: balance; }}
h2 {{ font: 600 24px/1.3 var(--f-display); margin: 0 0 6px; text-wrap: balance; }}
h3 {{ font: 700 16px/1.4 var(--f-body); margin: 18px 0 8px; }}
p {{ margin: 0; max-width: 68ch; }}
.lede {{ font-size: 17px; color: var(--ink); }}
.meta {{ display: flex; flex-wrap: wrap; gap: 8px 18px; font: 13px/1.5 var(--f-mono); color: var(--muted); }}
section {{ display: grid; gap: 14px; }}
.note {{ color: var(--muted); font-size: 13.5px; }}
.podium {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
@media (max-width: 720px) {{ .podium {{ grid-template-columns: 1fr; }} }}
.pod {{ background: var(--surface); border: 1px solid var(--rule); border-top: 4px solid var(--pc); padding: 16px 18px 18px; display: grid; gap: 4px; min-width: 0; }}
.p-grill {{ --pc: var(--c-grill); }} .p-pstack {{ --pc: var(--c-pstack); }} .p-matt {{ --pc: var(--c-matt); }}
.prank {{ font: 500 12px var(--f-mono); color: var(--muted); }}
.prank::before {{ content: "第 "; }} .prank::after {{ content: " 名"; }}
.pname {{ font: 700 18px/1.3 var(--f-body); color: var(--pc); }}
.psub {{ font: 12px/1.4 var(--f-mono); color: var(--muted); overflow-wrap: anywhere; }}
.pscore {{ font: 900 44px/1.1 var(--f-display); font-variant-numeric: tabular-nums; margin-top: 6px; }}
.pparts {{ font: 13px var(--f-mono); color: var(--muted); font-variant-numeric: tabular-nums; }}
.bars {{ display: grid; gap: 10px; }}
.brow {{ display: grid; grid-template-columns: 150px minmax(0, 1fr) 48px; gap: 10px; align-items: center; }}
@media (max-width: 560px) {{ .brow {{ grid-template-columns: 1fr 48px; }} .btrack {{ grid-column: 1 / -1; grid-row: 2; }} }}
.blab {{ font-size: 14px; display: flex; align-items: center; gap: 8px; min-width: 0; }}
.btrack {{ display: flex; height: 18px; background: var(--rule); overflow: hidden; }}
.seg {{ display: block; height: 100%; border-right: 1px solid var(--surface); }}
.s-correctness {{ background: var(--d1); }} .s-robustness {{ background: var(--d2); }} .s-scalability {{ background: var(--d3); }}
.s-quality {{ background: var(--d4); }} .s-tests {{ background: var(--d5); }} .s-efficiency {{ background: var(--d6); }}
.bval {{ font: 500 15px var(--f-mono); text-align: right; font-variant-numeric: tabular-nums; }}
.legend {{ display: flex; flex-wrap: wrap; gap: 6px 16px; font-size: 12.5px; color: var(--muted); }}
.lg {{ display: inline-flex; align-items: center; gap: 6px; }}
.sw {{ width: 12px; height: 12px; display: inline-block; }}
.dot {{ width: 10px; height: 10px; border-radius: 50%; display: inline-block; flex: none; }}
.d-grill {{ background: var(--c-grill); }} .d-pstack {{ background: var(--c-pstack); }} .d-matt {{ background: var(--c-matt); }}
.twocol {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px; }}
@media (max-width: 760px) {{ .twocol {{ grid-template-columns: 1fr; }} }}
.panel {{ background: var(--surface); border: 1px solid var(--rule); padding: 16px 18px; display: grid; gap: 12px; min-width: 0; }}
.tw {{ overflow-x: auto; background: var(--surface); border: 1px solid var(--rule); }}
table {{ border-collapse: collapse; width: 100%; font-size: 13.5px; }}
th, td {{ padding: 8px 10px; border-bottom: 1px solid var(--rule); text-align: left; white-space: nowrap; vertical-align: middle; }}
thead th {{ font: 500 12px/1.3 var(--f-body); color: var(--muted); background: var(--bg); }}
thead th small {{ font-family: var(--f-mono); margin-left: 2px; }}
tbody th {{ font-weight: 500; }} tbody th small {{ color: var(--muted); font-weight: 400; }}
tbody th .dot {{ margin-right: 8px; }}
td.num {{ font-family: var(--f-mono); font-variant-numeric: tabular-nums; text-align: right; }}
td.best {{ background: var(--best-bg); font-weight: 500; }}
td.tot {{ font-weight: 500; }}
.mono {{ font-family: var(--f-mono); }}
tr:last-child th, tr:last-child td {{ border-bottom: 0; }}
.scen {{ display: grid; gap: 4px; padding-block: 6px; border-bottom: 1px dashed var(--rule); }}
.scen:last-child {{ border-bottom: 0; }}
.sname {{ font-size: 13px; color: var(--muted); }}
.sbar {{ display: grid; grid-template-columns: 10px minmax(0, 1fr) 84px; gap: 8px; align-items: center; }}
.strack {{ height: 9px; background: var(--rule); }}
.sfill {{ display: block; height: 100%; }}
.f-grill {{ background: var(--c-grill); }} .f-pstack {{ background: var(--c-pstack); }} .f-matt {{ background: var(--c-matt); }}
.sfill.over {{ background: repeating-linear-gradient(45deg, var(--bad) 0 6px, transparent 6px 10px); }}
.sval {{ font: 12px var(--f-mono); text-align: right; font-variant-numeric: tabular-nums; }}
.sval.over {{ color: var(--bad); font-weight: 500; }}
.finding {{ display: grid; grid-template-columns: 34px minmax(0, 1fr); gap: 4px 12px; padding-block: 14px; border-top: 1px solid var(--rule); }}
.finding .n {{ font: 900 22px/1.2 var(--f-display); color: var(--accent); }}
.finding h3 {{ margin: 0 0 4px; }}
.reco {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }}
@media (max-width: 760px) {{ .reco {{ grid-template-columns: 1fr; }} }}
.reco .panel h3 {{ margin: 0; }}
.tag {{ font: 500 12px var(--f-mono); color: var(--muted); }}
ul {{ margin: 0; padding-left: 1.2em; display: grid; gap: 6px; max-width: 72ch; }}
code {{ font: 13px var(--f-mono); background: var(--bg); padding: 1px 4px; border: 1px solid var(--rule); }}
.defect {{ color: var(--bad); }} .ok {{ color: var(--good); }}
a {{ color: var(--accent); }}
:focus-visible {{ outline: 2px solid var(--accent); outline-offset: 2px; }}
</style>

<div class="wrap">
<header>
  <div class="eyebrow">Claude Code 无人值守基准 · 2026-10-08</div>
  <h1>Matt Skills、Grilling → Spec、pstack：谁写的代码更好</h1>
  <p class="lede">两道高难度题（Python 电子表格引擎、TypeScript 依赖调度器），三套工作流在相互隔离的沙箱里各自完成，用隐藏验收、差分模糊测试、规模探针和 4 位盲评裁判打分。<b>三家在正确性上几乎打平，差距来自设计质量、可扩展性和成本。</b></p>
  <div class="meta"><span>主模型 claude-opus-5-5 · effort high</span><span>6 次运行 · n=1</span><span>隐藏测试 Py 463 / TS 172</span></div>
</header>

<section aria-labelledby="s-score">
  <h2 id="s-score">综合排名</h2>
  <div class="podium">{podium}</div>
  <p class="note">两道题综合分的平均值，满分 100。去掉“效率”后重新加权（90 分制）：Grilling → Spec 83.0、pstack 78.7、Matt 71.9，名次不变。</p>
</section>

<section aria-labelledby="s-dim">
  <h2 id="s-dim">分维度得分</h2>
  <div class="legend">{legend}</div>
  <div class="twocol">
    <div class="panel"><h3 style="margin:0">Python · gridcalc 电子表格引擎</h3><div class="bars">{"".join(bar_row(c, "py") for c in C)}</div></div>
    <div class="panel"><h3 style="margin:0">TypeScript · taskflow 依赖调度器</h3><div class="bars">{"".join(bar_row(c, "ts") for c in C)}</div></div>
  </div>
  <h3>Python 明细</h3>{dim_table("py")}
  <h3>TypeScript 明细</h3>{dim_table("ts")}
  <p class="note">高亮为该维度最高分。正确性＝隐藏验收按类别平均；鲁棒性＝差分模糊一致率（2/3）＋ 经复现的缺陷扣分（1/3，严重 −5、轻微 −1）；可扩展性＝各规模场景相对最快者的比值；代码质量＝盲评设计/可读性/可维护性/健壮性均值；测试质量＝盲评测试分 70% ＋ 覆盖率 30%；效率＝成本与墙钟各占一半。</p>
</section>

<section aria-labelledby="s-correct">
  <h2 id="s-correct">正确性：全员接近满分</h2>
  <p>6 份实现的隐藏验收都 ≥ 99.8%，与参考实现的差分模糊测试一致率都 ≥ 99.7%。隐藏测试和参考实现由两个互不可见的子代理分别编写，交叉验证 100% 吻合。规格留白、只能问 PO 才知道的决策类测试（Py 114 / TS 42）三家几乎全对，只有 Matt 的 Python 版漏了 <code>SUM(1E308,1E308)</code> 溢出应为 <code>#VALUE!</code>。</p>
  <ul>
    <li><span class="defect">严重缺陷</span>：Matt 的 TS 版一次添加 2 万个链式依赖任务时，递归找环导致 <code>RangeError: Maximum call stack size exceeded</code>。4 位裁判读代码时都预言了这个问题，复现确认。</li>
    <li><span class="defect">轻微缺陷</span>：Grill 的 TS 版在超时 abort 监听器里调用 <code>cancel()</code> 时，仍会补发一次 <code>retry</code> 事件（参考实现也有同样行为）。</li>
    <li><span class="ok">无缺陷</span>：pstack 两份、Grill 的 Python 版、Matt 的 Python 版没有复现出裁判声称的缺陷。pstack 的 Python 版 300 个模糊种子中有 1 个分歧，落在规格歧义点上，未计为缺陷。</li>
  </ul>
</section>

<section aria-labelledby="s-scale">
  <h2 id="s-scale">可扩展性：TS 拉开最大差距</h2>
  <p>规格没要求的规模场景，对数刻度，越短越快。每个场景单独进程运行，上限 90 秒。</p>
  <div class="twocol">
    <div class="panel"><h3 style="margin:0">TypeScript</h3>{scale_chart("ts", TS_SCEN, 90000)}</div>
    <div class="panel"><h3 style="margin:0">Python（关键段耗时）</h3>{scale_chart("py", PY_SCEN, 90000)}</div>
  </div>
  <p class="note">Grilling → Spec 的 TS 版用最小堆选任务，只在出现前向引用或自依赖时才做环检测，所有场景低于 160 ms。pstack 每次 add 都做全量 DFS，Matt 递归找环且每层复制路径、再线性扫描就绪队列。Python 三家处于同一数量级。</p>
</section>

<section aria-labelledby="s-judge">
  <h2 id="s-judge">代码质量盲评</h2>
  <p>4 位裁判（Opus ×2、Fable ×2），每位看到随机顺序的匿名 X/Y/Z，提交中涉及工作流的关键词已抹去。分数为 1–10 均值。</p>
  <h3>Python</h3>{judge_table("py")}
  <h3>TypeScript</h3>{judge_table("ts")}
  <ul>
    <li><b>Grilling → Spec（Py）</b>：全迭代流水线（词法 → 调度场 → 代码生成 → 栈式 VM），不碰递归上限；Kahn 排序后只对剩余部分跑 Tarjan；结构编辑增量重定位；随机差分自测。缺点是概念多、类型忽略注释多。</li>
    <li><b>pstack（TS）</b>：用判别联合表达任务状态，非法状态难以构造；测试三家最强，有精确事件序列断言、定时器监控、未处理 rejection 陷阱和变异测试脚本。缺点是所有逻辑集中在一个文件，源码零注释。</li>
    <li><b>pstack（Py）</b>：模块小而清晰，函数注册表易扩展；但递归求值依赖临时调高 <code>sys.setrecursionlimit</code>，结构编辑全量重算。</li>
    <li><b>Matt（TS）</b>：紧凑易读、NOTES 详尽；算法选择（递归找环、线性扫描）不可扩展，测试偏薄。</li>
  </ul>
</section>

<section aria-labelledby="s-proc">
  <h2 id="s-proc">过程与成本</h2>
  {process_table()}
  <p class="note">成本含子代理。pstack 按其默认路由把最难的步骤交给 Fable，约一半花费在 Fable 上。Matt 的 Python 版主动用 <code>ask-po</code> 问了 23 次；pstack 的 Python 版只问 1 次，其余自己决定。</p>
</section>

<section aria-labelledby="s-find">
  <h2 id="s-find">分析</h2>
  <div class="finding"><div class="n">1</div><div><h3>正确性被模型能力打满</h3><p>对 Opus 5.5 这一级的模型，规格清楚、又能问到人时，工作流不再决定对不对，而是决定好不好、快不快、贵不贵。</p></div></div>
  <div class="finding"><div class="n">2</div><div><h3>拷问的价值体现在设计，而不在澄清需求</h3><p>决策类测试三家都几乎满分，问得多（Matt 23 次）和问得少（pstack 1 次）结果一样。Grilling → Spec 赢在拷问阶段就把测试缝、性能预算和 17–22 个边界语义谈定，随后的实现设计分两题都是 9.0，TS 可扩展性最好。代价是约 2 倍时间和成本。</p></div></div>
  <div class="finding"><div class="n">3</div><div><h3>Matt /implement 性价比最高，但容易停在能过测试</h3><p>TS 11 分钟、$2.94 就交付了全对的实现，但算法上走了捷径，隐藏测试和模糊测试都抓不到，只有规模探针和读代码的裁判发现了问题。</p></div></div>
  <div class="finding"><div class="n">4</div><div><h3>pstack 强在验证纪律，弱在成本</h3><p>测试最重、带变异测试和决策轨迹，TS 盲评综合分最高；但成本是 Matt 的 2.3–4.8 倍，Python 版的递归求值和全量重算被扣了设计分。</p></div></div>
  <div class="finding"><div class="n">5</div><div><h3>无人值守时，阶段边界靠模型理解</h3><p>Grill 的 TS 版在 PO 回答“yes”后直接开始实现，spec 是事后补写的；Python 版按顺序执行。</p></div></div>
</section>

<section aria-labelledby="s-reco">
  <h2 id="s-reco">怎么选</h2>
  <div class="reco">
    <div class="panel"><span class="tag">原型 · 小模块 · 规格清晰</span><h3>Matt /implement</h3><p>正确性不输、最快最省。上线前补一次规模和性能检查。</p></div>
    <div class="panel"><span class="tag">长期维护 · 有性能要求</span><h3>Grilling → Spec</h3><p>设计、可扩展性、文档全面领先，约 2 倍成本换来更少的返工。</p></div>
    <div class="panel"><span class="tag">高风险 · 需要审计轨迹</span><h3>pstack</h3><p>验证纪律最强、过程透明。预算按 3–5 倍准备；无头运行需关闭后台任务。</p></div>
  </div>
</section>

<section aria-labelledby="s-lim">
  <h2 id="s-lim">局限</h2>
  <ul>
    <li>每个组合只跑 1 次，同一工作流重跑会有波动；小差距不宜过度解读。</li>
    <li>题目对当前模型偏容易（正确性天花板），区分度主要来自补充维度；可扩展性和效率的权重带主观性。</li>
    <li>pstack 按设计调用 Fable / Sonnet 子代理，不是严格的同模型对比。</li>
    <li>pstack 首轮运行中，<code>claude -p</code> 在回合结束时杀掉了它的后台子代理；两次 pstack 运行已作废，并在 <code>CLAUDE_CODE_DISABLE_BACKGROUND_TASKS=1</code> 下从零重跑。Matt 两位选手从不使用后台子代理。</li>
    <li>PO、隐藏测试、参考实现和裁判都来自 Claude 家族，可能存在同源偏好；匿名化无法完全掩盖代码风格。</li>
  </ul>
</section>

<section aria-labelledby="s-method">
  <h2 id="s-method">方法</h2>
  <ul>
    <li><b>隔离</b>：每个选手运行在独立的 mount + PID 命名空间，只能看到自己的 <code>/arena</code> 工作区和自己的技能；隐藏测试、其他选手、宿主会话全部不可见。</li>
    <li><b>同条件</b>：同一模型与 effort、auto 权限模式、禁用联网搜索、相同任务提示词，只有工作流入口不同。</li>
    <li><b>模拟用户</b>：所有选手都能用 <code>ask-po</code> 问产品负责人（独立 Claude，只按 12 条隐藏决策回答被问到的问题）；拷问轮次和回合末的提问由驱动器转交同一个 PO。</li>
    <li><b>数据与代码</b>：完整工具链、隐藏测试、参考实现、6 份提交和评分 JSON 在仓库 <code>Keason-C/skills</code> 分支 <code>ccr-2cb2360b-uhgbp9</code> 的 <code>benchmarks/2026-10-08-workflow-bench/</code>。</li>
  </ul>
</section>
</div>
"""
(B / "report.html").write_text(page)
print("ok", len(page))
