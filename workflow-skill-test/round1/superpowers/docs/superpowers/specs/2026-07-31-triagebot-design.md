# TriageBot 设计文档

日期:2026-07-31 · 状态:已获产品负责人逐条批准(见「产品决策」一节)

## 1. 目标与设计哲学

TriageBot 把客服工单自动分诊为一个**结论**:类别、优先级、情绪、建议动作、是否转人工。

核心哲学:**LLM 负责理解,确定性规则负责裁决**。
LLM 的产出叫 `LLMSuggestion`——名字里就写着它只是建议。它永远不能直接成为
`TriageResult` 的任何一个字段;每个字段都要么经过确定性守卫,要么由纯函数从
"建议 + 工具事实 + 守卫结果"推导出来。系统里没有任何一条路径能让模型输出直达输出。

推论:**LLM 完全不能决定 priority 和 escalated_to_human**。它只能建议 category /
sentiment / action / confidence,而这四项每一项都可能被规则覆盖。

## 2. 架构

```
                     ┌──────────────────────────────────────────┐
   Ticket (pydantic) │            TriageEngine                  │
   ───────────────▶  │  显式状态机 NEW→ENRICHED→CLASSIFIED→终态  │ ──▶ TriageResult
                     └───┬───────────┬──────────────┬───────────┘
                         │           │              │
                 ┌───────▼──┐  ┌─────▼─────┐  ┌─────▼──────┐
                 │ sanitize │  │  tools    │  │  guards    │
                 │ 注入检测  │  │ 本地JSON  │  │ 纯函数裁决  │
                 │ 语言检测  │  │ fixture   │  │            │
                 └──────────┘  └─────┬─────┘  └────────────┘
                                     │
                              ┌──────▼──────┐
                              │  LLMDriver  │  Protocol
                              │  Mock / Anthropic
                              └─────────────┘
```

分层与依赖方向(单向,无环):

| 层 | 模块 | 职责 | 依赖 |
|---|---|---|---|
| 领域 | `models.py` | 枚举 + Ticket/TriageResult/LLMSuggestion,严格校验 | 无 |
| 领域 | `states.py` | TriageState 枚举 + 合法转移表 + `TriageStateMachine` | 无 |
| 安全 | `sanitize.py` | 注入特征检测、注入片段脱敏、语言检测 | 无 |
| 事实 | `tools.py` | `get_order_status` / `get_refund_policy`,读本地 fixture | models |
| 推断 | `drivers/` | `LLMDriver` Protocol、`MockDriver`、`AnthropicDriver` | models |
| 裁决 | `guards.py` | 纯函数守卫;优先级推导;终态准入 | models, sanitize |
| 编排 | `engine.py` | 串起状态机、驱动、工具、守卫 | 以上全部 |
| 导出 | `schema_export.py` | pydantic → JSON Schema 到 `schema/` | models |

`guards.py` 里的每个守卫都是 `(输入) -> GuardOutcome` 的纯函数:不做 I/O、不看时钟、
不持有状态。这是"可裁决性"的前提——守卫可以被单独测试,不需要构造引擎。

## 3. 数据模型

所有 pydantic 模型 `model_config = ConfigDict(extra="forbid", strict=False, frozen=True)`。
`extra="forbid"` 保证未知字段在边界被拒绝;`frozen=True` 保证结论不可事后篡改。

### 枚举

- `Category`: BILLING / REFUND / TECHNICAL / ACCOUNT / OTHER
- `Priority`: P0 / P1 / P2 / P3
  - P0 = 服务不可用或安全事件
  - P1 = 阻塞用户核心操作(付款失败、账号锁死等)
  - P2 = 一般问题
  - P3 = 咨询/建议
- `Sentiment`: ANGRY / FRUSTRATED / NEUTRAL / SATISFIED
- `TriageState`: NEW / ENRICHED / CLASSIFIED / AUTO_RESOLVED / ESCALATED
- `GuardCode`: 见 §5

### `Ticket`

| 字段 | 类型 | 约束 |
|---|---|---|
| `id` | str | 1..64,非空白 |
| `customer_id` | str | 1..64,非空白 |
| `subject` | str | 1..200,非空白(strip 后) |
| `body` | str | 1..20000,非空白(strip 后) |
| `order_id` | str \| None | 匹配 `^[A-Za-z0-9-]{1,32}$` |
| `amount` | Decimal \| None | >= 0,最多 2 位小数 |

