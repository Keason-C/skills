---

description: "Task list for 001-procurement-knowhow-bot"
---

# Tasks: 采购 Commodity Know-How 问答机器人

**Input**: Design documents from `/specs/001-procurement-knowhow-bot/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: **REQUIRED — 非可选。** 依据:宪法《开发流程与质量门禁》第 2 条明确要求四类场景
必须有测试(有据可答 / 无据转人工 / 越权被拒 / 格式不可解析被记录),且 spec 的每个
User Story 都定义了 Independent Test。因此本清单包含测试任务,且测试任务与实现任务同级。

**Organization**: 按 User Story 分组。每个 Story 完成后都是一个可独立演示的增量。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行(不同文件、无未完成依赖)
- **[Story]**: 所属用户故事(US1–US4);Setup / Foundational / Polish 阶段无此标签

## Path Conventions

单项目布局(见 plan.md):源码 `src/procurement_bot/`,测试 `tests/`,
脚本 `scripts/`,演示数据 `demo/`,全部位于仓库根目录下。

---

## Phase 1: Setup(共享基础设施)

**Purpose**: 项目初始化,让 `uv run pytest` 能跑起来(哪怕零个测试)

- [X] T001 创建 `pyproject.toml`:包名 `procurement-bot`,`requires-python = ">=3.11"`,运行时依赖 `python-docx>=1.2`、`pypdf>=6.0`、`openpyxl>=3.1`,`[project.optional-dependencies]` 含 `dev = ["pytest>=8"]` 与 `anthropic = ["anthropic>=0.40"]`,`[project.scripts] pbot = "procurement_bot.cli:main"`,setuptools 的 `package-dir = {"" = "src"}`
- [X] T002 [P] 创建包骨架空文件:`src/procurement_bot/__init__.py`、`src/procurement_bot/ingest/__init__.py`、`src/procurement_bot/llm/__init__.py`、`tests/__init__.py`
- [X] T003 [P] 创建 `.gitignore`(忽略 `.venv/`、`.pbot/`、`__pycache__/`、`demo/corpus/` 中的生成文件)
- [X] T004 创建 `tests/conftest.py` 的**禁网 fixture**:autouse fixture 将 `socket.socket.connect` / `socket.create_connection` 替换为抛 `RuntimeError("测试禁止联网")` 的实现(research.md D-04)。这是宪法原则 IV 的强制手段,必须最先落地

**Checkpoint**: `uv venv && uv pip install -e ".[dev]" && uv run pytest -q` 成功(0 tests)

---

## Phase 2: Foundational(阻塞性前置,所有 Story 都依赖)

**Purpose**: 数据模型、分词打分、md/txt 解析、导入管线、名单加载、驱动接口。
**⚠️ 本阶段完成前,任何 User Story 都无法开始。**

- [X] T005 在 `src/procurement_bot/models.py` 实现全部枚举与 frozen dataclass:`Sensitivity`、`Role`、`AnswerStatus`、`EscalationReason`、`DateConfidence`、`Document`、`Passage`、`RejectedFile`、`Requester`、`Citation`、`ConflictGroup`、`Answer`、`Escalation`、`AuditRecord`、`IngestReport`、`GapReport`。严格遵守 data-model.md;**`Passage` 不得有 `sensitivity` 字段**(INV-P2)
- [X] T006 [P] 在 `src/procurement_bot/errors.py` 定义 `IndexMissingError`、`UnknownRequesterError`、`RosterFormatError`、`CorpusNotFoundError`
- [X] T007 在 `src/procurement_bot/retrieval.py` 实现分词器 `tokenize(text) -> list[str]`:CJK 连续段切字符 bigram(单字成段时取该单字),ASCII 按 `[a-z0-9]+` 切词并小写化(research.md D-01)
- [X] T008 在 `src/procurement_bot/retrieval.py` 实现 `build_idf(passages)` 与 `score(question, passages, idf) -> list[ScoredPassage]`:分数 = Σ 命中词元 IDF × 位置权重(`heading_path` 命中 ×2.0),按长度轻度归一;平分时按 `passage_id` 字典序稳定排序
- [X] T009 [P] 在 `tests/test_retrieval.py` 测试:中文 bigram 切分正确;"电解铜"能命中含"电解铜"的片段;不相关问题得分为 0;**同一输入两次调用结果完全相同**(确定性)
- [X] T010 在 `src/procurement_bot/ingest/parsers.py` 实现 `parse_md`、`parse_txt` 与调度器 `parse(path) -> list[RawSection]`(`RawSection` 含 `heading_path`、`locator`、`text`);未知扩展名抛 `UnsupportedFormatError`
- [X] T011 [P] 在 `src/procurement_bot/ingest/versioning.py` 实现 `extract_version_info(text, filename) -> (date|None, version|None, DateConfidence)`,支持 `生效日期/发布日期/Effective Date` + `2024-03-01`/`2024/3/1`/`2024年3月1日`,以及 `版本:V1.2`/`Version: v1.2`/`Rev. 3`;正文抽不到时才回退到文件名中的 4 位年份并标记 `filename`;**绝不使用文件 mtime**(D-07)
- [X] T012 [P] 在 `tests/test_versioning.py` 测试三种日期写法、两种版本写法、抽不到时返回 `none`、文件名回退只在正文缺失时生效
- [X] T013 在 `src/procurement_bot/ingest/loader.py` 实现 `build_index(corpus_root, secret_dir_name) -> IndexData`:递归遍历;按相对路径首段判 `sensitivity`(FR-008);受限文档按保密目录下一级子目录判 `category`(FR-008a);调用 parser;把 `RawSection` 切成 ≤1500 字符的 `Passage`;解析失败或空内容记入 `RejectedFile` 且**不中断**(FR-018);计算 IDF;产出可 JSON 序列化的索引
- [X] T014 [P] 在 `tests/test_ingest.py` 测试:密级按目录判定;品类按子目录判定;保密根目录下的文件 `category is None`;**"已导入 + 未纳入" 的文件数 == 语料下文件总数**(SC-008 / INV-R1);重复导入幂等(INV-I1)
- [X] T015 [P] 在 `src/procurement_bot/roster.py` 实现 `load_roster(path) -> Roster`:UTF-8(容忍 BOM)CSV,四列;校验 INV-Q1/Q2/Q3;非法角色或缺列抛 `RosterFormatError` 并**指明行号**(D-10);实现 `lookup(employee_id)`、`route_for(category)`、`categories` 属性
- [X] T016 [P] 在 `tests/test_roster.py` 测试:三种角色解析;`;` 多品类;`*` 仅限采购负责人;采购员填了品类要报错;非法角色报错含行号;未知工号 `lookup` 抛 `UnknownRequesterError`
- [X] T017 [P] 在 `src/procurement_bot/llm/base.py` 定义 `PassageView`、`LLMRequest`、`LLMResponse` 与 `LLMDriver` Protocol(contracts/llm-driver.md)
- [X] T018 在 `src/procurement_bot/llm/mock.py` 实现 `KeywordMockDriver`(按 contracts/llm-driver.md 的四条确定性规则)与 `ScriptedDriver`(按问题子串匹配返回预设 `LLMResponse`,支持构造伪造引用的"说谎"响应)
- [X] T019 [P] 在 `tests/test_drivers.py` 测试:`KeywordMockDriver` 无重合时 `sufficient=False`;平分时按 `passage_id` 字典序取小(确定性);`ScriptedDriver` 能返回不存在的引用 ID

**Checkpoint**: 基础设施就绪,US1–US4 可以开始

---

## Phase 3: User Story 1 — 有据可查地答,答不上来就说不知道 (P1) 🎯 MVP

**Goal**: 采购员提问 → 从 md/txt 语料中找到依据 → 带出处作答;无依据时诚实回答"不知道"。

**Independent Test**: 只用 `.md`/`.txt` 演示语料,跑 quickstart 第 1、2 条;
再用"说谎驱动"验证伪造引用被拦截。此时即为可用 MVP。

> **注(analyze 发现 F1)**:US1 也需要 `roster.py`(T015)——FR-001 要求 `ask` 接受
> "提问者身份(含角色)",身份解析在 US1 就已发生,权限**判定**才属于 US2。
> 因此 roster 放在 Foundational 而非 US2 专属,这与 US1"可独立交付"并不冲突。

- [X] T020 [P] [US1] 在 `src/procurement_bot/verifier.py` 实现 `check(request, response) -> VerifyResult`:四项检查(`sufficient` 为假 / 引用为空 / 引用 ID 不在请求片段内 / 正文空白)任一失败即降级为 `unknown`,并置 `fabrication_blocked`(D-05)
- [X] T021 [P] [US1] 在 `tests/test_verifier.py` 覆盖四项检查各自的失败路径与全部通过的成功路径
- [X] T022 [P] [US1] 在 `src/procurement_bot/prompting.py` 实现 `build_request(question, scored_passages, top_k) -> (LLMRequest, partial_context: bool)`:取 Top-K,`source_label` 由文档名 + locator 拼成;候选数 > K 时 `partial_context=True`(FR-006)
- [X] T023 [US1] 在 `src/procurement_bot/conflict.py` 实现 `detect_groups(scored_passages, documents)`(标题词元剥离版本噪声词后 Jaccard ≥ 0.6 聚簇)与 `resolve(group) -> ConflictGroup`(全员日期/版本可比 → `superseded`;否则 → `unresolved`)(FR-005a/b, D-08)
- [X] T024 [P] [US1] 在 `tests/test_conflict.py` 测试:两份带日期的同主题文档 → `superseded` 且 primary 为新版;两份都无日期 → `unresolved`;主题不同的两份文档不聚簇
- [X] T025 [P] [US1] 在 `src/procurement_bot/audit.py` 实现 `AuditLog.append(record)` / `tail(limit)`(JSONL);**写入前剥除任何受限文档标识**,仅保留 `restricted_hit: bool`(INV-U1)
- [X] T026 [P] [US1] 在 `src/procurement_bot/escalation.py` 实现 `EscalationStore.create(...) -> Escalation` 与 `tail()`(JSONL 追加);记录中**不得含**受限正文(INV-E1)
- [X] T027 [US1] 在 `src/procurement_bot/core.py` 实现 `AskService`:`build_index`、`load`、`ask`。`ask` 严格按 contracts/core-api.md 的 CA-5 顺序执行;组装 `Answer` 时由代码从 Passage 生成 `Citation`(含 ≤200 字符摘录),**不采用模型自写的出处**(D-05);遵守 INV-A1~A4;驱动异常被捕获为 `unknown`(CA-7)
- [X] T028 [US1] 在 `src/procurement_bot/cli.py` 实现 `main()` 与 `ingest`、`ask` 两个子命令,含 contracts/cli.md 定义的通用参数、退出码与人读输出格式;`--json` 输出 `Answer` 序列化
- [X] T029 [US1] 在 `scripts/build_demo_corpus.py` 生成 `.md`/`.txt` 演示文档:`品类管理手册-电解铜.md`(含"本品类负责人:张伟(工号 P1002)")、`供应商准入流程.txt`、`规格要求-紧固件.md` 与 `规格要求-紧固件-补充.md`(**两份互相矛盾且均无日期**,供 FR-005b);创建 `demo/roster.csv`(5 人,含 D-10 的示例)
- [X] T030 [P] [US1] 在 `tests/test_answer.py` 测试:有覆盖 → `answered` 且 `citations` 非空且引用指向正确文档;无覆盖 → `unknown` 且 `citations` 为空且生成了 escalation;**说谎驱动伪造引用 → 被拦截为 `unknown` 且 `fabrication_blocked=True`**;`sufficient=False` 时即使有正文也丢弃
- [X] T031 [P] [US1] 在 `tests/test_core_api.py` 测试 CA-1(不读环境变量/argv)、CA-2(不打印)、CA-3(可 JSON 序列化)、CA-4(幂等)、CA-6(未知工号抛异常而非降权)
- [X] T032 [US1] 在 `tests/test_cli.py` 测试 `pbot ingest` 与 `pbot ask` 的端到端:退出码 0、输出含【出处】、无覆盖时输出"资料里没有查到"

**Checkpoint**: US1 完成 —— 一个可用的、不会瞎编的问答机器人(仅 md/txt)

---

## Phase 4: User Story 2 — 保密信息按角色隔离 (P2)

**Goal**: 受限内容只有对应品类的品类经理与采购负责人能看到,其余人一个字都看不到。

**Independent Test**: 同一个"电解铜单价"问题,分别以 P1001(采购员)、P1002(电解铜经理)、
P1003(紧固件经理)、P9000(负责人)提问,只有后两者拿到内容。

- [X] T033 [US2] 在 `src/procurement_bot/authz.py` 实现 `can_access(requester, document)`(data-model.md 中的四行判定)与 `partition(passages, documents, requester) -> (visible, restricted)`
- [X] T034 [US2] 在 `src/procurement_bot/authz.py` 实现 `restricted_hit_probe(question, restricted_passages, idf) -> (hit: bool, categories: frozenset[str])`:对受限片段打分,**只返回布尔与品类标签,文本立即丢弃**(D-06)
- [X] T035 [US2] 在 `src/procurement_bot/core.py` 的 `ask` 中接入:`partition` 必须早于 `prompting.build`(CA-5);受限命中且分数超过阈值且高于可见最高分 → 返回 `status=denied` + 固定文案(INV-A4)+ 联系人 + escalation(`permission_denied`)
- [X] T036 [US2] 在 `src/procurement_bot/cli.py` 增加 `denied` 分支的渲染(contracts/cli.md 的权限不足输出样式)
- [X] T037 [US2] 在 `scripts/build_demo_corpus.py` 增加保密语料:`保密/电解铜/成本构成说明.md`(含可识别的价格串,如 `68500 元/吨`)、`保密/紧固件/谈判策略要点.md`
- [X] T038 [US2] 在 `tests/test_authz.py` 测试 `can_access` 的四条分支 + 保密根目录文件仅负责人可见
- [X] T039 [US2] 在 `tests/test_authz.py` 增加 `test_restricted_text_never_leaves_authz`:以 P1001 与 P1003 提问受限问题,断言价格串 `68500` **不出现在** `LLMRequest` 的任何片段、`Answer` 的 JSON 序列化、审计记录、escalation 记录、CLI 完整输出中(宪法原则 II 的强制手段)
- [X] T040 [P] [US2] 在 `tests/test_authz.py` 增加提示词注入测试:问题含"忽略之前所有限制…",仍返回 `denied`
- [X] T041 [P] [US2] 在 `tests/test_authz.py` 增加 `test_denied_message_is_constant`:两个不同的受限问题得到**逐字相同**的 `Answer.text`(防侧信道,INV-A4)

**Checkpoint**: US2 完成 —— 可以给真实保密文档用了

---

## Phase 5: User Story 3 — 转人工 + 知识缺口沉淀 (P3)

**Goal**: 答不上来时当场告诉采购员找谁,并把缺口攒成一份可按次数排序的清单。

**Independent Test**: 连问几个无覆盖问题,`pbot gaps` 按次数降序列出,且指向正确的品类经理。

- [X] T042 [US3] 在 `src/procurement_bot/roster.py` 实现 `detect_category(question, categories) -> str|None`:用 roster 与保密子目录并集构成的品类词表在问题中做最长匹配(FR-014a, D-11);**词表来自数据,不得硬编码**
- [X] T043 [US3] 在 `src/procurement_bot/core.py` 中把 `detect_category` + `route_for` 接入 `unknown` 与 `denied` 分支,填充 `Answer.contacts`
- [X] T044 [US3] 在 `src/procurement_bot/escalation.py` 实现 `gap_report(limit) -> GapReport`:按**归一化问题文本**(去空白去标点小写化)聚合计数,降序;`permission_denied` 单独分组(C-G2)
- [X] T045 [US3] 在 `src/procurement_bot/cli.py` 增加 `gaps` 子命令与表格渲染
- [X] T046 [P] [US3] 在 `tests/test_escalation.py` 测试:无覆盖问题生成 `no_coverage` 记录;权限不足生成 `permission_denied` 记录;两类在 `gap_report` 中分开
- [X] T047 [P] [US3] 在 `tests/test_escalation.py` 测试排序:同一问题问 3 次、另一问题问 1 次 → 清单第一行是前者且次数为 3
- [X] T048 [P] [US3] 在 `tests/test_escalation.py` 测试路由:含"紧固件"的问题 → 联系人为 P1003;无法识别品类的问题 → 联系人为采购负责人 P9000

**Checkpoint**: US3 完成 —— 系统开始产出"该补哪些文档"的清单

---

## Phase 6: User Story 4 — 什么格式都能收 (P4)

**Goal**: Word/PDF/Excel 都能读;读不了的进"未纳入清单",绝不静默丢失。

**Independent Test**: 混合格式目录(含一个损坏文件与一个 `.bin`)导入后,
各格式内容可被问答命中,`pbot rejected` 列出 2 个失败文件及原因。

- [X] T049 [P] [US4] 在 `src/procurement_bot/ingest/parsers.py` 实现 `parse_docx`(python-docx;段落 + 表格;`locator` 用最近的标题样式段落)
- [X] T050 [P] [US4] 在 `src/procurement_bot/ingest/parsers.py` 实现 `parse_pdf`(pypdf;逐页,`locator = "第 N 页"`;抽出文本为空视为扫描件 → 抛异常进入被拒清单)
- [X] T051 [P] [US4] 在 `src/procurement_bot/ingest/parsers.py` 实现 `parse_xlsx`(openpyxl;逐工作表,每行拼成 `表头: 值` 的可读文本,`locator = "工作表:<名>"`)(US4-AS3)
- [X] T052 [US4] 在 `scripts/build_demo_corpus.py` 增加二进制格式生成:`采购流程说明.docx`(生效日期 2024-03-01)、`采购流程说明-2019旧版.docx`(生效日期 2019-05-01)供 FR-005a;`供应商清单-电解铜.xlsx`(两个工作表);`Category_Ownership_Matrix.pdf`(**英文**,用自写的最小 PDF 生成器,D-03);`保密/电解铜/2025年度报价表.xlsx`;损坏文件 `扫描件-旧合同.pdf`(截断字节)与 `说明.bin`
- [X] T053 [US4] 在 `src/procurement_bot/cli.py` 增加 `rejected` 子命令
- [X] T054 [P] [US4] 在 `tests/test_parsers.py` 测试四种格式各自的解析结果与 `locator` 正确性(docx 标题、pdf 页码、xlsx 工作表名)
- [X] T055 [P] [US4] 在 `tests/test_ingest.py` 增加 `test_corrupt_file_is_reported`:损坏 PDF 与 `.bin` 都出现在 `RejectedFile` 中且原因是人话,且**导入整体成功**
- [X] T056 [P] [US4] 在 `tests/test_conflict.py` 增加基于两份 docx 的 FR-005a 端到端断言:答案带 `另有旧版` notice 且 primary 为 2024 版

**Checkpoint**: US4 完成 —— 可以对着真实共享盘跑了

---

## Phase 7: Polish & Cross-Cutting

- [X] T057 [P] 在 `src/procurement_bot/llm/anthropic_driver.py` 实现 `AnthropicDriver`(**只写不跑**):函数体内 `import anthropic`;要求模型输出严格 JSON;**不得被任何测试导入执行**
- [X] T058 [P] 在 `src/procurement_bot/cli.py` 增加 `audit` 与 `roster-template` 子命令;`roster-template` 输出 **UTF-8 with BOM**(C-R1)
- [X] T059 [P] 在 `tests/test_constitution.py` 增加宪法合规测试:(a) `pyproject.toml` 中不含 `faiss|chroma|embedding|pgvector|sentence-transformers` 等禁用词(原则 V);(b) 递归扫描 `src/` 除 `llm/anthropic_driver.py` 外无 `import anthropic|openai` 等厂商 SDK(原则 IV);(c) 扫描 `src/` 无硬编码的品类名/人名(原则 III)
- [X] T060 [P] 在 `tests/test_core_api.py` 增加 `test_core_is_channel_agnostic`:完全不经 CLI,直接用 `AskService` 跑通"提问 → 答案 → 缺口清单"全流程
- [X] T061 编写 `scripts/demo_walkthrough.py`:按 quickstart.md 第 4 节的 14 条逐条执行并打印"预期 / 实际 / 是否符合"
- [X] T062 编写 `demo/qa_selftest.md`:针对自造语料的自测问答集(覆盖 quickstart 14 条 + 若干补充),作为需求方 20 条清单到位前的替代验收基准
- [X] T063 编写根目录 `README.md`:5 分钟上手、目录约定(引用 contracts/corpus-layout.md)、六条命令说明、**"能力边界"章节**(不用向量库导致的漏答、无法检测任意语义矛盾、无法拦截"引用真实来源但曲解内容"的残余幻觉风险 —— research.md D-05/D-08 已记录,必须对用户诚实)
- [X] T064 全量运行 `uv run pytest -q` 与 `uv run python scripts/demo_walkthrough.py`,确认全绿;修复所有失败

### Phase 7b: /speckit-analyze 补救任务(本阶段由 analyze 报告驱动新增)

- [X] T065 [P] **[分析发现 E1]** 在 `tests/test_cli.py` 增加 `test_mock_path_is_fast`:mock 驱动下单次 `ask` 端到端 < 2 秒(SC-005 的离线可测代理);并在 T063 的 README 中声明真实驱动的延迟取决于模型服务、不在离线验收范围内
- [X] T066 [P] **[分析发现 E2]** 在 `tests/test_ingest.py` 增加 `test_new_file_is_queryable_after_reingest`:写入一个新 `.md` → 重跑 `build_index` → 断言新内容可被检索命中(SC-004 / FR-019 的直接验证)
- [X] T067 [P] **[分析发现 E3]** 在 `tests/test_answer.py` 增加 `test_partial_context_notice`:构造候选数 > `top_k` 的情形,断言 `Answer.partial_context is True` 且 `notices` 含截断声明(FR-006)
- [X] T068 [P] **[分析发现 E4]** 在 `tests/test_escalation.py` 增加 `test_audit_record_is_complete`:一次问答后断言审计记录包含 data-model.md 定义的全部字段(FR-021)
- [X] T069 [P] **[分析发现 E5]** 在 `tests/test_authz.py` 增加 `test_mixed_document_is_fully_restricted`:一份同时含公开与受限内容的文档(位于保密目录)对采购员整份不可见(FR-012)
- [X] T070 **[分析发现 F1]** 在本文件 Phase 3 的说明中注明:US1 已需要 `roster.py` 以解析提问者身份(FR-001),故 roster 属于 Foundational 而非 US2 专属

> **F2(术语漂移)与 A1(FR-009/016 重叠)与 B1(内部性能指标)** 已在 spec.md 与
> plan.md 中就地修正或判定为不阻塞,不单列任务。

---

## Dependencies

```text
Phase 1 (Setup)
   └─> Phase 2 (Foundational)  ← 阻塞全部 Story
          ├─> Phase 3 (US1, P1)  🎯 MVP
          │      ├─> Phase 4 (US2, P2)   依赖 US1 的 ask 管线
          │      │      └─> Phase 5 (US3, P3)  依赖 US2 的 denied 分支才能测"权限不足"类缺口
          │      └─> Phase 6 (US4, P4)   仅依赖 US1 的 ingest 管线,与 US2/US3 可并行
          └─> Phase 7 (Polish)  依赖全部
