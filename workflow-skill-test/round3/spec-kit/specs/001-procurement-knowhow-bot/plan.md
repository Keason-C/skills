# Implementation Plan: 采购 Commodity Know-How 问答机器人

**Branch**: `001-procurement-knowhow-bot` | **Date**: 2026-07-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-procurement-knowhow-bot/spec.md`

## Summary

给采购部做一个命令行问答机器人:读同事上传到共享盘的 Word/PDF/Excel/Markdown 文档,
回答"品类归谁管、供应商有哪些、规格要求、走什么流程"这类问题,**每句话都要有出处**,
**答不上来老实说不知道并当场告诉采购员该找谁**,**报价/成本/谈判策略只有对应品类的
品类经理能看**。

技术路线(详见 [research.md](./research.md)):不建向量库;用**确定性的中文 bigram +
英文词元打分**做粗筛,取 Top-K 片段交给大模型;大模型藏在 `LLMDriver` 接口后面,
测试全部用确定性 mock 且**禁网**;引用由代码校验并生成,模型无法伪造出处;
权限过滤发生在组 prompt 之前,受限文本永不进入 prompt / 日志 / 输出。

## Technical Context

**Language/Version**: Python 3.11(实测 3.11.15),用 `uv` 管理环境与依赖

**Primary Dependencies**: `python-docx` 1.2.0、`pypdf` 6.14.2、`openpyxl` 3.1.5
(逐个的正当性见 research.md D-03)。真实模型 SDK 为**可选** extra,核心不依赖。

**Storage**: 无数据库。语料目录只读;状态为 `./.pbot/` 下的 `index.json` +
`escalations.jsonl` + `audit.jsonl`(D-09)

**Testing**: `pytest`;`tests/conftest.py` 用 autouse fixture **屏蔽 socket 连接**,
任何联网尝试立即失败(D-04)

**Target Platform**: Linux / Windows 桌面与内网服务器(采购部电脑能读到共享盘即可)

**Project Type**: 单 Python 包 + CLI(无前端;spec 明确本期只交付命令行)

**Performance Goals**: 单次提问端到端 ≤ 30s(SC-005);其中本地检索部分在
50 份文档 / 2000 片段规模下 ≤ 200ms(内部指标,不对外承诺)

**Constraints**: 测试必须**完全离线**;不得引入向量库/embedding;
真实 LLM 调用只写不跑;受限内容零泄漏(SC-003)

**Scale/Scope**: 数十份文档、个位数并发用户、三种角色、两级密级

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| # | 原则 | 本设计如何满足 | 强制手段(可失败的门禁) | 初检 | 复检 |
|---|------|----------------|--------------------------|------|------|
| I | 有据可查,拒绝编造 | 结构化响应 + 代码侧引用校验器;`sufficient=False` 或引用不存在 → 一律降级为"不知道" | `test_answer.py::test_lying_driver_is_blocked`、`test_no_coverage_abstains` | PASS | PASS |
| II | 权限先于内容 | authz 过滤在检索与组 prompt **之前**;受限片段仅参与"是否命中"打分,文本立即丢弃 | `test_authz.py::test_restricted_text_never_leaves_authz`(断言价格串不出现在 prompt/审计/输出) | PASS | PASS |
| III | 知识落在库里 | 品类词表/供应商/流程全部来自语料与 roster,零硬编码;解析失败进"未纳入清单";每次转人工即一条知识缺口 | `test_ingest.py::test_corrupt_file_is_reported`、`test_escalation.py::test_gap_report_ordering` | PASS | PASS |
| IV | 模型在驱动接口之后 | `LLMDriver` 协议;核心不 import 厂商 SDK;真实驱动只写不跑 | `conftest.py` 禁网 fixture + `test_drivers.py::test_core_imports_no_vendor_sdk` | PASS | PASS |
| V | 够用就好 | 无向量库/embedding;3 个解析依赖已逐个论证;自写 30 行 PDF 生成器避免第 4 个依赖 | `test_no_vector_dependency`(扫描 pyproject 禁用词) | PASS | PASS |
| VI | 内核与通道分离 | `AskService.ask(question, employee_id) -> Answer` 为纯入口;`cli.py` 只解析与渲染 | `test_core_api.py::test_core_is_channel_agnostic`(不经 CLI 直接调内核跑通全流程) | PASS | PASS |

**Gate 结论:无违规,Complexity Tracking 表留空。**

**一处经复核的边界情况**(记录在案,非违规):原则 II 禁止受限内容进入**生成上下文**。
本设计让受限片段参与打分(以便区分"没这资料"和"你没权限"),打分不是生成,
且文本在打分后立即丢弃、由测试断言其不出现在任何下游产物中。详见 research.md D-06。

## Project Structure

### Documentation (this feature)

```text
specs/001-procurement-knowhow-bot/
├── plan.md              # 本文件
├── research.md          # Phase 0:12 条技术决策
├── data-model.md        # Phase 1:实体与不变量
├── quickstart.md        # Phase 1:可照做的验证脚本
├── contracts/
│   ├── cli.md           # 命令行契约(命令、参数、退出码、输出格式)
│   ├── core-api.md      # 内核 Python API 契约(供企业微信等渠道复用)
│   ├── llm-driver.md    # LLM 驱动接口契约
│   └── corpus-layout.md # 语料目录与 roster.csv 的约定(给需求方看的)
├── checklists/
│   └── requirements.md  # spec 质量检查清单(16/16)
└── tasks.md             # Phase 2 输出,由 /speckit-tasks 生成
```

### Source Code (repository root)

```text
pyproject.toml
README.md
src/procurement_bot/
├── __init__.py
├── models.py          # 全部 dataclass:Document/Passage/Requester/Answer/...
├── errors.py
├── roster.py          # roster.csv 解析、角色/品类判定、转人工联系人路由
├── ingest/
│   ├── __init__.py
│   ├── parsers.py     # md/txt/docx/pdf/xlsx 五个解析器 + 未知格式处理
│   ├── versioning.py  # 生效日期/版本号抽取(D-07)
│   └── loader.py      # 目录遍历、密级判定(路径)、品类判定(子目录)、被拒清单
├── retrieval.py       # bigram+词元 IDF 打分(D-01)
├── authz.py           # 权限过滤(D-06)
├── conflict.py        # 竞争来源检测与 FR-005a/b 裁决(D-08)
├── prompting.py       # 组装 LLMRequest
├── verifier.py        # 引用校验/防幻觉(D-05)
├── llm/
│   ├── __init__.py
│   ├── base.py        # LLMDriver 协议 + LLMRequest/LLMResponse
│   ├── mock.py        # KeywordMockDriver / ScriptedDriver(确定性,离线)
│   └── anthropic_driver.py  # 真实驱动:只写不跑
├── escalation.py      # 转人工记录、知识缺口清单
├── audit.py           # 审计日志
├── core.py            # AskService:内核唯一入口(渠道无关)
└── cli.py             # 薄适配器:ingest/ask/gaps/rejected/audit/roster-template

