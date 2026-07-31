# Phase 1 — Data Model

**Feature**: 001-procurement-knowhow-bot | **Date**: 2026-07-31

全部实体为不可变 `@dataclass(frozen=True)`,除非另行说明。无数据库,序列化为 JSON/JSONL。

---

## 枚举

```text
Sensitivity  = internal | restricted
Role         = 采购员 | 品类经理 | 采购负责人
AnswerStatus = answered | unknown | denied
EscalationReason = no_coverage | permission_denied | fabrication_blocked
DateConfidence   = body | filename | none
```

---

## Document

一份被成功解析的原始资料。

| 字段 | 类型 | 说明 / 不变量 |
|------|------|----------------|
| `doc_id` | str | 语料根下的相对路径(POSIX 风格),**天然唯一** |
| `filename` | str | 文件名(不含目录) |
| `fmt` | str | `md`/`txt`/`docx`/`pdf`/`xlsx` |
| `sensitivity` | Sensitivity | **由路径判定**:相对路径首段为保密文件夹名 → `restricted`,否则 `internal`(FR-008) |
| `category` | str \| None | 受限文档 = 保密文件夹下的一级子目录名;直接位于保密根下 → `None`(FR-008a)。非受限文档为 `None` |
| `effective_date` | date \| None | 见 versioning(D-07) |
| `version` | str \| None | 如 `1.2` / `3` |
| `date_confidence` | DateConfidence | `body` 优先于 `filename`;抽不到为 `none` |
| `ingested_at` | datetime | 导入时间 |
| `title_tokens` | tuple[str,...] | 由文件名去扩展名后分词并剥离版本噪声词,供冲突检测用(D-08) |

**不变量**

- INV-D1:`sensitivity == internal` ⇒ `category is None`。
- INV-D2:`category is not None` ⇒ `sensitivity == restricted`。
- INV-D3:`doc_id` 在一次索引内唯一。
- INV-D4:同名不同路径的两份文件是**两个** Document,系统不去重(spec Edge Cases)。

---

## Passage

可引用的最小单位。

| 字段 | 类型 | 说明 |
|------|------|------|
| `passage_id` | str | `{doc_id}#{序号}`,稳定且唯一 |
| `doc_id` | str | 外键 → Document |
| `locator` | str | 人可读的位置:`§ 2.1 规格要求` / `第 3 页` / `工作表:合格供应商` |
| `text` | str | 正文;长度上限 1500 字符,超出则在导入时按段落边界继续切分 |
| `heading_path` | tuple[str,...] | 章节层级,供加权(标题命中权重 2.0) |

**不变量**

- INV-P1:`text` 非空且去除首尾空白后长度 ≥ 1。
- INV-P2:敏感度**不独立存储**,一律通过 `doc_id` 继承自 Document(FR-012 = 整份判密)。
  这是一个刻意的建模决定:让"片段有自己的密级"在类型上就不可表达,从而杜绝
  "某处忘了继承"导致的越权。

---

## RejectedFile

未能纳入知识库的文件(FR-018)。

| 字段 | 类型 | 说明 |
|------|------|------|
| `path` | str | 相对路径 |
| `reason` | str | 人话原因:`不支持的格式(.bin)` / `文件损坏或加密,无法读取` / `内容为空` |
| `detail` | str | 技术细节(异常类型与消息),给排查用 |
| `found_at` | datetime | |

**不变量**:INV-R1:`Document` 集合与 `RejectedFile` 集合的 `path` 不相交;
两者并集 == 语料目录下的全部普通文件(**零静默丢失**,SC-008)。

---

## Requester

| 字段 | 类型 | 说明 |
|------|------|------|
| `employee_id` | str | 工号,唯一 |
| `name` | str | |
| `role` | Role | |
| `categories` | frozenset[str] | 负责品类;`采购负责人` 为 `{"*"}`;`采购员` 为空集 |

**不变量**

- INV-Q1:`role == 采购员` ⇒ `categories == ∅`(解析时若填了值,报错而非忽略)。
- INV-Q2:`"*" in categories` ⇒ `role == 采购负责人`。
- INV-Q3:`role == 品类经理` ⇒ `categories` 非空且不含 `*`。

**权限判定(唯一实现处 `authz.can_access`)**

```text
can_access(requester, document):
    if document.sensitivity == internal:      return True
    if "*" in requester.categories:           return True        # 采购负责人
    if document.category is None:             return False       # 保密根目录 → 仅负责人
    return document.category in requester.categories
```

