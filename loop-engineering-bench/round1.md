# Round 1 — S1 生产级认证服务

## 档案摘要
- 种子输入（三家一字不差）：生产级 auth 服务，邮箱+密码，SSO 有呼声，公网级安全，会话+密码重置，服务间查登录态/权限，拒绝玩具 demo。
- 关键预置裁决：SSO 本期不做只留架构缝；注册限公司邮箱域+邮箱验证；introspection 走 per-service API key 且权限查询须实时准确；RBAC 三角色起步；栈不指定（Python/TS 皆可，选手自选并说明理由）；生产 Postgres；邮件抽象（dev 落日志）；容器化交付 Dockerfile+文档。
- 验收标准 A1–A10 见 /workspace/bench/dossiers/S1.md（含无人值守硬指标 A10：spec 定稿后实现阶段零人工澄清）。
- 上限：规划软上限 90min/约8轮来回；实现硬上限 4h/家。

## 时间线与插手记录
- 15:25 UTC 环境初始化；A 资产=本地 matt skills，C 资产=obra/superpowers@shallow-clone，B=无 skill 对照组。
- ~15:45 UTC 三家 Opus 规划 agent 并行启动，输入为同一段种子原话。
- 15:45–16:10 规划面试期：A 三轮 30 问（附推荐答案+代价说明）；B 两批 22 问（附默认建议）；C 一次一问共 9 问 + 设计文档 3 段确认 + design.md 批准（共 13 次介入）。全部按档案作答，同题同答。
- ~16:05 A 规划完成（commit 5912d02：glossary + 8 ADR + spec(64 用户故事) + 12 tickets）。A 自我推翻初稿中"5 分钟访问令牌"设计，改为纯回源解析以满足"停用即时生效"（ADR 0008）。
- ~16:08 B 规划完成（commit 1ea0698：spec(19 条决策日志) + 15 tickets，TS 栈）。
- ~16:10 A-T01、B-T01 两个 Sonnet 实现 agent 启动（无人值守、禁提问）。
- 16:18 定时检查#1：A 在写平台层（logger/redact/migrations，带测试）；B 在写双端口 app 骨架；C design.md 定稿（a171d96 + 修订 d8826d5）正拆 phase 计划（writing-plans）。三家无卡死。
- （注：16:18 前的日志时间戳系估算，偏快约 1.5h；相对顺序准确，后续以真实时钟为准。）
- 16:38 C 规划完成（commit c588623：design.md + 6 phase/38 任务/285 步实现计划，Python/FastAPI 栈）。writing-plans 过程中 C 反查出 3 个设计缺陷并修正（30/14 天窗口重复、客户端密钥 Argon2 会拖垮内省性能改 SHA-256、citext 扩展依赖去除）。
- 16:32 B-T01 完成（3d4f5a8，17 测试）；16:47 B-T02 完成（dc3e0f6，53 测试，迁移+数据访问层）；16:50 派 B-T03。
- 16:40 C-Phase1 启动（Sonnet, executing-plans）；至 16:50 已按任务提交 3 commit（骨架/配置/数据库夹具）。
- 16:50 定时检查#2：A-T01 仍在写平台层（config/logger/app + 测试，未提交，属正常 TDD 节奏）；B、C 如上。三家无卡死。
- 17:05 A-T01 完成（aea3f23，48 测试，自查中发现并修复 Kysely migrator 的 search_path 缺陷）；派 A-T02。
- 17:07 B-T03 完成（c49dc4c，96 测试，Argon2id+HIBP k-匿名 fail-open+SecLists 字典 fail-closed）；17:15 B-T04 完成（109b35e，134 测试累计，邮件抽象三驱动）；派 B-T05。
- 17:10 C-Phase1 完成（9 commit 至 2276081，87 测试 93.3% 覆盖，修正计划内 5 处缺陷）；派 C-Phase2。
- 17:22 定时检查#3：A 在 T02（0002 迁移+escape-html）；B 在 T05（limiter.ts）；C Phase2 过半（sessions/password_reset 已提交，d6a6ba4）。无卡死。
- 17:27 C-Phase2 完成（818deda，187 测试，修正计划中 2 个 flaky 测试与 4 处小缺陷）；派 C-Phase3。
- 17:31 B-T05 完成（f402613，164 测试，集成测试抓到 timestamptz 精度导致永锁的真实 bug）；17:43 B-T06 完成（5b8e69d，192 测试，审计 100% 覆盖）；派 B-T07。
- 17:48 A-T02 完成（8ceb1c0，126 测试；自查抓到验证 token 写入请求日志的泄漏，加固 URL query 脱敏）；派 A-T03。
- 17:54 定时检查#4：A-T03 起步；B-T07 进行中；C-Phase3 尾声（登出 b6cdfa2 已提交）。无卡死。B 进度 6/15 票领先。
- 17:57 C-Phase3 完成（b6cdfa2，254 测试；抓到计划自相矛盾：登录失败回显邮箱 vs 防枚举字节一致，按安全属性裁决）。
- 18:05 B-T07 完成（ab67547，211 测试；枚举防护做到耗时对齐+字节一致 202；识别并规避 fastify-type-provider-zod 对 zod v4 内部 API 的耦合风险）；派 B-T08。
- 18:19 C-Phase4 完成（21b12b2，327 测试；手动 e2e：撤销会话后下一次 introspect 立即 active:false）；派 C-Phase5。
- 18:25 定时检查#5：A-T03 写 sessions 迁移中；B-T08 写 sessionAuth 中；C-Phase5 过半（admin 鉴权 f673ff6）。无卡死。
- 18:31 B-T08 完成（416469f，263 测试；停用→下一请求 401 有 spy 级回归）；18:40 A-T03 完成（65997e7，170 测试）；18:44 C-Phase5 完成（afa1367，398 测试，bootstrap-admin 真子进程冒烟）。
- 18:47 B-T09 完成（d158cd0，296 测试，重置事务原子性有注入异常回滚测试）；派 B-T10。18:50 派 C-Phase6（最终交付）。18:53 A-T04 完成（bb3b710，210 测试）；派 A-T07。
- 18:56 定时检查#6：A 在 T07（0005 重置令牌迁移）；B 在 T10（serviceAuth）；C Phase6 过半（镜像+Python 示例已交，TS 示例进行中）。无卡死。
- 19:05 **C 全量完成**（最终 HEAD 0d3e4b0；420 测试 93% 覆盖，security+services 96.5%；验收 e2e 含停用即时失效；Docker 镜像实建实跑非 root；runbook/威胁模型/双语接入示例齐全；实现总用时约 2h25m，全程零人工澄清）。
- 19:15 A-T07 完成（a7ff9e2，245 测试）；派 A-T05（角色+bootstrap admin，A 流水线最后一张核心票）。
- 19:22 B-T10 完成（11b4f99，327 测试；诚实报告 P99 压测未达标，根因=沙箱同机 4vCPU 争抢而非代码，DB 单查 0.077ms；建议 T15 独立机复测）；派 B-T11（管理 API）。
- 19:28 定时检查#7：A 在 T05 起步；B 在 T11。C 已完成。
- 19:40 A-T05 完成（4a4b3a6，273 测试，角色赋权+bootstrap admin+应用作用域读路径）；派 A-T06。
- 19:48 A-T06 完成（4fe0d36，287 测试，停用即时失效+外键触发的真实事务回滚测试）；派 A-T08。
- 19:50 定时检查#8：A 完成 8 张核心票（T01-T07,T05,T06），在跑 T08 防暴破；B 在跑 T11 管理 API。C 已完成。真实时钟下三家实现约 16:15 起跑，4h 上限约 20:15-20:30，临近收尾。
- 20:05 B-T11 完成（a6c43b5，361 测试；"最后一个 admin 不可归零"用 roles 表 FOR UPDATE 行锁串行化+并发验证）；派 B-T13。
- 20:15 **B 达上限收尾**（最终 HEAD 7c5ad36，384 测试；create-admin CLI 真实执行并用生成密码登录 role=admin 成功；advisory-lock 分批清理）。B 完成 12/15 票（T01-T11,T13），缺 T12 托管页面、T14 可观测性/OpenAPI/文档、T15 最终 e2e 验收测试。

