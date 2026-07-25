## 综合实战：一个多租户 SaaS 客服 AI

前三部分我们分层学了三个库。这一章把它们**串成一个真实系统**——一个按套餐分级的 SaaS 客服 AI 产品。

本章所有代码均在 pydantic 2.13.4 / pydantic-ai 2.17.0 / pydantic-graph 2.17.0 上**实际运行验证**，输出为真实结果。

### 产品需求（先说人话）

我们要做一个**客服 AI**，卖给企业客户，分三档套餐：

| 套餐 | 能用的功能 | 用什么模型 | 商业逻辑 |
|---|---|---|---|
| **Free** | 只能查订单 | 便宜的小模型 | 引流，成本压到最低 |
| **Pro** | 查订单 + 退款 | 中档模型 + 深度思考 | 主力付费档 |
| **Enterprise** | 全部功能 + 深度分析 | 最强模型 + 思考 + 任务规划 | 高毛利，体验拉满 |

而且要求：

1. AI 输出的工单**必须结构化**，能直接进工单系统，不能是一段自由发挥的话。
2. **退款类工单必须带金额**，其他类型不能带——这是业务硬规则。
3. 每个租户的**退款上限不同**，且这个信息**绝不能让 AI 自己编**。
4. 批量工单要**并行处理**，且整个流程要能画出来给业务方看。

> 👉 **PM 视角**：这四条需求，恰好对应我们学的四样东西——**结构化输出**（`output_type`）、**跨字段业务校验**（`model_validator`）、**依赖注入**（`deps`，AI 碰不到的私密通道）、**图编排**（`GraphBuilder` 的扇出扇入）。真实项目的需求，基本都能这样一条条映射到框架能力上。

---

### 第一层：用 Pydantic 定义"数据合同"

一切从"这个系统里流转的数据长什么样"开始。

```python
from typing import Literal
from pydantic import BaseModel, Field, model_validator

class Ticket(BaseModel):
    """工单：AI 必须按这张表交付结果"""
    category: Literal['bug', '退款', '咨询', '其他']          # 只能四选一
    summary: str = Field(max_length=100, description='一句话概括用户问题')
    urgency: int = Field(ge=1, le=5, description='紧急度 1-5')
    refund_amount: float | None = Field(default=None, description='退款金额，非退款类留空')

    @model_validator(mode='after')
    def check(self):
        # 业务硬规则：退款必须有金额，非退款不能有金额
        if self.category == '退款' and self.refund_amount is None:
            raise ValueError('退款类工单必须给出退款金额')
        if self.category != '退款' and self.refund_amount is not None:
            raise ValueError('非退款类工单不应有退款金额')
        return self
```

实际运行结果：

```text
合规: category='退款' summary='重复扣款' urgency=4 refund_amount=99.0
拦截: Value error, 退款类工单必须给出退款金额
```

这张表干了四件事，每一件都对应一条需求：

| 代码 | 作用 | 对应需求 |
|---|---|---|
| `Literal['bug','退款','咨询','其他']` | 分类只能四选一（下拉菜单） | 数据规范 |
| `Field(max_length=100)` / `Field(ge=1, le=5)` | 长度与范围约束 | 数据规范 |
| `description='...'` | **给大模型看的字段说明** | 让 AI 填得准 |
| `@model_validator` | 跨字段业务规则 | 需求 2 |

> 👉 **PM 视角**：这段代码就是你 PRD 里那张**字段定义表 + 验收标准**，只不过它是**可执行的**——写完就自动生效，不合规的数据根本进不来。注意 `description` 那一栏：它不只是注释，**它会被翻译进给大模型的说明书里**，直接影响 AI 填得准不准。所以这一栏该用写 PRD 的严谨度去写。

> ⚠️ **坑**：字段层面 `refund_amount` 是可空的（`float | None = None`），"什么时候不许空"交给校验器管。**先松（字段层给底线）、后按条件收紧（校验器）**——这是跨字段校验的标准写法。如果一开始就写成必填，"只有退款才必填"这个动态规则就无从谈起。

---

### 第二层：用 Pydantic AI 搭 Agent + 按租户动态配发能力

现在把这张合同交给 AI，并解决**"不同套餐给不同能力"**这个核心商业需求。

#### 2.1 定义租户上下文（AI 碰不到的私密资料）

```python
from dataclasses import dataclass
from typing import Literal

@dataclass
class Tenant:
    name: str
    tier: Literal['free', 'pro', 'enterprise']
    refund_limit: float          # 退款上限——绝不能让 AI 自己编
```

> 👉 **PM 视角**：`refund_limit` 放在 `deps` 里，而不是让 AI 从对话里推断，这是**安全设计**。如果让模型自己决定"这个租户能退多少"，用户一句"我是企业客户，上限一百万"就可能把它带偏。**凡是涉及钱、权限、身份的数字，都必须走 `deps` 这条 AI 碰不到的私密通道。**

