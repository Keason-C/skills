# REFLECTION.md — superpowers-runner-2 过程日志

工单:#4821(sqlite-utils 数据质量校验 + 可交互报告)
方法论:obra/superpowers 6.2.0,严格按技能链执行。
适配声明:本环境无法真正派发 subagent。凡技能要求 dispatch subagent 的环节(writing-plans 的
plan review、executing-plans 的 implementer/reviewer 分工、requesting-code-review 的独立
reviewer),我**串行扮演各角色**,每次角色切换都会在下面注明,并尽量做到"换角色时只带上该角色
应该看到的输入"。

---

## 阶段 0 — using-superpowers

读了 `using-superpowers/SKILL.md`。它的规则很硬:任何回应之前(包括澄清提问之前)必须先进技能。
这条对我实际有约束力——我拿到 TASK2.md 的第一反应是"先 `ls` 一下仓库摸摸底",而技能明确把
"Let me explore the codebase first" 列为红旗:*Skills tell you HOW to explore*。

**想跳过的冲动**:有。理由是"我总得知道这是个什么仓库才知道该用哪个技能"。但实际上技能链的选择
根本不依赖仓库内容——"给现存项目加功能" → brainstorming 是无条件的。所以这条红旗是对的,我这个
冲动是伪需求。

**开销**:几乎为零(读一个 60 行文件),收益是把后面的顺序钉死了。值。

## 阶段 1 — brainstorming(探索 + 提问)

按 checklist 第 1 项先做 *Explore project context*。这一步在**存量仓库**上和绿地项目的差别在这里
第一次显现:绿地项目的 "explore context" 基本是空操作,而这里它是整个任务里信息密度最高的一步。
我读了:git log、pyproject.toml(依赖策略、dev group)、mypy.ini(**关键发现:`sqlite_utils.cli`
被 `ignore_errors = True` 豁免了 mypy**,所以"新 Python 代码过 mypy"这条验收只能靠把逻辑放进
非 cli 模块来真正兑现)、Justfile(lint 链含 black/flake8/mypy/ty/cog/codespell)、
`.github/workflows/test.yml`(**CI 用 pip 装、只跑 pytest,没有 node**→ 前端构建产物必须提交进仓库
并进 package-data,否则 CI 和用户安装都会拿不到报告模板)、`tests/test_docs.py`(**新命令必须出现在
docs/cli.rst 里,否则参数化测试直接挂**)、`docs/cli-reference.rst`(cog 生成,CI 有 `cog --check`)。

这五条里有四条是"不读就一定会踩"的坑,而且都不在 TASK2.md 里。**这就是 superpowers 在存量代码库上
比绿地更有价值的地方:它把"先理解既有约定"从一个自觉行为变成了 checklist 上的必做项。**绿地项目里
这一步是仪式,这里它直接改变了架构(逻辑必须离开 cli.py;构建产物必须入库)。

跑了基线全量测试:`1371 passed, 19 skipped in 23.45s`。这个基线是"老测试一个不能挂"唯一可验证的锚点,
不先跑就没得比。

**被打断/干扰的地方**:brainstorming 要求"一次问一个问题"。我这条通道是异步的(问完必须结束回合、
等 PM 回信),一次一个问题意味着 N 个回合。任务书要求"一次问全",我按任务书办,并在这里记档:
这是对技能的一处偏离,代价是失去了"根据上一个答案调整下一个问题"的能力——我只能靠给每个问题附上
推荐默认值来补偿。

**开销值不值**:到目前为止值。探索阶段花掉的时间全部转化成了硬约束,没有一条是白读的。

## 阶段 2 — brainstorming(方案 → 设计 → spec)

Iris 九个问题全答了,其中第 6 条给了修订(把"明细上限"和"只扫前 N 行"拆成两个参数)。**这条修订是
提问纪律直接换来的产出改变**:如果我不问,我会按自己的默认把两者合并成一个 `--limit`,那就正好踩中
她"别混在一个参数里"的雷。brainstorming 里"先问、别猜业务"这条在这里兑现了。

写 spec 时最有价值的一步是 checklist 第 4 项 *Propose 2-3 approaches with trade-offs*。我本来会直接
上 `jsonschema`,写对比时才被迫想清楚"为什么不自己实现子集"——理由不是"懒",而是**部分实现会对
没检查过的关键字报 clean,这是比多一个依赖更坏的失败模式**。这句话现在写进了决策记录,是能拿去说服
老周的话,而不是我的偏好。同理,"逻辑放哪"这个对比逼出了那条 mypy 豁免的后果:
`[mypy-sqlite_utils.cli] ignore_errors = True` 意味着**把逻辑写进 cli.py 会让"新代码过 mypy"变成
一句空话**。这是存量仓库特有的陷阱,绿地项目没有这种"既有配置反过来约束新架构"的情况。