## 终验证据（裁判亲手跑，非自我报告）

### C（superpowers）— 已完成全部 6 阶段
- **全量测试**：裁判亲手 `uv run pytest` = **420 passed**（干净环境，34.5s）。注：首跑出现 1 例失败 `test_missing_required_setting_is_fatal`，经查是裁判自己 `cp .env.example .env` 导致 pydantic-settings 读到 .env 里的 DATABASE_URL——删除 .env 后通过，属验证环境污染，非代码缺陷。
- **主流程走查**（tests/test_acceptance.py 亲手 verbose 跑通，1 passed）：注册→防枚举文案→未验证登录被拒→token 验证→登录 303→OAuth 授权(state 保留)→换令牌 200→内省 active:true 且零角色→赋权后内省 member→**管理员停用后内省立即精确 `{"active": false}`**（A2 核心，实测）→审计不含密码/令牌。证据：round1/C/tests/test_acceptance.py:88,106,118,135。
- **零缓存即时吊销**（A2）：round1/C/src/authsvc/services/introspection.py:56-80 单次带索引 JOIN，实时校验令牌/会话/用户状态/角色四项，grep 确认无 cache/lru/redis。注释诚实。
- 服务实起：uvicorn 启动 healthz=200。

### B（brainstorm 基线）— 完成 12/15 票
- **全量测试**：裁判亲手 `npx vitest run` = **384 passed / 43 files**（63s）。日志中的 error 是 fail-open 测试故意触发（HIBP 500/SMTP auth fail/network unreachable），断言优雅降级，全过。
- **零缓存即时吊销**：round1/B/src/domain/sessions/service.ts:21-22 注释明示每次查库、repo 无 Redis；stopped→下一请求 401 有 spy 级回归（T08 报告）。
- 缺票：T12 托管页面、T14 OpenAPI/可观测性、T15 最终 e2e 验收测试（达 4h 上限未及）。