`order_id` 的正则不只是整洁——它是**注入防御的结构性保证**:唯一会被拼进工具调用参数
的自由文本字段,在边界就被限制成字母数字和连字符,注入语句在语法上无法通过。

### `LLMSuggestion`(驱动输出,建议)

`category`、`sentiment`、`confidence` (0..1)、`suggested_priority`、`suggested_action`
(1..500 非空白)、`rationale` (1..2000)。

### `TriageResult`(最终结论)

`ticket_id`、`category`、`priority`、`sentiment`、`confidence`、`recommended_action`、
`escalated_to_human`、`rationale`、`final_state`(校验器强制只能是 AUTO_RESOLVED /
ESCALATED)、`guards_triggered`(GuardCode 列表)、`injection_detected`(bool)、
`language`(en/zh/other)。

`final_state` 与 `escalated_to_human` 之间有跨字段校验器:
`escalated_to_human is True ⟺ final_state is ESCALATED`。这条不变式让"两个字段说法不一致"
成为一个不可能构造出来的状态,而不是一个需要靠测试去发现的 bug。

## 4. 状态机

```
NEW ──▶ ENRICHED ──▶ CLASSIFIED ──┬──▶ AUTO_RESOLVED  (终态)
                                  └──▶ ESCALATED      (终态)
```

`TriageStateMachine` 持有当前状态,`transition_to(next)` 查合法转移表,非法则抛
`IllegalTransitionError`。终态无出边(含终态→自身)。跳级(如 NEW→CLASSIFIED)非法。

两层防护:运行期由状态机拒绝;数据层由 `TriageResult.final_state` 的校验器拒绝
非终态值。要求"非法状态转移必须在类型/校验层被拒绝"因此在两个层面都成立。

## 5. 守卫规则(确定性,优先于 LLM)

`GuardCode` 与语义:

| 守卫 | 触发条件 | 是否强制升级人工 |
|---|---|---|
| `AMOUNT_THRESHOLD` | `amount is not None and amount > 1000.00` | 是 |
| `LOW_CONFIDENCE` | 重试后 `confidence < 0.6` | 是 |
| `PROMPT_INJECTION` | body 命中注入特征 | 是 |
| `P0_ALWAYS_HUMAN` | 推导出的 priority == P0 | 是 |
| `MISSING_ORDER_EVIDENCE` | 提供了 order_id 但工具查无此单,且 category ∈ {REFUND, BILLING} | 是 |
| `UNSUPPORTED_LANGUAGE` | 语言既非 en 也非 zh | 否(通过压低 confidence 间接升级) |
| `REFUND_POLICY_OVERRIDE` | category==REFUND 且建议动作 ≠ 政策规范动作 | 否 |
| `REFUND_POLICY_MISSING` | category==REFUND 但查不到政策条目 | 是 |

阈值集中在 `guards.py` 顶部的常量里,不散落在各处:
`AMOUNT_ESCALATION_THRESHOLD = Decimal("1000.00")`、`CONFIDENCE_THRESHOLD = 0.6`、
`MAX_RETRIES = 1`、`UNSUPPORTED_LANGUAGE_CONFIDENCE_CAP = 0.5`。

边界语义**明确**:金额用 `>` 而非 `>=`(等于 1000.00 不升级);置信度用 `<`
(等于 0.6 通过)。两条边界各有等值与临界的测试。

### 5.1 金额守卫

纯函数,先于一切 LLM 判断成立。无论 LLM 说什么类别、多高置信度,`amount > 1000` 就升级。

### 5.2 置信度守卫与重试

1. 第一次分类:`ToolContext(order=可能有, refund_policy=None, is_retry=False)`
2. 若 `confidence < 0.6`:补齐工具上下文(按建议类别查政策条目——fixture 为
   **每个** category 都备有条目,所以这一步对任何类别都能拿到新证据),
   以 `is_retry=True` 再分类一次(**最多一次**)
3. 仍 `< 0.6` → `LOW_CONFIDENCE` 守卫 → 升级人工

"带上工具上下文重试"因此有实义:第二次调用给驱动的证据严格多于第一次。

### 5.3 退款政策一致性

`category == REFUND` 时,引擎**必须**已调用 `get_refund_policy(REFUND)`。
- 查到:`recommended_action` 恒等于 `policy.canonical_action`。若 LLM 的建议动作与之不同,
  覆盖之,记 `REFUND_POLICY_OVERRIDE`,并在 rationale 追加
  "recommended_action overridden by refund policy <policy_id> / 已被退款政策覆盖"。
  继续自动处理(不升级)。