**spec 自审**(checklist 第 7 项)不是走过场:两处真实歧义被抓出来——(1) 表级错误算不算进
`total_violations`、影不影响退出码;(2) 默认往 stdout 打什么。两个都是实现时必然要现场拍板的点,
现在提前定死了,省掉后面来回改。

**想跳过的冲动**:有,而且比阶段 0 强。我已经很清楚要写什么代码了,"再写一份 spec 是重复劳动"的感觉
很强。事后看,spec 本身的措辞不是重点,**逼我做对比和自审的那两个 checklist 项才是**。

**用户审批门**:brainstorming 要求 spec 写完后等用户 review。我的通道最多两轮提问且 Iris 已回
"请继续你的工作流",我把这句当作放行,不再占用第二轮提问额度。这是第二处对技能的偏离,记录在案。

## 阶段 3 — writing-plans

写了 8 个任务的实施计划(`docs/superpowers/plans/2026-07-31-validate-command.md`),每个任务都是
"先写失败测试 → 跑它确认失败 → 最小实现 → 跑通 → 提交"的五步循环。

**这一步开销最大,也最容易让人不耐烦。**计划文档比我最终要写的代码还长。中途我明确想过:"我脑子里
已经有完整实现了,直接写代码不是更快?"

事后判断:**部分值得,但不是我以为的那个理由。**计划的价值不在"记录我要写什么"(那部分确实是重复
劳动),而在两个硬 checklist 上:

1. *No Placeholders*。自审时我抓到自己在 Task 4 用一串注释("// Filter bar: select.filter-column,
   ... 调用 draw()")代替了真实的 render.ts 代码,还给自己找了个借口:"这是 UI 骨架,写细了浪费"。
   技能明确把 "Steps that describe what to do without showing how" 列为 plan failure。我回去把
   ~150 行 render.ts 真写了出来。**这不是形式主义**:写的过程中才发现 `draw()` 重建 tbody 会把
   展开的详情行丢掉、以及 clean-state 提前 return 必须在 filter bar 之前——这两个是实现时一定会
   踩、debug 起来还挺费劲的点。
2. *Type consistency* 自查。逐个核对了前后任务的签名,发现 tsconfig 的 `include` 里列了 `build.mjs`
   (在 `allowJs:false` 下多余且可能报错)、`css.d.ts` 漏在文件清单里。都是小事,但都是会打断
   实现节奏的小事。

**存量仓库 vs 绿地的差异(第二次显现)**:计划里"Files: Modify `sqlite_utils/cli.py:3019 附近`"这种
精确到行的要求,在绿地项目里毫无意义(文件都是新的),在这里则强迫我提前把新命令插在哪、import 加在
哪、会不会破坏 cog 的 `refs` 字典都想清楚了。**Global Constraints 这一节尤其适配存量仓库**——我把
"baseline 1371 passed"、"cli.py 不受 mypy 检查"、"CI 没有 Node"、"test_docs.py 会强制文档"这四条
仓库既有事实写成了每个任务隐含的约束。绿地项目的 Global Constraints 通常是空洞的技术偏好清单。

**碍事的地方**:writing-plans 要求"假设执行者对代码库零上下文"。我就是执行者,而我此刻上下文最满。
为一个我自己马上要执行的计划写"零上下文说明"是真实的浪费,大概占了这一步一半的字数。这个纪律是为
subagent 派发设计的,在我这种串行单体模式下打了折扣。

**冲动记录**:想跳过 self-review 直接进实现。没跳,收益如上。

## 阶段 4 — executing-plans + test-driven-development

**适配声明**:executing-plans 第 1 步要求用 using-git-worktrees 建隔离工作区。worktree 会把目录建在
仓库外,违反"只在此仓库目录内创建/修改文件"的任务约束,因此我改为**在原地开 `validate-command`
分支**——满足"绝不在 main 上实现"的硬要求,牺牲了物理隔离。第三处对技能的偏离,记录在案。
另外该技能明确说"有 subagent 时请改用 subagent-driven-development",我这里只能串行扮演。

TDD 严格执行了 8 个任务。**红-绿循环真实抓到的东西**(不是仪式,是产出差异):

1. **Task 6 有一个测试"通过得莫名其妙"**:`test_validate_missing_schema_file_exits_two` 在命令还
   不存在时就绿了——因为 click 对未知命令也返回 exit 2。TDD 的 "Test passes? You're testing
   existing behavior. Fix test." 这条直接命中。我给它加了 `"Could not read schema file" in output`,
   它才变红。**如果我先写实现后补测试,这个假测试会永远留在仓库里**,而且看起来完全合理。
2. **Task 4 我自己违反了 Iron Law**:写 render.ts 时顺手加了一个"只有表级错误、没有行违规时不渲染
   筛选栏"的分支,没有任何测试覆盖。发现后我按技能要求把代码删掉、补测试、看它红、再恢复。补的
   测试暴露的场景恰好就是 Task 6 里 `test_validate_missing_required_column_is_reported_once`
   会生成的那种报告——真实路径,不是假想。
3. **计划的两个缺口是实现时才炸的**,说明计划再细也不能替代执行:
   - 新增顶层 `frontend/` 目录**打断了 setuptools 的 flat-layout 自动发现**,整个包直接构建失败。
     修法是显式声明 `packages = ["sqlite_utils"]`。这是"给存量项目加东西"独有的伤害:我加的是一个
     和 Python 无关的目录,却把打包搞挂了。
   - `tsc` 报 `NodeListOf<Element>` 不可迭代,要在 tsconfig 的 lib 里加 `DOM.Iterable`。
   - `ty`(仓库 lint 链里的第二个类型检查器,我一开始差点忘了跑)抓到 `db[table]` 返回
     `Table | View`,而 `validate_table` 要 `Table`。改用 `db.table(table)`。**mypy 没报这个,ty 报了**
     ——存量仓库的 lint 链有它自己的脾气,照抄 Justfile 才安全。

## 阶段 5 — systematic-debugging(计划外,但技能库要求)

端到端演示后我加跑了一步"把生成的 HTML 真正塞进 jsdom 跑一遍",结果 `querySelector("h1")` 返回
null——**报告看起来根本没渲染**。

这是整个任务里 superpowers 价值最大的一刻。我的第一反应是"main.ts 的 DOMContentLoaded 分支有问题,
改成直接调用 boot() 就好了"——这是一个看似合理、实则会把正确代码改错的修复。systematic-debugging
的 Iron Law(NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST)拦住了我,我按 Phase 1 第 4 条
"在每个组件边界加诊断"做了一遍:shell 在不在 → 数据能不能 parse → bundle 有没有执行。

证据是 `readyState: loading`。**根因在我的验证脚本里,不在产品里**:jsdom 构造函数返回时文档还没
解析完,我读得太早。等 `load` 事件后一切正常(5 条违规、期望/实际、筛选、展开全对)。

如果我按第一反应"修"了 main.ts,我会**引入**一个真 bug(在真实浏览器里 boot 可能在 #app 存在前
执行),而且还会以为自己修好了。这一次,流程纪律的收益是直接可量化的:避免了一次错误修改。

Phase 4 要求"修复前必须有失败测试"。根因既然在一次性脚本里,没有产品代码可修——但调查暴露了一个
**真实的覆盖空洞**:vitest 只测了 `renderReport()`,从没测过 main.ts 的 `#report-data → #app` 接线,
而那正是集成缝隙。我补了 `main.test.ts`。它一写就绿,所以我按 writing-good-tests 的
"说出哪个production 改动会让它失败"自证:临时把 `getElementById("report-data")` 改成错的 id,测试
立刻红。**这一步把"新写的测试是不是废测试"从信仰变成了证据。**

**这个阶段对存量代码库的启示**:绿地项目里我写的每一行都是自己的,出问题第一嫌疑人就是新代码;
存量项目里"哪一层坏了"的可能性空间大得多(仓库的构建、仓库的 lint、我的代码、我的验证脚本),
边界诊断这套办法的性价比因此明显更高。

## 阶段 6 — requesting-code-review

**适配声明**:技能要求派发独立 reviewer subagent,并且明确警告"别自己 review diff,那会烧掉你
coordinator 的上下文"。我只能串行扮演 Senior Code Reviewer,拿 `git diff main..HEAD` 从头读。
这是第四处偏离,而且是**代价最实在的一处**:我评审的是我自己两小时前写的代码,"新鲜眼睛"是假的,
我知道每一行的意图,因此天然倾向于认为它合理。

即便如此,这一步抓到了两个真问题,而且都是**只有对照仓库既有代码才看得出来的**:

1. **Critical:`_iter_rows` 用了 `cursor.fetchall()`**。需求白纸黑字写着"最大的表百万行级别",
   而 fetchall 会把整张表先物化成 Python list。我在写的时候完全没意识到——因为所有测试都是 20 行的
   小表,**测试全绿并不能暴露这个**。发现它的方式是评审时去读 `db.py:2009` 的 `rows_where`,
   看到仓库自己是 `for row in cursor:` 流式的。
2. **Important:手搓 `"[{}]".format(name)` 做标识符引用**,而仓库在 `db.py:79` 就导出了
   `quote_identifier()`(会把内嵌引号 double 掉)。表名带 `]` 直接生成非法 SQL。

**这是整个任务里"存量代码库 vs 绿地"差异最大的一处。**绿地项目里 code review 主要看"这代码本身好不好";
存量项目里最有价值的评审问题是**"仓库已经怎么做了,你为什么不一样"**。这两个 bug 都不是"写得丑",
而是"没跟仓库的既有解法对齐",绿地项目根本不会产生这类缺陷。superpowers 的评审模板里
"Integrates cleanly with surrounding code?" 这一条,在存量仓库上的权重应该比它现在的排序高得多。

修复照 TDD 走:两个测试先红(第一版 streaming 测试还太宽,把 PRAGMA 内省也禁了 fetchall,收窄后
才是诚实的),修完绿,然后**把 `for row in cursor:` 改回 `fetchall()` 验证测试真的会红**,确认不是
废测试。

## 阶段 7 — verification-before-completion

Iron Law:没有当场跑出来的证据就不许说"完成"。我把验收口径逐条变成命令跑了一遍,并且**把新旧测试
分开跑**——这一步意外有价值:旧测试文件从基线 1371 变成了 1373,乍看像是"改动了老测试"。查下来是
仓库自己的 `test_docs.py` 对 `cli.cli.commands` 做参数化,新命令自动多出 2 个用例,
`tests/test_docs.py` 文件本身 `git diff` 为空。**如果我只报"1417 passed",这个 +2 就被糊过去了;
分开跑并解释清楚,才是真的"零回归"。**

还额外做了一个技能没要求、但我认为该做的验证:`uv build --wheel` → 干净 venv 安装 → 在没有
`frontend/`、没有 node 的环境里跑 CLI 生成报告 → 用 jsdom 确认报告真的渲染、筛选、排序都工作。
这条链路正是老周"Python 只负责打包产物"和 Iris"拖进浏览器就能用"两个要求的交汇点,不端到端验一次
就只是"我觉得能行"。

## 阶段 8 — finishing-a-development-branch

按技能:全量测试绿 → 检测环境(普通 checkout,无 worktree 需清理)→ 确认 base 是 main → **呈现
三选项菜单并等待人来决定**。技能的 rationalization 表里专门有一条 "They obviously want it merged"
→ "Integration is your human partner's decision."。加上任务明令"绝不 push",我选择保留分支不动,
把菜单交回给人。

---

# 三维打分与诚实总结

## 1. 思维清晰度增益:**8/10**

真正提升清晰度的是**少数几个强制动作**,不是"写文档"这件事本身:

- brainstorming 的"提 2-3 个方案讲权衡"逼出了"为什么不自己实现 JSON Schema 子集"的真实理由
  (部分实现会对没检查的关键字谎报 clean),这句话我本来只有模糊直觉。
- "先探索既有代码"作为 checklist 必做项,挖出了四条不读就必踩的坑(cli.py 免 mypy、CI 无 node、
  test_docs 强制文档、cog --check),其中两条**直接改变了架构**。
- systematic-debugging 的边界诊断,把"报告没渲染"从一个我几乎要错误修复的产品 bug,变成了
  "我的验证脚本读早了"。
- code review 的"和周边代码是否一致",抓到 fetchall 和引用引号。

扣 2 分:writing-plans 要求"假设执行者零上下文",而执行者就是我本人,那部分文字对清晰度零贡献。

## 2. 流程开销负担:**6/10**(6 = 负担明显但可接受)

最重的是 writing-plans。计划文档比最终新增的产品代码还长,而且其中很大一部分(完整贴出 render.ts、
把每个测试的代码写全)在我这种"自己写计划自己执行"的模式下是纯重复——那些代码我写第二遍时几乎是
复制粘贴。**这个开销是为 subagent 派发设计的,我这里享受不到收益却付全额成本。**

其次是所有"派发 subagent"环节退化成自我扮演:code review 尤其吃亏,自我评审拿不到真正的新鲜眼睛,
我很清楚自己对某些设计有偏袒(比如我到现在也不确定"把逻辑放 validate.py 而不是 Table.validate()"
是不是最好的选择,一个独立 reviewer 更可能挑战它)。

不重的部分:REFLECTION、spec 自审、TDD 循环本身。TDD 的"开销"是错觉——红-绿循环里抓到的假测试
和 Iron Law 违规,补救成本远低于事后发现。

## 3. 对最终质量贡献:**9/10**

可以点名的、若无流程就不会存在的质量差异:

| 若跳过流程 | 实际结果 |
|---|---|
| `--limit` 一个参数混用 | Iris 修订成 `--max-violations` + `--scan-limit` 两个 |
| 逻辑写进 cli.py,"过 mypy"变空话 | 独立 validate.py,真受检 |
| 前端产物不入库,CI 直接挂 | 产物入库 + package-data + wheel 验证 |
| `fetchall()` 百万行炸内存 | 流式,且有会红的回归测试 |
| 表名带 `]` 生成非法 SQL | 用仓库的 quote_identifier |
| 假测试(exit 2 蒙对)长期留存 | 加断言收紧 |
| 错误"修复"正确的 main.ts | 边界诊断定位到验证脚本 |
| 报告 boot 路径无测试 | main.test.ts,并自证会红 |

扣 1 分:这些收益里有几项(mypy 豁免、CI 无 node)本质来自"认真读仓库",一个足够有经验的人不套
superpowers 也可能读到;流程的作用是**把"可能读到"变成"一定读到"**。

## 诚实的负面感受

1. **最烦的是 writing-plans 的体量。**中途我明确想跳过,理由("我就是执行者,写给谁看?")在我这个
   串行模式下其实是成立的。它救我的是两个 checklist(No Placeholders、Type consistency),不是
   计划正文。如果只能保留一半,我会保留自审、砍掉"零上下文说明"。
2. **自我扮演 reviewer 让 requesting-code-review 打了对折。**它仍然有产出(两个真 bug),但我知道
   那是因为我强迫自己去读 db.py 做对照,而不是因为"新鲜眼睛"。这个技能的价值高度依赖 subagent,
   没有 subagent 时应该明说"改为对照既有代码做 checklist 式自查",而不是假装在评审。
3. **一次问全 vs 一次一个问题的冲突。**我按任务书一次问了 9 个,失去了"根据上一个答案调整下一个"的
   能力。Iris 那条修订(拆两个参数)如果是对话式的,我可能会顺势追问"那快速抽查要不要也能限制
   明细条数",现在只能自己定。
4. **仪式感最强、收益最低的一步是 spec 和 plan 的"呈现给用户逐节确认"。**我的通道无法真做,只能
   记录偏离。
5. 一个反直觉的发现:**流程在"我以为我懂了"的时刻最值钱**。渲染失败那次,我的第一反应百分之百是
   错的,而且我当时很自信。TDD 的"看着它红"和 debugging 的"先找根因"都是同一件事——
   **强制在自信和行动之间插入一次证据检查**。这是我从这次任务里唯一真正想保留到默认习惯里的东西。

## 存量代码库 vs 绿地:总结

**更有用的纪律**
- *Explore project context*(brainstorming checklist #1):绿地是空操作,存量是信息密度最高的一步。
- *Global Constraints*(writing-plans):在存量仓库里被填的是"仓库既有事实"(基线数字、免检模块、
  CI 能力、文档强制),条条有约束力;绿地里往往退化成技术偏好清单。
- *Integrates cleanly with surrounding code*(code review):存量项目最高频的缺陷来源就是
  "没跟既有解法对齐",这一条应该排在评审清单前列。
- *systematic-debugging 的边界诊断*:存量项目里"哪一层坏了"的可能性空间大得多(仓库构建/仓库 lint/
  新代码/验证脚本),分层取证的性价比更高。

**更碍事的纪律**
- *writing-plans 的"假设零上下文"*:存量仓库的真正上下文在代码里,不在计划文档里;把它复述一遍
  既冗长又容易过时。更该写的是"这个仓库有哪些坑",而不是"这个函数怎么写"。
- *TDD 的 "Delete means delete"*:对新代码完全正确;但存量仓库里我改动的是既有文件(cli.py、
  pyproject.toml、docs),"删掉重来"的粒度不好界定,好在这次没真正撞上。
- *worktree 隔离*:对存量仓库其实更需要(避免污染),但和"只在仓库目录内操作"的外部约束冲突,
  退化成了普通分支。