---

## Roster

`roster.csv` 的内存表示。字段:`by_id: dict[str, Requester]`、
`categories: frozenset[str]`(全部出现过的品类,供转人工路由的品类识别用)。

**路由(FR-014a)**:`route_for(category) -> tuple[Requester, ...]`
— 返回负责该品类的全部品类经理;为空或 `category is None` 时返回采购负责人。

---

## Citation

| 字段 | 类型 | 说明 |
|------|------|------|
| `passage_id` | str | |
| `doc_name` | str | 文档名 |
| `locator` | str | |
| `excerpt` | str | 原文摘录(≤ 200 字符),**由代码从 Passage 截取,不由模型产生**(D-05) |

---

## ConflictGroup

| 字段 | 类型 | 说明 |
|------|------|------|
| `doc_ids` | tuple[str,...] | 竞争来源(≥ 2) |
| `resolution` | `superseded` \| `unresolved` | |
| `primary_doc_id` | str \| None | `superseded` 时为最新的那份 |
| `superseded_doc_ids` | tuple[str,...] | `superseded` 时的旧版 |

**状态流转**:检索 Top-K → 按标题词元 Jaccard ≥ 0.6 聚簇 → 若全员日期/版本可比
⇒ `superseded`;否则 ⇒ `unresolved`(FR-005a / FR-005b)。

---

## Answer

内核的唯一输出对象(渠道无关)。

| 字段 | 类型 | 说明 |
|------|------|------|
| `status` | AnswerStatus | |
| `text` | str | 答案正文。`unknown`/`denied` 时为统一文案 |
| `citations` | tuple[Citation,...] | `status != answered` 时**必为空** |
| `notices` | tuple[str,...] | 结构化提示,如"资料不一致,请自行核实"/"本次只参考了资料的部分内容"/"另有旧版:…" |
| `contacts` | tuple[Requester,...] | `unknown`/`denied` 时应联系的人(FR-014) |
| `conflicts` | tuple[ConflictGroup,...] | |
| `partial_context` | bool | FR-006 |
| `escalation_id` | str \| None | 生成的转人工记录 ID |

**不变量**

- INV-A1:`status == answered` ⇒ `citations` 非空(宪法原则 I:无出处即非答案)。
- INV-A2:`status != answered` ⇒ `citations == ()`。
- INV-A3:`status in {unknown, denied}` ⇒ `escalation_id is not None` 且 `contacts` 非空。
- INV-A4:`status == denied` 时,`text` 为**固定常量**,不随命中内容变化(防侧信道,D-06)。

---

## Escalation(JSONL 追加)

| 字段 | 类型 |
|------|------|
| `escalation_id` | str(uuid4 hex 前 12 位) |
| `created_at` | datetime |
| `employee_id` / `name` / `role` | str |
| `question` | str |
| `reason` | EscalationReason |
| `question_category` | str \| None |
| `routed_to` | tuple[str,...](工号) |

**不变量**:INV-E1:记录中 **MUST NOT** 出现任何受限片段正文(FR-016)。
`reason == permission_denied` 时不写入任何文档标识。

---

## AuditRecord(JSONL 追加)

| 字段 | 类型 |
|------|------|
| `at` | datetime |
| `employee_id` / `role` | str |
| `question` | str |
| `status` | AnswerStatus |
| `visible_hit_doc_ids` | tuple[str,...] | 仅**可见**文档 |
| `restricted_hit` | bool | 是否命中了受限材料(**只记布尔,不记文档名**) |
| `fabrication_blocked` | bool | 防幻觉校验是否拦截过 |
| `partial_context` | bool |
| `escalation_id` | str \| None |

**不变量**:INV-U1:审计记录中 MUST NOT 出现受限文档的名称或正文(FR-016 + D-06)。

---

## 索引文件 `index.json`

```text
{
  "built_at": ...,
  "corpus_root": ...,
  "documents": [Document...],
  "passages": [Passage...],
  "rejected": [RejectedFile...],
  "idf": {token: float}          # 由语料现算并固化,保证 ask 与 ingest 的打分一致
}
```

**不变量**:INV-I1:`ingest` 是幂等的——同一语料目录重复执行产出逐字节相同的
`documents`/`passages`/`idf`(时间戳字段除外)。这是"确定性"的可测断言。
