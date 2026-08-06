# S6 需求档案 — 全栈跨前后端改动（FastAPI + React/TS）（裁判专用）

## 目标代码库（锁定）
- **fastapi/full-stack-fastapi-template**，tag **0.10.0**（commit `d40de23`）。FastAPI(Python) 后端 + React + TypeScript + TanStack Router 前端，**OpenAPI 自动生成的 TS client**（`frontend/src/client/*.gen.ts`）。
- 规模：后端 ~1.6k 行、前端 ~8.4k 行 TS/TSX；跨栈复杂度高（两语言 + 生成客户端 + 认证 + CRUD + alembic 迁移 + playwright e2e）。
- 现有实体：`User`、`Item`（`ItemBase`: title/description）。Items 是 demo CRUD 资源，前端有 `frontend/src/routes/_layout/items.tsx` 页面。
- **前后端契约链**：后端 SQLModel schema → OpenAPI → `npm run generate-client`(openapi-ts) 重生成 `types.gen.ts`/`schemas.gen.ts`/`sdk.gen.ts` → 前端用生成的 typed client。**改后端 schema 不重生成 client、不同步前端 → `tsc` build 会报错**（自动契约检查）。
- **绿基线（裁判亲手焊死）**——改动必须守住：
  - 后端：`cd backend && pytest` = **60 passed**（Python 3.13 + 本地 postgres，env 见 .env，各副本 DB=app_a/b/c，POSTGRES_PASSWORD=changethis）。
  - 前端：`cd frontend && npm run build`（= `tsc` 类型检查 + vite build）**通过**、出 dist。
- 三副本 round6/{A,B,C}（各自 DB、backend venv[python3.13]、frontend node_modules），分支 round6-feature。

## 种子输入（三家一字不差的起始指令）
「我们这个全栈应用（FastAPI 后端 + React/TS 前端）现在的 Items 只有标题和描述。产品上我想让用户能给每个 item **设一个优先级**（比如低/中/高），创建和编辑时能选、列表里能看到、最好还能按它排一下。这是个贯穿前后端的改动——后端要存、API 要传、前端要能选能显示。你把它端到端做掉，别把现有的东西改坏（后端测试、前端构建都得一直是绿的），前后端的类型/契约要对得上。告诉我你做了什么、怎么保证前后端一致、怎么验证的。」

## 用户画像（我扮演的角色）
- 这个全栈应用的**产品/技术负责人**。懂产品、懂全栈大概，但**不替你决定具体实现**（字段类型用 enum 还是 int、前端用什么组件你定）。只定"要什么能力、什么算完成、不能破坏什么"。
- 最在乎：**前后端契约/类型对得上**（生成的 client 要跟后端 schema 一致）、**不破坏现有**（60 后端测试 + 前端 build 一直绿）。
- 最怕：**契约漂移**（后端改了、前端没跟上、类型对不上、或运行时字段对不上）。

## 必须有（Must-have / 硬约束）
1. **端到端贯通**：优先级字段要真的贯穿——后端 `Item` model（含 Create/Update/Public schema）→ alembic 迁移 → CRUD/API 读写 → **重新生成 TS client**（用项目的 `npm run generate-client`/openapi-ts，不许手改 `*.gen.ts`）→ 前端创建/编辑表单能选、列表能显示。
2. **前后端契约一致**：改完后端 schema 必须重生成 client，前端 `tsc` 类型检查（`npm run build`）必须通过——这是契约对齐的硬证据。不许手改生成文件来"糊上"。
3. **迁移安全**：加字段要有 alembic 迁移，DB 能干净 upgrade；对已有行安全（给默认值或可空），不破坏现有 60 测试。
4. **零破坏**：现有后端 60 测试保持绿、现有前端 build 保持绿、现有功能（登录/用户/items CRUD）不回归。
5. **两端都测**：后端加针对新字段的测试（创建/更新/读取带优先级）；前端至少 build+类型过，能加 e2e/组件测试更好。
6. **不弱化/不删现有测试**充数骗绿。