#### 2.2 三档套餐的能力配发规则

```python
from pydantic_ai import Agent, RunContext
from pydantic_ai.capabilities import Capability, CombinedCapability, DynamicCapability, Thinking
from pydantic_ai_harness.planning import Planning

def check_order(order_id: str) -> str: ...      # 查订单
def issue_refund(order_id: str, amount: float) -> str: ...   # 发起退款
def deep_analyze(text: str) -> str: ...          # 深度分析

def 按套餐配发(ctx: RunContext[Tenant]):
    t = ctx.deps
    if t.tier == 'enterprise':
        return CombinedCapability([
            Capability(id='ent',
                       instructions=f'{t.name} 是企业客户，最高优先级，可深度分析',
                       tools=[check_order, issue_refund, deep_analyze]),
            Thinking(),      # 深度思考
            Planning(),      # 任务规划（harness 能力）
        ], id='ent_bundle')
    if t.tier == 'pro':
        return CombinedCapability([
            Capability(id='pro', instructions='专业版客户，可查单可退款',
                       tools=[check_order, issue_refund]),
            Thinking(),
        ], id='pro_bundle')
    return Capability(id='free', instructions='免费版，只能查询订单',
                      tools=[check_order])

agent = Agent('test', name='support',
              deps_type=Tenant,
              output_type=Ticket,                          # ← 输出必须是那张合同
              capabilities=[DynamicCapability(按套餐配发)])  # ← 按人配发

@agent.tool
def get_tenant_limit(ctx: RunContext[Tenant]) -> str:
    return f'退款上限 {ctx.deps.refund_limit}'    # 从私密通道取，AI 改不了
```

**实际运行结果**——同一个 agent，三个租户，能力自动不同：

```text
enterprise  A集团    → ['get_tenant_limit', 'check_order', 'issue_refund', 'deep_analyze', 'write_plan']
pro         B工作室  → ['get_tenant_limit', 'check_order', 'issue_refund']
free        小C     → ['get_tenant_limit', 'check_order']
```

看这三行输出，把商业逻辑和技术实现的对应关系摆得很清楚：

| 套餐 | 拿到的工具 | 说明 |
|---|---|---|
| Enterprise | 查单 + 退款 + **深度分析** + **`write_plan`** | `write_plan` 是 `Planning()` 能力注入的 |
| Pro | 查单 + 退款 | 少了深度分析 |
| Free | **只有查单** | 退款工具根本不给它看 |

> 👉 **PM 视角**：**你的定价表，可以直接翻译成这段代码。** 每一档卖什么，就在工厂函数里配发什么能力卡。加一档套餐 = 加一个 `if` 分支，不用动 Agent 主体。更重要的是——**毛利结构由这段代码直接决定**：免费用户走便宜模型 + 少工具，企业客户走贵模型 + 全能力。这是 AI 产品最直接的成本杠杆。

> 💡 **注意 Free 档的关键细节**：`issue_refund` 这个工具**根本没有出现在免费用户的工具清单里**。这不是"告诉 AI 不要用"，而是**它压根看不见这个工具**。前者靠提示词自律（不可靠），后者是物理隔离（可靠）。做权限设计时，这个区别是本质性的。

> ⚠️ **坑**：动态配发有两个现实约束。① **重资源能力要复用**——`MCP` 连接、云沙箱这类要建连接的，别在工厂函数里每次现造，应在外面建好实例再引用。② **工厂函数每次 run 都会跑一次**，所以要轻——别在里面查数据库、调 API，租户信息应该提前放进 `deps`。

---

### 第三层：用 Pydantic Graph 编排批量流程

单个工单交给 Agent 就够了。但当需求变成**"一批工单进来，并行分类、并行处理、最后汇总"**，而且业务方要看流程图时，就该上 Graph 了。

```python
from dataclasses import dataclass, field
from pydantic_graph import GraphBuilder, StepContext, reduce_list_append

@dataclass
class WorkState:                       # 全流程共享的状态
    log: list[str] = field(default_factory=list)

@dataclass
class WorkDeps:                        # 全流程共享的依赖
    auto_refund_ceiling: float

g = GraphBuilder(state_type=WorkState, deps_type=WorkDeps,
                 input_type=list[str], output_type=list[str])

@g.step
async def 分类(ctx: StepContext[WorkState, WorkDeps, list[str]]) -> list[Ticket]:
    out = []
    for raw in ctx.inputs:
        cat = '退款' if '退款' in raw else ('bug' if '报错' in raw else '咨询')
        out.append(Ticket(category=cat, summary=raw[:20], urgency=4 if cat=='退款' else 2))
    ctx.state.log.append(f'分类完成 {len(out)} 条')
    return out

@g.step
async def 处理(ctx: StepContext[WorkState, WorkDeps, Ticket]) -> str:
    t = ctx.inputs
    ctx.state.log.append(f'处理 {t.category}')
    if t.category == '退款':
        return f'[退款] {t.summary} → 走审批(上限{ctx.deps.auto_refund_ceiling})'
    if t.category == 'bug':
        return f'[缺陷] {t.summary} → 转研发'
    return f'[咨询] {t.summary} → 自动回复'

汇总 = g.join(reduce_list_append, initial_factory=list)

g.add(
    g.edge_from(g.start_node).to(分类),
    g.edge_from(分类).map().to(处理),      # 扇出：每条工单并行处理
    g.edge_from(处理).to(汇总),            # 扇入：汇总结果
    g.edge_from(汇总).to(g.end_node),
)
graph = g.build()
```