### A（matt skills）— 见下（T08 收尾中）

### A（matt skills）— 完成 9 张核心票（T01-T08 + T05），缺 T09 审计查询/T11 生产收尾
- **全量测试**：裁判亲手 `pnpm test` = **346 passed / 52 files**（真实 PG + 每测起临时 redis-server 子进程）。
- **服务实起**：`node dist/main.js` 起服务，公网 3000 healthz=200，内网 3001 readyz=200，内网路由在公网口 404（双入口物理隔离实测）。缺环境变量时拒绝启动并逐项报错（配置校验正确行为）。
- **即时吊销**（A2）：test/deactivate-and-activate.test.ts:139「停用即时生效核心回归」——建会话→解析 authenticated:true→停用→不推进时钟再解析→authenticated:false, reason=user_deactivated（round1/A/test/deactivate-and-activate.test.ts:25,32-33）。resolve-session.ts 零缓存。
- **缺口**：无 README/部署 runbook（T11 未及），无审计查询 API（T09），无接入示例代码。

### 三家安全基线（裁判 grep 扫描）
- 硬编码密钥：三家均无（A 的"命中"是表单字段名与 HTML password 输入框，误报）。
- SQL 注入：三家全参数化。B 的 `SELECT ${SELECT_COLUMNS}` 是硬编码列名常量、值走 $1，安全。C 无 f-string 拼接 SQL。

## 分数表

| 维度（权重） | A matt | B brainstorm | C superpowers |
|---|---|---|---|
| 正确性与验收 23% | 8.5 | 8.0 | 9.5 |
| 健壮性 18% | 9.0 | 8.5 | 9.0 |
| 测试 13% | 9.0 | 9.0 | 9.5 |
| 可维护性 13% | 9.0 | 8.5 | 9.0 |
| 运维就绪 9% | 6.0 | 7.0 | 9.5 |
| Loop 适配 14% | 8.5 | 8.0 | 8.0 |
| 思维补全 10% | 9.5 | 7.5 | 9.0 |
| **加权总分** | **8.60** | **8.15** | **9.09** |

**排名：C（9.09） > A（8.60） > B（8.15）**

关键差异：
- **C** 是唯一交付完整可上线 v1 的（38 任务全完成、Docker 实建实跑、runbook/威胁模型/双语接入示例齐全、端到端验收含即时吊销实测），运维就绪与正确性拉满。
- **A** 需求分析最深（挖出默认角色洞、先有鸡先有蛋、锁定即 DoS、自我推翻 5 分钟令牌设计）、ADR 最好、思维补全最强；但运维就绪翻车（T11 未及，无 README/部署文档/接入示例），且单票最慢没跑完队列。
- **B** 基线扎实、决策日志清晰；但无 skill 约束暴露出扩范围倾向（试图把 SSO/MFA/细粒度权限拉进 v1，靠裁决顶回——无人值守下是风险），思维补全与交付完整度均落后。

## 插手与自主性记录
- 规划阶段提问数：A 30（3 轮）、B 22（2 批）、C 9 + 3 段设计确认 + 1 次 design 批准。
- 实现阶段：三家均零人工澄清（无人值守达成）。全部答问出自 S1 档案，同题同答一字不差；新裁决 30 余条入档案。
- 详见 loop-engineering-bench/interventions.md。

## 代码级发现
（待验证后填写，证据=文件路径+行号）

## 结论（狠话版）
1. **要能上线的东西，选 superpowers（C）。** 它是唯一把"生产级 v1"四个字兑现到底的——别人还在写业务逻辑，它已经把 Docker、runbook、威胁模型、双语接入示例、端到端验收全交了，而且每条运维命令都真跑过。285 步的计划无人值守一次跑通，零澄清。
2. **要把需求想全、少踩坑，用 matt（A）的 grilling 做前端。** 它问出了另外两家没问的致命洞（外部协作者自助注册默认能看所有工具、全新部署没人能赋权、账号锁定被人当武器）。但它太慢、太细，4 小时只跑到一半队列，运维文档整个没做——A 适合当"设计大脑"，不适合单独兜底交付。
3. **B（裸 brainstorm）是对照组，证明了 skill 的价值。** 没有 skill 约束，它一路想把 SSO/MFA/细粒度权限塞进 v1，全靠我按档案顶回去——无人值守下没人顶，它就会超交付、跑偏。代码质量不差，但流程不稳。