## 加分（Nice-to-have）
- 后端字段用有意义的类型（enum 三档 low/medium/high，比 magic int 好），OpenAPI 里体现为枚举、前端生成 union 类型。
- 列表可按优先级排序（种子提到"最好还能排一下"）。
- 前端 e2e（playwright）覆盖"设优先级→保存→列表可见"。
- 迁移 downgrade 也写好（可回滚）。
- 说明里画清"改了哪些层、契约怎么对齐、怎么验证"。

## 明确不做（Out of scope，被问到才说）
- 不做与优先级无关的重构/改架构。
- 不改认证/用户体系。
- 不升级框架大版本/换构建工具/换状态管理。
- 不做优先级之外的新字段/新功能。
- 不碰 CI/部署配置（除非新测试要接入护栏，那种小改可以）。

## 预置答案（被问到才答，没问不说）
- 字段类型（enum vs int vs string）：「你定，但我倾向有意义的枚举（low/medium/high 三档）——OpenAPI 里是枚举、前端能生成成 union 类型、契约最清晰。用别的你说清理由。」
- 默认值：「已有的 item 没有优先级，给个合理默认（比如 medium）或可空，别让迁移把老数据搞坏、别让现有测试红。」
- 前端组件：「你定，跟现有 items 表单/列表风格一致就行（项目用 Chakra + react-hook-form + TanStack）。」
- 要不要排序：「有更好（种子说了'最好还能排'），但别为排序把范围搞大——先把'能存能选能显示'端到端做扎实，排序是加分。」
- 契约怎么对齐：「必须用项目自己的 `npm run generate-client`（openapi-ts）重生成 client，不许手改 `*.gen.ts`。改完前端 `npm run build`（tsc）必须过——这就是我要的契约对齐证据。」
- 迁移：「加 alembic 迁移，能 upgrade（downgrade 也写上更好），对老数据安全。」
- 测什么：「后端加优先级相关的 API 测试；前端至少 build+类型过，能加 e2e 更好。别删现有测试、别改松断言。」
- 怎么算 done：「后端 60 测试仍绿 + 新测试过；前端 `npm run build` 绿（tsc 类型对齐）；client 是重生成的不是手改的；创建/编辑能选优先级、列表能看到；我能看懂你改了哪些层、契约怎么对齐、怎么验证。」
- 破坏红线：「现有的登录/用户/items 都不能回归；60 后端测试 + 前端 build 一直绿是硬线。」

## 验收标准（打分依据，硬性；裁判亲手复验）
A1 **后端 60 测试仍全绿** + 新增的优先级相关后端测试通过（裁判跑 `pytest`）。
A2 **alembic 迁移**存在且能干净 `upgrade head`；对已有数据安全（默认/可空）；裁判跑迁移不报错。
A3 **字段贯穿后端**：`Item` 的 model/Create/Update/Public schema 都含优先级；API 创建/更新/读取真的读写它（裁判打 API 验证）。
A4 **TS client 是重生成的**：`*.gen.ts` 反映新字段，且是 openapi-ts 生成的（非手改——裁判看 diff 是否只有生成器风格的改动 + 后端 schema 一致）。
A5 **前端 `npm run build`（tsc + vite）通过**：类型检查过 = 前后端契约对齐的硬证据（裁判亲手 build）。
A6 **前端 UI 真用了字段**：创建/编辑表单能选优先级、列表/详情能显示（裁判看代码 + 能 build）。
A7 **零破坏**：现有后端测试、前端 build、现有功能不回归（裁判重跑基线）。
A8 **两端测试**：后端新测试真断言优先级行为；前端至少 build+类型过（e2e 加分）；无删/改松现有测试。
A9 附**清晰跨栈改动说明**：改了哪些层、契约怎么对齐、怎么验证。
A10 计划定稿后实现阶段**零人工澄清**（Loop 适配硬指标）。