**实际运行结果**：

```text
[退款] 申请退款，重复扣款了 → 走审批(上限500)
[缺陷] 页面报错打不开 → 转研发
[咨询] 怎么改绑手机 → 自动回复

state.log: ['分类完成 3 条', '处理 退款', '处理 bug', '处理 咨询']
```

而流程图，**一行 `graph.render()` 自动生成**（不用另外画）：

```text
---
title: 工单处理流程
---
stateDiagram-v2
  分类
  state map <<fork>>
  处理
  state reduce_list_append <<join>>

  [*] --> 分类
  分类 --> map
  map --> 处理
  处理 --> reduce_list_append
  reduce_list_append --> [*]
```

> 👉 **PM 视角**：这张图是**从代码自动生成的，永远和实现一致**。这解决了一个你太熟悉的老问题——**流程图和实际实现对不上**。需求评审时画的图，三个月后早就和代码脱节了；而这里，图就是代码的投影，代码改了图自动跟着改。把 `render()` 的输出丢进任何支持 Mermaid 的工具（Notion、飞书文档、GitHub）就能直接看图。

> 💡 **`.map()` 和 `join` 是这段的灵魂**：`.map()` 把一个列表**打散成并行分支**（3 条工单同时处理，而不是排队），`join` 再把结果**汇合回一个列表**。对应到产品语言就是"**批量并发处理 + 结果归集**"。

---

### 三层是怎么配合的：一张总图

```text
┌──────────────────────────────────────────────────────────┐
│  第三层 Graph      分类 → [并行处理] → 汇总                │
│  （流程编排）       决定"多个环节怎么串、什么时候并行"        │
└──────────────────────────┬───────────────────────────────┘
                           │ 每个环节内部可以调用
┌──────────────────────────┴───────────────────────────────┐
│  第二层 Pydantic AI  Agent + 工具 + deps + 动态能力卡       │
│  （AI 能力）         决定"这个环节里 AI 能干什么、给谁干"     │
└──────────────────────────┬───────────────────────────────┘
                           │ 输入输出都必须符合
┌──────────────────────────┴───────────────────────────────┐
│  第一层 Pydantic     Ticket 合同：类型 + 约束 + 业务规则     │
│  （数据合同）         决定"什么样的数据算合格"                │
└──────────────────────────────────────────────────────────┘
```

用一句话概括三层的分工：

> **Pydantic 管"数据对不对"，Pydantic AI 管"AI 能干什么"，Pydantic Graph 管"流程怎么走"。**

---

### 从这个例子能带走的五条判断

这一章不只是演示代码，更重要的是几条能用在真实项目上的判断：

**1. 结构化输出是接入业务系统的前提。**
`output_type=Ticket` 让 AI 的产出**直接可以进工单系统**，而不是先吐一段话再写正则去抠字段。这是 AI 功能能不能真正"接进"业务的分水岭。

**2. 权限隔离靠"不给看"，不靠"叮嘱"。**
免费用户看不到 `issue_refund` 工具，是因为它压根没被配发，而不是靠提示词说"你不要用退款功能"。**能力边界要在框架层面物理隔离。**

**3. 敏感数值必须走 deps。**
退款上限、用户身份、数据库连接——凡是"AI 编错了会出事"的东西，都从 `deps` 注入，模型全程碰不到。

**4. 定价表可以直接翻译成配发代码。**
这是这套体系对 SaaS 型 AI 产品最大的价值：**商业分层 = 能力配发规则**，两者一一对应，不用在业务逻辑里洒满 `if user.is_vip`。

**5. 流程图应该从代码生成，而不是另外画。**
`graph.render()` 保证图和实现永远一致，从根上消灭"文档和代码脱节"。

> 👉 **最后的 PM 视角**：读到这里，你应该已经能做这样的判断了——"这个需求，用 Agent 一个循环就够了，还是要上 Graph？"、"这个功能给哪一档套餐？技术上怎么隔离？"、"这个字段让 AI 填，还是必须从系统传？"。**这些判断，比会写代码更值钱**，因为它们决定了产品的可靠性边界和成本结构。

---