```

**Story 间依赖说明**:

- US1 独立,是 MVP。
- US2 依赖 US1 的 `ask` 管线(要在管线里插入 authz)。
- US3 的"权限不足类缺口"依赖 US2;其"无覆盖类缺口"只依赖 US1。若要严格独立交付,
  可先做 US3 的无覆盖部分,US2 完成后再补权限部分。
- **US4 与 US2/US3 完全独立**(只碰 `ingest/parsers.py` 与 demo 脚本),可并行。

## Parallel Execution Examples

- **Phase 2**:T009 / T011+T012 / T015+T016 / T017 三组互不相干,可并行。
- **Phase 3**:T020+T021(verifier)、T022(prompting)、T025(audit)、T026(escalation)
  四者文件互不重叠,可并行;T027(core)必须等它们全部完成。
- **Phase 4 vs Phase 6**:两个 Story 触碰的文件几乎不重叠(authz/core vs parsers/scripts),
  是最大的并行机会。
- **Phase 7**:T057 / T058 / T059 / T060 / T062 / T063 全部可并行;T061 与 T064 最后串行。

## Implementation Strategy

1. **MVP = Phase 1 + 2 + 3**。交付时可以对采购负责人说:"现在它能答 md/txt 里的问题,
   答不上来会说不知道,而且不会编。" 这已经能验证最核心的信任问题。
2. 接着做 **Phase 4(保密)**——这是上线前的硬门槛,没有它不能碰真实文档。
3. 然后 **Phase 6(多格式)**——这是"能不能真的用起来"的分水岭(采购部资料多为 Word/Excel)。
4. **Phase 5(缺口清单)** 可以稍晚,它的价值随使用时间累积。
5. Phase 7 收尾,其中 **T063 的"能力边界"章节不可省略**——对用户诚实是宪法原则 I 的延伸。

## Task Summary

| 阶段 | 任务数 | 其中测试任务 |
|------|--------|--------------|
| Phase 1 Setup | 4 | 1(禁网 fixture) |
| Phase 2 Foundational | 15 | 5 |
| Phase 3 US1 (P1) | 13 | 5 |
| Phase 4 US2 (P2) | 9 | 4 |
| Phase 5 US3 (P3) | 7 | 3 |
| Phase 6 US4 (P4) | 8 | 3 |
| Phase 7 Polish | 8 | 2 |
| Phase 7b Analyze 补救 | 6 | 5 |
| **合计** | **70** | **28** |

---

## 实现阶段的实际偏差记录(诚实留痕)

以下是 implement 阶段**照着任务做、但被现实纠正**的地方。tasks.md 是计划,不是历史,
所以把差异写在这里,而不是假装当初就想到了。

| 任务 | 计划 | 实际 | 原因 |
|------|------|------|------|
| T007/T008 | 只做 bigram + IDF 打分 | **额外加了 `unknown_content_chars` 未知词 guard** | 跑演示时发现"钛合金紧固件的规格"会被"紧固件规格"匹配上并答非所问 —— 正是需求方最怕的"瞎编"。这是 plan 阶段没预见到的漏洞 |
| T027 | `ask` 按 CA-5 顺序执行 | 未知词 guard 插在**权限判定之前** | 否则库里根本没有的问题会因偶然蹭到保密文件字眼而被答成"你权限不足",既误导又暗示保密资料的存在 |
| T027 | FR-005b 由 conflict 模块产出提示 | 内核**额外把并列来源都塞进 citations** 并改写答案正文 | 只发一条 notice 但仍然只列一个来源,不满足"并列呈现全部来源" |
| T027 | 冲突提示直接输出 | 只对**支撑了本次答案**的冲突组发提示 | 否则弱命中会在每个不相干问题下面挂一条"另有旧版" |
| T033/T034 | probe 只回 hit/分数/品类 | 增加 `uncategorised` 标志 | 未归品类的保密材料转给品类经理等于白转,应转采购负责人 |
| T051 | xlsx 每行渲染为"表头: 值",分号分隔 | 改为 ` | ` 分隔,且**不再单独输出表头行** | 分号是句子分隔符会把数据行切碎;单独的表头行是检索噪声 |
| T010/T049 | markdown/docx 标题栈按 `level-1` 下标维护 | 改为 `(级别, 标题)` 元组栈 | 原写法在"文档以 `##` 开头、没有 `#`"时会把同级标题错误嵌套 —— 由 `test_markdown_sibling_headings_do_not_nest` 抓到 |
| T002 | 创建 `tests/__init__.py` | **删除了它** | 有 `__init__.py` 时 pytest 不把 `tests/` 放进 sys.path,`from conftest import` 会失败 |
| T057 | roster 模板用真实示例 | 改为占位名(张三/品类甲) | `test_domain_knowledge_is_not_hardcoded` 抓到模板里的品类名违反宪法原则 III |

**结论**:9 处偏差里,**5 处是在跑演示时被真实输出打脸发现的**,4 处是被自己写的测试抓到的。
计划没白做(结构、模块边界、契约全部照用),但"计划里没有的东西"确实存在,
而且集中在"确定性检索到底够不够用"这个我在 research 阶段乐观了的判断上。