- 查不到:记 `REFUND_POLICY_MISSING` 并升级人工——无法核对的政策不能自动执行。

不变式(测试直接断言):**任何 category==REFUND 的结果,其 recommended_action 必然等于
fixture 里 REFUND 政策的 canonical_action**。LLM 编造的政策文本没有任何路径能出现在输出里。

### 5.4 提示注入防御

三道防线,任一独立成立:

1. **检测**:中英文特征表(`ignore previous instructions`、`system prompt`、
   `you are now`、`developer mode`、`忽略之前的指令`、`你现在是`、`开发者模式` …)。
2. **脱敏**:命中的片段在传给驱动**之前**替换为 `[REDACTED:INJECTION]`。
   驱动看到的永远是 `TicketView`,不是原始 `Ticket`——原始 body 在类型上就到不了驱动。
3. **结构性隔离**:工具调用参数从不来自自由文本。`get_order_status` 只接受已被
   `Ticket.order_id` 正则约束过的值,`get_refund_policy` 只接受 `Category` 枚举成员;
   两个工具都在入口再次校验,拒绝非法输入。

命中即 `PROMPT_INJECTION` 守卫 → 强制升级人工(产品决策 6),同时 priority 判为 P0(安全事件)。

**可证伪的行为不变式**(测试直接断言):对同一工单,附加注入载荷前后,
`category`、`sentiment`、`recommended_action` 三个字段完全相同;差异只出现在
`injection_detected` / `escalated_to_human` / `priority` / `guards_triggered` 上,
即注入只能触发防御,永远不能改变分诊内容。

### 5.5 语言

CJK 字符 → `zh`;仅 ASCII 拉丁 → `en`;其余(平假名/片假名/西里尔/阿拉伯…) → `other`。
`other` 时确定性地强制 `category = OTHER` 且 `confidence = min(confidence, 0.5)`。
0.5 < 0.6,于是必然走重试→仍不达标→升级人工。规则之间自洽,不需要额外的特判。

## 6. 优先级推导(纯函数)

`derive_priority(category, amount, sentiment, injection_detected, signals) -> Priority`

按顺序:

1. **基线**:`OTHER` → P3;命中咨询类信号("how do I"、"请问"、"咨询"、"suggestion")→ P3;
   其余 → P2
2. **阻塞升级**:命中阻塞类信号(付款失败 `payment failed` / `扣款失败`、
   账号锁死 `locked out` / `登录不了`)→ P1;或 `amount > 1000` → P1
3. **情绪加权**:`sentiment == ANGRY` 时 P3→P2、P2→P1(P1/P0 不变)
4. **P0 覆盖(最后,不可被下调)**:`injection_detected`(安全事件)
   或 `category == TECHNICAL 且命中服务不可用信号`(`service unavailable` / `is down` /
   `503` / `宕机` / `无法访问`)

第 4 步放在最后是刻意的:P0 是安全/可用性判断,不允许被前面任何一步稀释。

## 7. 终态准入

`AUTO_RESOLVED` 需**同时**满足(产品决策 8):
① 没有任何强制升级的守卫触发 ② `confidence >= 0.6` ③ `priority ∈ {P1,P2,P3}` ④ `category != OTHER`
否则 `ESCALATED`。

## 8. LLM 驱动

```python
class LLMDriver(Protocol):
    def classify(self, view: TicketView, context: ToolContext) -> LLMSuggestion: ...
```

`TicketView` 是脱敏后的只读视图(`ticket_id`、`subject`、`redacted_body`、`language`、
`amount`、`order_id`)。驱动拿不到原始 `Ticket`。

- **`MockDriver`**:确定性关键词打分(中英双语表)。同一输入永远同一输出,不看时钟、
  不用随机。重试时若上下文提供了新证据(订单已找到 或 政策已取到),置信度 +0.25(上限 0.95);
  没有新证据则原样返回——两条路径都可测。全部测试使用它。
- **`AnthropicDriver`**:真实调用 Claude API,把 `LLMSuggestion` 的 JSON Schema 作为工具
  定义交给模型走结构化输出,再用 pydantic 严格解析。**只写代码,不在测试中运行**;
  构造函数惰性导入 `anthropic`,因此不装 SDK 也不影响导入其它模块与离线测试。

## 9. TypeScript 侧