## 关键陷阱区（"思维补全"评分着眼点）
- **契约漂移是头号风险**：改了后端 schema 却忘了重生成 client、或手改 `*.gen.ts` 糊上去——前端类型会跟后端脱节。好工作流会用 `generate-client` 重生成、并靠 `tsc` build 当契约守门员。
- **迁移别漏/别不安全**：只改 model 不写迁移，DB 和测试会炸；加非空无默认字段会把老数据/现有测试搞坏——要默认或可空。
- **两端都要动**：只改后端不改前端 = 半截；只改前端不改后端 = 假的。真跨栈要 model→migration→API→client→UI→两端测试全链。
- **别手改生成文件**：`*.gen.ts` 是生成产物，手改=契约造假，下次 regenerate 就冲掉。
- **范围纪律**：别借机重构架构、别把排序/过滤/批量等一堆加进来——先把"能存能选能显示"这条线端到端做扎实。
- **枚举跨栈一致**：后端 Enum → OpenAPI enum → 前端 union 类型，值要一一对上（大小写/命名）。

## 流程裁决
- 计划阶段软上限 90 分钟；实现阶段总硬上限 4 小时/家，超时按现状记。
- 面试轮数软上限 ~8 来回；答案只出本档案；新问题先裁决落档再答，各家同问一字不差同答；没问的不多说。

## 工作流程线（每家；沿用前五轮）
- A (matt): grilling(+codebase-design) → to-spec → to-tickets → [Sonnet, implement/tdd]
- B (裸 brainstorm): 自然对话 → 计划 → [Sonnet, 无 skill]
- C (superpowers): brainstorming → writing-plans → [Sonnet executing-plans]

## 新增裁决记录（跑动中追加，全家共享同一答案）
- [06:20 UTC, A第1轮3问] A grounding扎实(读通契约链/现有Select+Badge组件/DataTable无sorted model/现有测试只断言title-desc)。标准答案（同题任何家再问一字不差复用）：
  1. 优先级档位/粒度：「三档就够 v1——`low`/`medium`/`high`（存小写，UI 显示 Low/Medium/High）。锁死这个闭集，后端 Enum、OpenAPI enum、前端 union 一一对上。以后要加'urgent'再走一遍 model+迁移+regen+UI，本期先三档。」
  2. 必填/默认/回填：「优先级**始终有值、默认 medium**——创建表单预选 Medium（用户可改但不会见空态），ItemCreate.priority 服务端 optional-默认-medium，迁移用 server_default 把已有行回填成 medium。这样 ItemPublic.priority 非空（干净 union，不带 `| null`）。就按你推荐的。」
  3. 排序是否在本期/在哪跑：「排序是'最好还能'的加分项——先把'能存能选能显示'这条核心端到端做扎实。你要在本期带上，就用**客户端排序（选项 A，让 DataTable 表头可排、只排当前页）**这个低风险的额外项，不动 API/契约、不加迁移风险；服务端排序（选项 B，跨页真排序）**本期延后**除非我特别要。high 默认排在最上面可以。**但一条硬线：排序不许危及核心或改坏共享的 DataTable/现有 build；有风险就砍掉排序、只交核心。**」（注：排序机制各家自定，维护者立场统一=核心优先/最小低风险/high-first/有风险就砍。C给的是服务端always-sort，同样接受。）
- [06:25 UTC, B第1轮3问] B独立洞察: 选IntEnum(1/2/3)非str enum,理由=服务端ORDER BY排序正确(str enum按字母排high<low<medium错,需CASE)。**A/C都选str enum没想到这个排序×枚举交互——C的服务端str-enum always-sort有字母序bug隐患(除非加CASE/映射)。B思维补全亮点,记分。** 档案立场"倾向string,用别的说清理由",B说清了故接受。标准答案：
  - B-Q1 档位/默认/回填：同上——三档low/med/high(B用IntEnum 1/2/3也行),默认medium,迁移server_default回填medium。
  - B-Q2 排序语义：「排序最小、high-first、核心优先、有风险就砍。你的IntEnum让服务端(a)默认按优先级排(high→low,created_at兜底)很干净——就用(a),别做(c)双选。」
  - B-Q3 验收面：「list+表单即可(无独立detail页),优先级创建可设/编辑可改/列表可见/按Q2排序。本期不做过滤。确认只list+forms。」
  - B的IntEnum选择接受(说清了排序理由);同时A/C的str enum也接受(档案默认倾向)。各家自证,不回溯提点。