tests/
├── conftest.py        # 禁网 fixture + 共享夹具
├── test_parsers.py
├── test_ingest.py
├── test_retrieval.py
├── test_versioning.py
├── test_authz.py
├── test_conflict.py
├── test_verifier.py
├── test_answer.py
├── test_escalation.py
├── test_drivers.py
├── test_core_api.py
└── test_cli.py

scripts/
└── build_demo_corpus.py  # 生成 docx/xlsx/pdf/损坏文件(含 30 行自写 PDF 生成器)

demo/
├── corpus/            # 假采购语料(中英混排),含 保密/<品类>/ 子目录
├── roster.csv
└── qa_selftest.md     # 自测问答集(替代待提供的 20 条清单)
```

**Structure Decision**: 采用单包布局(`src/procurement_bot/`)。理由:本期只有 CLI 一个
渠道,没有前后端之分;宪法原则 VI 要求的"内核/通道分离"通过 `core.py` 与 `cli.py`
的模块边界实现,而不是通过拆成两个项目——后者对一个几十份文档的部门工具是过度设计
(原则 V)。`llm/` 与 `ingest/` 做成子包,是因为它们各自有多个可替换实现,
子包边界即替换点。

## 需求 → 设计映射(供 /speckit-analyze 核对)

| 需求 | 承载模块 | 验证 |
|------|----------|------|
| FR-001, FR-022 | `core.AskService.ask` / `cli.py` | test_core_api, test_cli |
| FR-002, FR-004 | `verifier.py`(引用由代码生成) | test_verifier, test_answer |
| FR-003 | `verifier.py` + `core.py` 的 abstain 分支 | test_answer |
| FR-005a/b | `conflict.py` | test_conflict |
| FR-006 | `prompting.py` 的 `partial_context` 标记 | test_answer |
| FR-007, FR-008, FR-008a | `ingest/loader.py`(按路径判密与判品类) | test_ingest |
| FR-009, FR-010, FR-011, FR-012 | `authz.py` | test_authz |
| FR-011a | `roster.py` | test_roster(并入 test_authz) |
| FR-013, FR-014, FR-014a, FR-015, FR-016 | `escalation.py` + `roster.route_for` | test_escalation |
| FR-017, FR-018 | `ingest/parsers.py` + `loader.py` | test_parsers, test_ingest |
| FR-019, FR-020 | 无索引服务、无硬编码;`ingest` 可重跑 | test_ingest, test_no_hardcoded_domain |
| FR-021 | `audit.py` | test_escalation, test_authz |

## Complexity Tracking

> Constitution Check 无违规,本表留空。

(无)