- `scripts/export_schema.py`(即 `schema_export.py` 的 CLI 入口)把 `Ticket` 与
  `TriageResult` 的 JSON Schema 写到 `schema/`。
- `ts/src/schema.ts`:手写 zod schema。
- **同步测试**:`ts/test/schema-sync.test.ts` 读取 `schema/triage_result.schema.json`,
  断言 zod schema 的字段集合、必填集合、各枚举取值与之逐一相等。
  手写 + 同步测试优于代码生成:生成的 zod 是不可读的机器产物,而同步测试能在 pydantic
  改动时直接把 TS 侧红掉,收益相同而可读性高得多。
- **真实产物测试**:`ts/test/fixtures/valid-result.json` 由 Python 真实跑一遍分诊产出并提交
  入库(不是手写的假 JSON)。测试断言它通过 zod;另有若干篡改版本(枚举越界、confidence
  超范围、缺字段、多余字段、escalated 与 final_state 矛盾)断言被拒。
- `ts/src/cli.ts`:`triagebot-view <file.json>`,默认人类可读输出(升级/注入有醒目标记),
  `--json` 输出规范化 JSON;校验失败打印 zod 结构化错误路径,退出码 1。

## 10. 测试策略

pytest 覆盖:空/空白 body、超长 body、subject 超长、非法 order_id、非法 amount、
未知字段、注入文本(中英)、注入行为不变式、金额边界(999.99 / 1000.00 / 1000.01)、
置信度边界(0.59 / 0.60)、重试成功路径与重试失败路径、未知 order_id(REFUND 升级 /
TECHNICAL 不升级)、REFUND 政策一致性与覆盖、政策缺失、非法状态转移(跳级/终态出边/
重复转移)、优先级推导各分支、终态准入四条件、非支持语言。

vitest 覆盖:真实产物通过校验 + 五类篡改被拒 + schema 同步 + CLI 格式化与退出码。

所有测试离线。`MockDriver` 无网络;`AnthropicDriver` 不在测试中实例化。

## 11. 产品决策(已批准)

1. Priority 用 P0/P1/P2/P3,语义如 §3;priority 由确定性规则推导,LLM 不能决定;P0 一律人工。
2. Sentiment 四档:ANGRY / FRUSTRATED / NEUTRAL / SATISFIED。
3. 支持中英双语;其余语言归 OTHER 且 confidence ≤ 0.5。
4. 金额阈值 1000.00 USD,`>` 升级,等于不升级;单币种。
5. 置信度阈值 0.6,最多重试 1 次。
6. 注入:标记 + 强制升级人工;注入文本不得进入任何工具调用参数。
7. REFUND 政策冲突:政策覆盖 LLM 建议,继续自动处理,rationale 记录。
8. AUTO_RESOLVED 四条件如 §7。
9. 空/空白 body 边界拒绝;body ≤ 20000、subject ≤ 200,超限拒绝不截断。
10. 未知 order_id:继续分诊并写入 rationale;仅 REFUND/BILLING 因证据缺失升级。
11. CLI:位置参数 `<file.json>`,默认人类可读、`--json` 切 JSON,校验失败打印错误路径并退出码 1。

## 12. 技术决策(自行拍板,记入 README)

1. **包布局**:`src/triagebot/` 单包,按职责分文件(models/states/sanitize/tools/guards/
   engine/drivers)。理由:守卫必须能脱离引擎单独测试,分文件是这个要求的物理表达。
2. **金额用 `Decimal`** 而非 float。金钱比较用二进制浮点会让 `1000.00` 这种边界不可靠,
   而边界恰恰是本项目的核心考点。
3. **模型 `frozen=True`**:结论不可变,杜绝"下游偷偷改一下 escalated_to_human"。
4. **`extra="forbid"`**:未知字段是上游 schema 漂移的信号,应当报错而非静默吞掉。
5. **`escalated_to_human ⟺ final_state==ESCALATED` 用跨字段校验器**,而不是靠约定。
6. **zod schema 手写 + 同步测试**,不做代码生成(理由见 §9)。
7. **TS CLI 只吃单个结果对象**(产品未要求数组/stdin,YAGNI)。
8. **`order_id is None` 不算证据缺失**:产品决策 10 说的是"工具查不到",没查过就不算查不到。
9. **`AnthropicDriver` 惰性导入 SDK**:保证未安装依赖时离线测试与其它导入不受影响。
10. **依赖管理用 `uv` + `pyproject.toml`**,TS 侧 `npm` + `vitest` + `tsx`。
