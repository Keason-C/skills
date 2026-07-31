<!--
SYNC IMPACT REPORT
==================
Version change: (template, unversioned) → 1.0.0
Bump rationale: MAJOR-equivalent initial ratification. First concrete constitution replacing
the placeholder template; all principles newly defined.

Modified principles:
  [PRINCIPLE_1_NAME] → I. 有据可查,拒绝编造 (Grounded or Silent) — NON-NEGOTIABLE
  [PRINCIPLE_2_NAME] → II. 权限先于内容 (Authorization Precedes Content) — NON-NEGOTIABLE
  [PRINCIPLE_3_NAME] → III. 知识落在库里,不落在人手里 (Knowledge Lives in the Corpus)
  [PRINCIPLE_4_NAME] → IV. 模型在驱动接口之后 (Model Behind a Driver Boundary) — NON-NEGOTIABLE
  [PRINCIPLE_5_NAME] → V. 够用就好,不过度设计 (Deliberate Simplicity)
  (added)            → VI. 内核与通道分离 (Channel-Agnostic Core)

Added sections:
  [SECTION_2_NAME]  → 技术约束与安全要求 (Technical Constraints & Security Requirements)
  [SECTION_3_NAME]  → 开发流程与质量门禁 (Development Workflow & Quality Gates)

Removed sections: none

Deferred / TODO items: none. RATIFICATION_DATE set to today (greenfield project, adopted at
project inception).

---
AMENDMENT 1.0.0 → 1.0.1 (2026-07-31, PATCH)
Trigger: /speckit-analyze finding D1 (HIGH) + D2 (MEDIUM) — 宪法文本落后于 clarify 阶段
的需求方答复,未构成设计违规,但只读宪法的实现者会据此建出错误的权限模型。
Change (§技术约束与安全要求 · 敏感度模型):
  - "仅品类经理及以上可见" → "仅**负责该品类的**品类经理及采购负责人可见"
  - 增补:密级 MUST 由存放位置判定,MUST NOT 由内容关键词推断;报价/成本/谈判策略的
    列举降格为操作指引,不再读起来像判密规则。
Bump rationale: PATCH —— 澄清既有约束的表述,未新增或删除任何原则,不改变已通过的
Constitution Check 结论。
Affected artifacts: 无需改动 spec/plan/tasks(它们本来就是正确的一方)。
-->

# 采购知识问答机器人 (Procurement Commodity Know-How Bot) Constitution

本宪法定义本项目不可协商的工程与产品底线。任何规格、计划、任务与实现都必须与之一致;
冲突时以本文件为准。

## Core Principles

### I. 有据可查,拒绝编造 (Grounded or Silent) — NON-NEGOTIABLE

系统输出的每一条事实性断言 MUST 可回溯到语料库中某个具体文档的具体位置(文件名 + 片段标识)。

- 回答 MUST 附带来源引用;无来源的断言视为缺陷,不是风格问题。
- 当检索到的材料不足以支撑答案时,系统 MUST 明确回答"不知道 / 资料里没有",
  并 MUST 生成一条人工转交记录(escalation),而不是给出低置信度的猜测。
- "看起来合理但无出处"的回答 MUST 被判定为比"我不知道"更严重的失败。
- 每一条前述规则 MUST 有对应的自动化测试;不可测的"努力做到"不算数。

**理由**:采购决策会引用这些答案去谈判、去下单。一次编造的规格或流程,代价远高于一百次
"我不知道"。用户原话即为"要靠谱一点,别瞎编乱答"。

### II. 权限先于内容 (Authorization Precedes Content) — NON-NEGOTIABLE

访问控制 MUST 在内容进入模型上下文之前生效,而不是靠提示词让模型"自觉不说"。

- 每个文档(或文档片段)MUST 携带敏感度标签;每个提问者 MUST 携带角色。
- 语料的筛选 MUST 在组装 prompt 之前完成:无权访问的内容绝不进入上下文窗口。
  依赖模型自我审查的设计 MUST 被拒绝。
- 报价、成本、谈判策略等受限内容被过滤后,系统 MUST 告知用户"该问题涉及受限信息,
  你的权限不足",而不是假装该信息不存在,也不得泄露被过滤内容的任何细节。
- 权限相关的行为 MUST 有针对性的负向测试(越权提问必须被拒绝)。

**理由**:提示词注入可以绕过"请不要透露",但绕不过"数据根本没被读进来"。

### III. 知识落在库里,不落在人手里 (Knowledge Lives in the Corpus)

系统的价值在于让组织知识独立于个人存续,因此语料库 MUST 是唯一真相来源。

- 任何领域知识(品类归属、供应商、流程、规格)MUST NOT 硬编码在代码或提示词里;
  它们 MUST 来自可被非技术同事直接编辑的文档文件。
- 语料库 MUST 支持增量新增文档而无需改代码、无需重新构建索引服务。
- 无法解析的文档 MUST 被显式记录并可被人看见(而不是静默丢弃),否则知识会悄悄丢失。
- 每次转人工 MUST 被记录为"知识缺口",作为语料补全的输入。

**理由**:领导要的不是一个聊天玩具,是交接不断档。静默丢文档 = 知识又回到了人脑里。

