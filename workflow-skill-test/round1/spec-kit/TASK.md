# TASK: TriageBot — 客服工单分诊 Agent

你要从零构建一个中等复杂度的 AI Agent 项目「TriageBot」:一个客服工单自动分诊系统。核心设计哲学:**LLM 负责理解,确定性规则负责裁决**——所有关键业务决策必须由类型系统与纯逻辑守卫,LLM 的输出永远只是"建议",可以被规则覆盖。

## 1. Python 侧(核心,pydantic v2)

### 1.1 数据模型
- `Ticket`:工单输入。字段至少含 `id`、`customer_id`、`subject`、`body`,可选 `order_id`、`amount`(涉诉金额)。
- `TriageResult`:分诊输出。至少含 `category`(枚举:BILLING / REFUND / TECHNICAL / ACCOUNT / OTHER)、`priority`、`sentiment`(枚举)、`confidence`(0~1)、`recommended_action`、`escalated_to_human`(bool)、`rationale`。
- 所有模型必须是严格校验的 pydantic v2 模型(禁止随意 `Any`;非法输入必须在边界被拒绝)。

### 1.2 工具(tools)
Agent 可调用两个工具,数据来自本地 JSON fixture(自行设计 fixture 内容):
- `get_order_status(order_id)` → 订单状态(含 not-found 情况)
- `get_refund_policy(category)` → 退款政策条目

### 1.3 LLM Driver 抽象
- 定义 `LLMDriver` 接口(Protocol 或 ABC):输入工单+工具上下文,输出"原始分类建议"(结构化)。
- 实现 `MockDriver`:**确定性**的关键词规则实现,供全部测试使用。
- 实现 `AnthropicDriver`:调用 Claude API 的真实实现,**只写代码,不要求实际运行**(测试中不得依赖网络)。

### 1.4 确定性守卫规则(核心考点,必须在 LLM 之外用纯逻辑实现,且优先级高于 LLM 建议)
1. **金额守卫**:`amount` 超过阈值的工单,无论 LLM 说什么,必须 `escalated_to_human=True`。
2. **置信度守卫**:LLM 建议 `confidence` 低于阈值时,带上工具上下文重试;若仍低于阈值,必须升级人工。
3. **退款政策一致性**:`category=REFUND` 的工单,`recommended_action` 必须先查询退款政策,且与政策一致(不允许 LLM 编造政策)。
4. **提示注入防御**:工单 `body` 中出现指令注入特征(如"ignore previous instructions"、试图让 agent 执行动作的文本)时,必须标记并保证注入文本永远不会改变分诊行为。

### 1.5 分诊流程状态机
工单处理必须显式建模为状态机:`NEW → ENRICHED(工具上下文已取)→ CLASSIFIED → AUTO_RESOLVED | ESCALATED`。非法状态转移必须在类型/校验层被拒绝。

## 2. TypeScript 侧(zod)

- 从 pydantic 模型导出 JSON Schema 到 `schema/` 目录(提供导出脚本)。
- 一个小型 TS CLI:读取 TriageBot 输出的分诊结果 JSON 文件,用 **zod** 校验后类型安全地格式化展示。
- 必须有测试证明:pydantic 产出的合法结果 JSON 能通过 zod 校验;篡改后的非法 JSON 会被拒绝。

## 3. 测试与验收(硬性)

- `pytest` 全部通过,覆盖至少:空 body、超长 body、注入攻击文本、金额阈值边界(等于/略超)、置信度阈值边界与重试路径、未知 order_id、REFUND 政策一致性、非法状态转移。
- TS 侧 `vitest`(或等价)通过,覆盖合法/非法 JSON 校验。
- `README.md`:架构说明(分层图/文字均可)、如何运行测试、设计决策清单。
- 所有测试离线可跑(不得访问网络)。

## 4. 未尽事宜

规格故意未写死的细节(如优先级档位、阈值具体数值、多语言支持、CLI 形态等):属于**产品决策**的,向产品负责人提问;属于**技术决策**的,自行决定并在 README 的决策清单中记录。