### IV. 模型在驱动接口之后 (Model Behind a Driver Boundary) — NON-NEGOTIABLE

所有大模型调用 MUST 收敛到一个显式的驱动(driver)接口后面。

- 业务逻辑 MUST NOT 直接引用任何厂商 SDK;它只依赖驱动抽象。
- 测试套件 MUST 全部离线可跑:默认驱动为确定性 mock/fake,不需要网络、不需要 API key。
- 真实厂商驱动 MAY 被编写,但 MUST NOT 在自动化测试中被执行。
- 若测试需要网络或密钥才能通过,该测试 MUST 被判定为不合格并重写。

**理由**:不确定的依赖会让"回归测试"退化成"运气测试";而采购部的 IT 环境未必随时有外网。

### V. 够用就好,不过度设计 (Deliberate Simplicity)

用户明确拒绝向量数据库方案;本项目 MUST 保持与几十份文档的量级相称的复杂度。

- MUST NOT 引入向量数据库、embedding 服务或独立的检索基础设施。
- 检索 MUST 使用可解释的确定性方法(关键词/词元匹配、元数据过滤、结构化打分),
  其结果 MUST 可被人复现和解释。
- 新增运行时依赖 MUST 有书面理由;能用标准库解决的 MUST NOT 引入第三方库。
- 复杂度预算被突破时,MUST 先修改本宪法,再写代码。

**理由**:"太重了"是用户的原话。几十份文档的问题不该用几万份文档的架构去解。

### VI. 内核与通道分离 (Channel-Agnostic Core)

问答内核 MUST 不感知它被谁调用。

- 核心 API MUST 是纯函数式的请求→响应形态,不依赖终端、HTTP 或任何 IM 平台。
- CLI MUST 是内核之上的一层薄适配器;后续企业微信适配器 MUST 能在不修改内核的前提下接入。
- 用户身份与角色 MUST 作为参数传入内核,MUST NOT 由内核自行从环境中读取。

**理由**:用户已经说了"后面可能要接企业微信"。现在留好缝,比将来拆房子便宜。

## 技术约束与安全要求 (Technical Constraints & Security Requirements)

- **语言与运行时**:Python 3.11+,使用 `uv` 管理依赖与虚拟环境。
- **交付形态**:阶段一为命令行工具;内核以可导入的 Python 包形式提供。
- **文档格式**:MUST 支持 `.md`/`.txt`(必选)、`.docx`、`.pdf`、`.xlsx`;
  未知或损坏格式 MUST 被降级为"无法解析"并记录,MUST NOT 使整批导入失败。
- **敏感度模型**:至少两级——`internal`(全体采购员可见)与 `restricted`
  (仅**负责该品类的**品类经理及采购负责人可见)。
  密级 MUST 由**存放位置**判定(约定的保密目录),MUST NOT 由内容关键词自动推断;
  下列内容属于应当被放入保密目录的资料,此列举是操作指引而非判密规则:
  报价、成本、谈判策略。
- **审计**:每次问答 MUST 记录提问者、角色、命中的文档、是否发生权限过滤、是否转人工。
  审计记录 MUST NOT 包含被过滤掉的受限内容正文。
- **无外网依赖的测试**:测试 MUST NOT 发起网络请求。
- **不做的事**:不做向量库;不做用户密码体系(角色由调用方注入);不做多租户。

## 开发流程与质量门禁 (Development Workflow & Quality Gates)

- 本项目 MUST 遵循 Spec Kit 流程:constitution → specify → clarify → plan → tasks →
  analyze → implement,MUST NOT 跳步或提前写实现代码。
- 面向业务的不确定性 MUST 通过 clarify 环节向需求方澄清;纯技术决策由实现方自行决定
  并 MUST 记录在 plan 的技术决策表中。
- 质量门禁(全部 MUST 通过方可宣布完成):
  1. `pytest` 全绿,且在断网环境下可重复运行。
  2. 存在针对以下场景的测试:有据可答、无据转人工、越权被拒、格式不可解析被记录。
  3. README 提供可照做的演示路径(含示例语料与示例提问)。
- 任何违反本宪法的实现 MUST 在合并前修正,或先走宪法修订流程。

## Governance

- 本宪法优先于其他一切实践约定与个人偏好。
- **修订流程**:提出修改 → 说明受影响的规格/计划/任务 → 更新版本号与 Sync Impact Report
  → 同步修改受影响产物。修订 MUST 在同一次变更中完成,MUST NOT 留下悬空引用。
- **版本策略**(语义化版本):
  - MAJOR:删除或不兼容地重定义某条原则。
  - MINOR:新增原则或实质性扩展某条原则的约束。
  - PATCH:措辞澄清、错别字、非语义性调整。
- **合规审查**:每次进入 `/speckit-analyze` 时 MUST 逐条核对本宪法;
  发现的违规按 CRITICAL 级别处理,MUST 在 implement 之前解决。
- 复杂度必须被论证;"以后可能用得上"不构成引入依赖的理由。

**Version**: 1.0.1 | **Ratified**: 2026-07-31 | **Last Amended**: 2026-07-31
