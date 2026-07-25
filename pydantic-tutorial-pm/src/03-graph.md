## 第三部分：Pydantic Graph —— 把流程图变成能跑的引擎

> **读者定位**：你已经理解了 Pydantic 的 `BaseModel`（把数据结构写成类），也理解了 Pydantic AI 的 `Agent` / `Tools` / `Capabilities`（把一个会用工具的智能体包起来）。这一部分讲的是**第三层**：当业务流程复杂到 Agent 那个"想 → 调工具 → 再想"的单一循环装不下时，你需要一张**显式的流程图**。
>
> **本文所有代码都在 `pydantic-graph 2.17.0` + `pydantic-ai 2.17.0` 上实跑验证过**，贴出来的输出全部是真实运行结果，不是手写的。

---

### 0. 先说三件事，省得你踩坑

**第一件：这个版本是重写过的，网上的教程基本都过时了。**

`pydantic-graph` 在 2.x 做了一次架构重写，引入了 **builder（构建器）模式**。如果你在网上搜到的代码长这样：

```python
# ❌ 这是旧版写法，2.17.0 跑不起来
graph = Graph(nodes=[NodeA, NodeB])
graph.mermaid_code()
graph.next(node, persistence=...)
```

那就是旧版的。下面这张表列出**本版本已经删掉、绝对不要写**的东西：

| 已删除的东西 | 说明 | 替代方案 |
|---|---|---|
| `pydantic_graph.persistence` 整个模块 | 没有内置持久化 / 中断续跑 | 自己基于 `iter()` + `override_next()` 做，或用官方的 durable execution 方案 |
| `pydantic_graph.mermaid` 整个模块 | 画图模块没了 | `Graph.render()` |
| `graph.mermaid_code()` / `mermaid_image()` / `mermaid_save()` | 三个画图方法都没了 | `Graph.render()` |
| `Graph(nodes=[A, B])` 直接构造 | 不能直接 new 一个 Graph | `GraphBuilder(...)` → `.build()` |
| `graph.next(node, persistence=...)` | 没有 persistence 参数 | `GraphRun.next()` / `GraphRun.override_next()` |
| `pydantic_graph.beta.*` | beta 命名空间没了 | 全部提升到顶层：`from pydantic_graph import GraphBuilder` |

实测确认：

```python
import importlib
for m in ['pydantic_graph.persistence', 'pydantic_graph.mermaid', 'pydantic_graph.beta']:
    try:
        importlib.import_module(m)
        print(m, '-> 存在')
    except ImportError as e:
        print(m, '-> 不存在:', e)
```

```text
pydantic_graph.persistence -> 不存在: No module named 'pydantic_graph.persistence'
pydantic_graph.mermaid -> 不存在: No module named 'pydantic_graph.mermaid'
pydantic_graph.beta -> 不存在: No module named 'pydantic_graph.beta'
```

**第二件：官方自己都劝你先别用。**

官方文档 `graph.md` 的开头有一段很有名的警告，原话是：

> "Don't use a nail gun unless you need a nail gun.
> If Pydantic AI agents are a hammer, and multi-agent workflows are a sledgehammer, then graphs are a nail gun:
> - sure, nail guns look cooler than hammers
> - but nail guns take a lot more setup than hammers
> - and nail guns don't make you a better builder, they make you a builder with a nail gun"
>
> 翻译：**别为了用钉枪而用钉枪**。Agent 是锤子，多 Agent 协作是大锤，图是钉枪。钉枪确实看起来更酷，但它需要多得多的前期搭建，而且它不会让你成为更好的工匠，只会让你成为一个"手里拿着钉枪的工匠"。

这段话本身就是选型建议。第九节我会展开讲什么时候该用。

**第三件：这个库不依赖 pydantic-ai。**

官方 README 原话：

> "This library is developed as part of Pydantic AI, however it has **no dependency on `pydantic-ai`** or related packages and can be considered as a **pure graph-based state machine library**. You may find it useful whether or not you're using Pydantic AI or even building with GenAI."

翻译：这是一个**纯粹的图 / 有限状态机库**。它是在做 Pydantic AI 的过程中顺手做出来的，但它跟大模型一点关系都没有——你完全可以用它来编排一个纯 CRUD 的订单流程。

> 👉 **PM 视角**：把它想成一个**开源的、代码版的工作流引擎**（类似 Camunda、Airflow、钉钉审批流后台的那一层），只不过流程定义不是拖拽出来的 XML/JSON，而是 Python 类型注解。你在 PRD 里画的那张泳道图，可以几乎一比一翻译成这个库的代码。

**第四件：本章代码里出现 `await` 或 `async for` 的片段，都要放进异步函数里跑。**

为了突出重点，本章有些代码片段只贴了关键几行。凡是里面出现 `await xxx` 或 `async for ... in ...` 的，**直接复制到 `.py` 文件运行会报 `SyntaxError`**——Python 不允许在文件最外层写 `await`。正确做法是套一层：

```python
import asyncio

async def main():
    result = await graph.run(inputs=...)      # ← 片段里的 await 代码放这里
    print(result)
    # async for 的片段同理，也放在这个函数里

asyncio.run(main())                            # ← 用它启动
```

> ⚠️ **坑**：反过来，**`graph.run_sync()` 不能放进 `async def` 里**——它内部会自己启动一个事件循环，而 async 函数里已经有一个在跑了，会直接报错。一句话记法：**同步环境用 `run_sync()`，异步环境用 `await run()`，两者不能混。** 详见 2.4 节的实测报错。

---

## 一、架构总览

### 1.1 它解决什么问题：Agent 的单循环装不下的时候

回想一下第二部分讲的 Agent。Agent 的执行模型本质上是一个**固定的循环**：

```text
用户输入 → 请求模型 → 模型说"我要调工具" → 调工具 → 把结果塞回去 → 再请求模型 → ...
                                 ↓
                          模型说"我说完了" → 结束
```

这个循环有个特点：**下一步做什么，是模型自己决定的**。这非常灵活，但也意味着：

| 你想要的 | Agent 循环能给你吗 |
|---|---|
| "先查库存，再扣款，最后发货" 严格按这个顺序 | ❌ 模型可能乱序，可能漏步 |
| "3 个供应商同时报价，谁先回用谁的" | ❌ 一个循环里没法真并行 |
| "金额 > 1 万必须走总监审批，没得商量" | ❌ 模型可能被话术绕过去 |
| "第 3 步失败了，自动转人工，不要重试" | ❌ 错误处理散在各个工具里 |
| "把整条流程画给业务方看" | ❌ 循环没有形状，画不出来 |

`pydantic-graph` 解决的就是这一类问题：**当"下一步做什么"应该由你（产品/工程）决定，而不是由模型决定的时候。**

> 👉 **PM 视角**：这就是"AI 自由发挥"和"SOP 强约束"的分界线。
> - 客服问答、写文案、查资料 → 交给 Agent 自由发挥
> - 退款审批、风控放款、订单履约 → 必须走图，每一步都要可审计、可回溯、可画给合规看
>
> 更实际的判断标准：**如果这个流程失败了，需要有人来背锅，那就用图。**

### 1.2 核心概念全景（先列一遍，后面逐个讲）

这个库一共就这么些概念，先混个脸熟：

| 概念 | Python 名字 | 一句话 | 生命周期 |
|---|---|---|---|
| 构建器 | `GraphBuilder` | 你用它来"画"图 | 构建期（进程启动时） |
| 编译后的图 | `Graph` | `builder.build()` 的产物，不可变，可复用 | 构建期 → 长期存活 |
| 一次执行 | `GraphRun` | 图跑一次的上下文，`graph.iter()` 产出 | 运行期（每次请求一个） |
| 步骤（函数式） | `Step` / `@g.step` | 一个 async 函数就是一个节点 | 构建期定义 |
| 步骤（声明式） | `BaseNode` 子类 | 一个 dataclass + `run()` 就是一个节点 | 构建期定义 |
| 流式步骤 | `@g.stream` | 一个 async 生成器节点，边产边下发 | 构建期定义 |
| 起点 / 终点 | `StartNode` / `EndNode` | 图的入口和出口，`g.start_node` / `g.end_node` | 内置 |
| 结束信号 | `End` | 节点里 `return End(x)` 表示整张图结束 | 运行期 |
| 分支 | `Decision` / `g.decision()` | if-elif-else 的图形化版本 | 构建期定义 |
| 分支条件 | `g.match()` / `g.match_node()` | 一个 `case` 分支 | 构建期定义 |
| 扇出 | `Fork`（由 `.map()` / `.broadcast()` 生成） | 一变多，并行 | 自动生成 |
| 扇入 | `Join` / `g.join(reducer)` | 多变一，汇总 | 构建期定义 |
| 汇总函数 | `ReducerFunction` | 告诉 Join 怎么合并结果 | 构建期定义 |
| 状态 | `StateT` | 整条流程共享的可变数据（订单、审批单） | 运行期，每次 run 一份 |
| 依赖 | `DepsT` | 注入的外部资源（数据库、API 客户端） | 运行期，每次 run 传入 |
| 步骤上下文 | `StepContext` | `@g.step` 拿到的 `ctx`，有 `.state/.deps/.inputs` | 运行期 |
| 节点上下文 | `GraphRunContext` | `BaseNode.run()` 拿到的 `ctx`，只有 `.state/.deps` | 运行期 |
| 错误标记 | `ErrorMarker` | 节点抛异常时的信封，允许你接管 | 运行期 |
| 结束标记 | `EndMarker` | 图跑完的信封，带最终输出 | 运行期 |

用 `python -c "import pydantic_graph; print(pydantic_graph.__all__)"` 可以看到完整导出列表：

```text
('BaseNode', 'End', 'GraphRunContext', 'Edge', 'GraphBuilder', 'Graph', 'GraphRun',
 'GraphTask', 'GraphTaskRequest', 'EndMarker', 'ErrorMarker', 'JoinItem', 'Step',
 'StepContext', 'StepNode', 'StartNode', 'EndNode', 'Fork', 'Decision', 'Join',
 'JoinNode', 'ReducerContext', 'ReducerFunction', 'ReduceFirstValue',
 'reduce_dict_update', 'reduce_list_append', 'reduce_list_extend', 'reduce_null',
 'reduce_sum', 'TypeExpression', 'GraphSetupError', 'GraphRuntimeError')
```

### 1.3 ASCII 架构图

```text
┌──────────────────────────────────────────────────────────────────────────┐
│  构建期（进程启动时跑一次，之后不再变）                                     │
│                                                                          │
│    GraphBuilder(state_type=…, deps_type=…, input_type=…, output_type=…)  │
│         │                                                                │
│         ├── @g.step      函数式节点      ──┐                              │
│         ├── @g.stream    流式节点        ──┤                              │
│         ├── g.node(X)    声明式 BaseNode ──┼─→ 节点集合                    │
│         ├── g.join(f)    汇总节点        ──┤                              │
│         └── g.decision() 分支节点        ──┘                              │
│                                                                          │
│    g.add(                                                                │
│      g.edge_from(A).to(B),              ← 显式连线                        │
│      g.edge_from(A).map().to(B),        ← 扇出                            │
│      g.edge_from(A).to(B, C, D),        ← 广播                            │
│      g.edge_from(A).to(g.decision()…),  ← 分支                            │
│      g.node(SomeBaseNode),              ← 连线由返回类型注解自动推导 ★     │
│    )                                                                     │
│         │                                                                │
│         ▼                                                                │
│    g.build()   ── 校验结构 / 展平路径 / 归一化 fork / 计算 join 的父 fork   │
│         │                                                                │
│         ▼                                                                │
│  ┌───────────────────────────────────────────────────────────────┐       │
│  │  Graph（不可变，线程安全，可以放在模块级全局变量里复用）          │       │
│  │    .run(state=, deps=, inputs=)      → 跑完拿结果               │       │
│  │    .run_sync(...)                     → 同上，同步版本           │       │
│  │    .iter(...)                         → 逐步执行，能插手         │       │
│  │    .render(title=, direction=)        → 输出 mermaid 源码        │       │
│  └───────────────────────────────────────────────────────────────┘       │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  运行期（每次业务请求一份）                                                │
│                                                                          │
│    GraphRun                                                              │
│      .state    ← 这次跑的可变状态（订单对象）                              │
│      .deps     ← 这次跑注入的资源（DB 连接）                               │
│      .next_task    ← 下一步要跑什么（可以偷看）                            │
│      .output       ← 跑完了没有，输出是啥                                  │
│      .next()       ← 手动推进一步                                          │
│      .override_next()  ← 改写下一步（人工干预 / 错误恢复）★                 │
│                                                                          │
│    执行调度器内部：                                                        │
│      active_tasks      正在跑的任务（并行时有多个）                        │
│      active_reducers   正在累积的 Join 状态                                │
│      fork_stack        每个任务属于哪次 fork（用来判断 join 什么时候满）    │
└──────────────────────────────────────────────────────────────────────────┘
```

> 👉 **PM 视角**：这个"构建期 / 运行期"的分离，对应的是**流程模板**和**流程实例**。
> - `Graph` = 你在审批流后台配好的那张"报销审批流模板"，配一次，全公司用
> - `GraphRun` = 小王今天提交的那一张具体的报销单，走到哪一步了，各自独立
>
> 这跟钉钉/飞书审批的模型是完全一样的。

### 1.4 最独特的设计：边由返回类型注解推导

这是 `pydantic-graph` 跟市面上所有其他工作流引擎最不一样的地方，**必须讲透**。

官方 README 原话：

> "`pydantic-graph` allows you to define graphs using standard Python syntax. In particular, **edges are defined using the return type hint of nodes**."

意思是：**节点之间的连线，不是你手动连的，而是从函数的返回类型注解里读出来的。**

看这段代码：

```python
@dataclass
class DivisibleBy5(BaseNode[None, None, int]):
    foo: int

    async def run(self, ctx: GraphRunContext) -> Increment | End[int]:
        #                                        ^^^^^^^^^^^^^^^^^^^^
        #                                        这一行就是"连线"
        if self.foo % 5 == 0:
            return End(self.foo)
        else:
            return Increment(self.foo)
```

那个 `-> Increment | End[int]` 不只是给类型检查器看的注释。`pydantic-graph` 会在 `build()` 的时候**用 `get_type_hints()` 把它读出来**，然后：

- 看到 `Increment` → 画一条 `DivisibleBy5 ──→ Increment` 的边
- 看到 `End[int]` → 画一条 `DivisibleBy5 ──→ [终点]` 的边
- 因为有两个目标 → 自动插入一个菱形的 **decision（判定）节点**

所以上面这几行代码画出来是：

```text
  DivisibleBy5 --> decision
  decision --> Increment
  decision --> [*]
```

**这个设计的三个后果：**

| 后果 | 好处 | 代价 |
|---|---|---|
| 流程图和代码永远一致 | 不可能出现"图改了代码没改" | 改流程必须改类型注解 |
| 类型检查器帮你查流程错误 | 你 `return` 了一个没在注解里的节点，mypy/pyright 直接报错 | 必须写完整注解，不能偷懒写 `-> Any` |
| 图能自动画出来 | `render()` 直接出 mermaid | 注解写错，图就画错 |

> 👉 **PM 视角**：这解决的是工作流引擎最经典的一个痛点——**流程图和实际代码对不上**。
>
> 传统做法是：PM 在 Visio 里画一张图，工程师照着写代码，三个月后代码改了五遍，那张图还躺在 Confluence 里一动没动，谁也不敢信。
>
> 这里的做法是：**图就是代码本身**。工程师改了 `-> Increment | End[int]` 这行，`render()` 出来的图立刻变。你随时可以让工程师跑一行 `print(graph.render())`，把结果丢进任何支持 mermaid 的工具（飞书文档、Notion、GitHub），看到的就是当前线上真实跑的流程。

**⚠️ 但这个推导只对 `BaseNode` 完整生效，对 `@g.step` 只部分生效。** 这是一个真实存在的坑，我在第三节和第五节会单独展开，这里先记住结论：

| 节点写法 | 返回单个节点类型 | 返回多个节点类型的 union |
|---|---|---|
| `BaseNode` + `g.node(X)` | ✅ 自动连线 | ✅ 自动生成 decision，运行时按**实际返回对象的类**分流 |
| `@g.step` | ✅ 自动连线 | ⚠️ 会生成一个**运行时必然报错**的 decision，需要绕开 |

### 1.5 两条构图路线

这个库提供了两套写节点的语法，**可以混着用**：

```text
路线 A：函数式（builder 风格）              路线 B：声明式（面向对象风格）
────────────────────────────              ────────────────────────────
@g.step                                   @dataclass
async def check_stock(ctx) -> int:        class CheckStock(BaseNode[S, D, R]):
    return ctx.inputs                         order_id: int
                                              async def run(self, ctx) -> Charge:
连线：g.edge_from(A).to(B) 手动写               return Charge(self.order_id)

上下文：StepContext                        连线：写在 -> 返回注解里，g.node() 注册
  .state / .deps / .inputs                上下文：GraphRunContext
                                            .state / .deps（没有 .inputs）
数据怎么传：通过边传递                       数据怎么传：塞进下一个节点的构造参数
```

第三节会详细对比。

---

## 二、最小可运行例子：从 4 数到 5

这是官方 README 里的例子，我把它完整跑了一遍。功能很蠢（从一个数开始，一直加 1 直到能被 5 整除），但它把**所有核心概念都用上了**：起点、函数式 step、声明式 BaseNode、分支、循环、终点。

### 2.1 完整代码

```python
from __future__ import annotations

from dataclasses import dataclass

from pydantic_graph import BaseNode, End, GraphBuilder, GraphRunContext, StepContext


@dataclass
class DivisibleBy5(BaseNode[None, None, int]):
    foo: int

    async def run(self, ctx: GraphRunContext) -> Increment | End[int]:
        if self.foo % 5 == 0:
            return End(self.foo)
        else:
            return Increment(self.foo)


@dataclass
class Increment(BaseNode):
    foo: int

    async def run(self, ctx: GraphRunContext) -> DivisibleBy5:
        return DivisibleBy5(self.foo + 1)


g = GraphBuilder(input_type=int, output_type=int)


@g.step
async def start(ctx: StepContext[None, None, int]) -> DivisibleBy5:
    return DivisibleBy5(ctx.inputs)


g.add(
    g.node(DivisibleBy5),
    g.node(Increment),
    g.edge_from(g.start_node).to(start),
)

fives_graph = g.build()


async def main():
    result = await fives_graph.run(inputs=4)
    print(result)
```

实跑输出：

```text
5
```

再跑一次 `fives_graph.run_sync(inputs=12)`：

```text
15
```

（12 → 13 → 14 → 15，15 能被 5 整除，结束。）

### 2.2 逐行拆解

| 行 | 代码 | 在干嘛 | 为什么这么写 |
|---|---|---|---|
| 1 | `from __future__ import annotations` | 让所有类型注解变成"延迟求值"的字符串 | **必须写**。因为 `DivisibleBy5` 的返回注解里引用了 `Increment`，而 `Increment` 定义在它下面。没这一行，Python 会在定义 `DivisibleBy5` 时就报 `NameError` |
| 2 | `@dataclass class DivisibleBy5(BaseNode[None, None, int])` | 定义一个声明式节点 | 三个泛型参数依次是：**State 类型**（这里没状态，`None`）、**Deps 类型**（没依赖，`None`）、**这个节点如果 `return End(x)`，`x` 的类型**（`int`） |
| 3 | `foo: int` | 节点的输入数据 | dataclass 的字段就是节点的"参数"。上游节点通过 `DivisibleBy5(某个值)` 把数据传进来 |
| 4 | `async def run(self, ctx: GraphRunContext) -> Increment \| End[int]` | 节点的业务逻辑 + **出边定义** | 返回注解读作："这个节点要么去 `Increment`，要么结束整张图并吐出一个 int" |
| 5 | `class Increment(BaseNode)` | 第二个节点，泛型全省略 | `BaseNode` 三个泛型都有默认值。这个节点不用状态、不用依赖、也不会 `return End(...)`，所以三个都能省 |
| 6 | `g = GraphBuilder(input_type=int, output_type=int)` | 创建构建器 | 声明"整张图接受一个 int，最终吐出一个 int" |
| 7 | `@g.step async def start(ctx: StepContext[None, None, int]) -> DivisibleBy5` | 一个函数式节点 | `StepContext` 的三个泛型是 **State / Deps / 这个 step 的输入类型**。它的活儿就是把图的原始输入 `ctx.inputs`（一个裸 int）包装成第一个 `BaseNode` |
| 8 | `g.node(DivisibleBy5)` | 把 BaseNode 注册进图 | 注册的**同时**会读它 `run()` 的返回注解，自动建出边。这一步是"注册 + 连线"二合一 |
| 9 | `g.edge_from(g.start_node).to(start)` | 手动连一条边 | 从图的入口连到 `start` 这个 step。`g.start_node` 是内置的虚拟起点 |
| 10 | `g.build()` | 编译 | 校验结构（比如有没有孤岛节点）、展平路径、算 fork/join 关系，返回不可变的 `Graph` |
| 11 | `await fives_graph.run(inputs=4)` | 执行 | 返回值就是 `End(x)` 里那个 `x` |

**为什么需要 `start` 这个 step？**

因为图的输入是一个裸 `int`（4），但图里流转的是 `BaseNode` 对象。`start` 是个适配器，负责把 `4` 包装成 `DivisibleBy5(4)`。

**为什么 `Increment` 不用注册出边？**

注册了——`g.node(Increment)` 读到它的返回注解是 `-> DivisibleBy5`（单个类型），于是自动画了一条 `Increment ──→ DivisibleBy5` 的边。这条边构成了**循环**。

### 2.3 它画出来长什么样

`print(fives_graph.render())` 的真实输出：

```text
stateDiagram-v2
  start
  DivisibleBy5
  state decision <<choice>>
  Increment

  [*] --> start
  start --> DivisibleBy5
  DivisibleBy5 --> decision
  decision --> Increment
  decision --> [*]
  Increment --> DivisibleBy5
```

读法：

- `[*]` 是起点/终点
- `state decision <<choice>>` 是那个菱形的判定节点（**你没写它，是从 `-> Increment | End[int]` 自动生成的**）
- `Increment --> DivisibleBy5` 那条边形成了回路

把这段文本粘进任何支持 mermaid 的编辑器，就能看到图。

> 👉 **PM 视角**：注意这里的因果关系。工程师没有画图，他只写了业务逻辑和类型注解，图是**副产品**。这意味着流程图的维护成本是**零**——它不可能过时，因为它是从跑着的代码里生成的。
>
> 你可以要求团队把 `print(graph.render())` 的结果做成 CI 的一环，每次 PR 自动更新文档里的流程图。流程变更评审从此有据可依。

### 2.4 三个执行入口

`Graph` 上只有这几个公开方法：

```python
from pydantic_graph import Graph
print([a for a in dir(Graph) if not a.startswith('_')])
```

```text
['get_parent_fork', 'is_final_join', 'iter', 'render', 'run', 'run_sync']
```

| 方法 | 用途 | 注意 |
|---|---|---|
| `await graph.run(state=, deps=, inputs=)` | 跑完拿结果，**最常用** | 异步 |
| `graph.run_sync(state=, deps=, inputs=)` | 同上，同步版本 | ⚠️ **不能在 async 环境里调用** |
| `async with graph.iter(...) as run:` | 逐步执行，能观察和插手 | 第六节详讲 |
| `graph.render(title=, direction=)` | 出 mermaid 源码 | 第七节详讲 |

> ⚠️ **坑**：`run_sync` 内部是 `loop.run_until_complete(...)`，在已经有事件循环的地方调用会直接炸。实测：
>
> ```python
> async def main():
>     graph.run_sync()   # 在 async 函数里调 run_sync
> asyncio.run(main())
> ```
> ```text
> RuntimeError : This event loop is already running
> ```
>
> 规则很简单：**在 `async def` 里面永远用 `await graph.run(...)`，`run_sync` 只在脚本顶层 / 同步代码里用。**


---

## 三、两种写节点的方式

这一节把 `@g.step`（函数式）和 `BaseNode`（声明式）拆开讲清楚，因为**选错了会很难受**。

先列一下这一节要覆盖的点：

1. `@g.step` 的写法与 `StepContext`
2. `BaseNode` 的写法与 `GraphRunContext`
3. 两者的完整对比表
4. 两者怎么混用（`as_node()` + `Annotated`）
5. `@g.stream` 流式节点
6. 节点的 `node_id` 和 `label`
7. ⚠️ 一个真实的坑：step 返回 union of BaseNode 会炸

### 3.1 `@g.step`：函数式

最简单的形态——一个 async 函数就是一个节点：

```python
import asyncio
from dataclasses import dataclass
from pydantic_graph import GraphBuilder, StepContext


@dataclass
class OrderState:
    log: list[str]


g = GraphBuilder(state_type=OrderState, input_type=int, output_type=str)


@g.step
async def check_stock(ctx: StepContext[OrderState, None, int]) -> int:
    ctx.state.log.append(f'查库存: 订单 {ctx.inputs}')
    return ctx.inputs


@g.step
async def charge(ctx: StepContext[OrderState, None, int]) -> str:
    ctx.state.log.append(f'扣款: 订单 {ctx.inputs}')
    return f'订单 {ctx.inputs} 已完成'


g.add(
    g.edge_from(g.start_node).to(check_stock),
    g.edge_from(check_stock).to(charge),
    g.edge_from(charge).to(g.end_node),
)

order_graph = g.build()


async def main():
    state = OrderState(log=[])
    result = await order_graph.run(state=state, inputs=1001)
    print(result)
    print(state.log)
```

实跑输出：

```text
订单 1001 已完成
['查库存: 订单 1001', '扣款: 订单 1001']
```

`render()` 输出：

```text
stateDiagram-v2
  check_stock
  charge

  [*] --> check_stock
  check_stock --> charge
  charge --> [*]
```

**关键点：**

| 要点 | 说明 |
|---|---|
| `ctx` 是 `StepContext[State, Deps, Input]` | 三个泛型依次是：图的状态类型、图的依赖类型、**这个 step 自己的输入类型** |
| `ctx.inputs` | 上游节点传过来的数据。这是 `@g.step` 独有的 |
| 返回值 | 直接返回业务数据（`int`、`str`、`dict`……），会沿着你手动连的边流到下一个节点 |
| 边要手动连 | `g.edge_from(A).to(B)` |
| 节点 ID | 默认就是函数名（`check_stock`、`charge`） |

> 👉 **PM 视角**：函数式写法适合**流水线型**流程——每一步吃上一步的输出，吐给下一步。就像工厂流水线：上一道工序的半成品，直接传到下一道工位。数据在**边上流动**。

### 3.2 `BaseNode`：声明式

```python
from __future__ import annotations
from dataclasses import dataclass
from pydantic_graph import BaseNode, End, GraphRunContext


@dataclass
class Triage(BaseNode[TicketState, None, str]):
    ticket: str          # ← 节点自带的数据

    async def run(self, ctx: GraphRunContext[TicketState, None]) -> Escalate | End[str]:
        ctx.state.trail.append('分诊')
        if '崩溃' in self.ticket:
            return Escalate(self.ticket)      # ← 把数据塞进下一个节点的构造参数
        return End('工单已关闭')
```

**关键点：**

| 要点 | 说明 |
|---|---|
| 三个泛型 `BaseNode[StateT, DepsT, RunEndT]` | 状态类型、依赖类型、**如果这个节点会 `return End(x)`，`x` 的类型**。都有默认值，用不到就省略 |
| `ctx` 是 `GraphRunContext[State, Deps]` | **只有两个泛型，没有 inputs！** |
| 数据怎么传 | 通过 dataclass 字段。上游 `return Escalate(self.ticket)`，数据在**构造参数里** |
| 边怎么定义 | 写在 `run()` 的返回注解里，`g.node(Triage)` 注册时自动读出来 |
| 节点 ID | 默认是类名（`Triage`），由 `BaseNode.get_node_id()` 返回 `cls.__name__` |

> 👉 **PM 视角**：声明式写法适合**状态机型**流程——"当前处于'待审批'状态，下一步可能是'已通过'或'已驳回'"。数据在**节点里**，边只是状态转移。像审批单本身在流转，每一站盖个章。

### 3.3 完整对比表

| 维度 | `@g.step` 函数式 | `BaseNode` 声明式 |
|---|---|---|
| 定义方式 | `@g.step` 装饰一个 async 函数 | `@dataclass` + 继承 `BaseNode` + 实现 `run()` |
| 上下文类型 | `StepContext[StateT, DepsT, InputT]` | `GraphRunContext[StateT, DepsT]` |
| 能拿到 `ctx.state` | ✅ | ✅ |
| 能拿到 `ctx.deps` | ✅ | ✅ |
| 能拿到 `ctx.inputs` | ✅ | ❌ **没有**，数据放在 `self.xxx` 字段里 |
| 数据传递方式 | 通过边（返回值 → 下一个节点的 `ctx.inputs`） | 通过节点构造参数（`return NextNode(data)`） |
| 出边怎么定 | `g.edge_from(A).to(B)` 手动连 | 从 `run()` 返回注解自动推导 |
| 注册方式 | 被 `g.add(g.edge_from(...))` 引用时自动注册 | `g.node(X)` 显式注册 |
| 能返回多个可能的下游 | ⚠️ 需要显式 `g.decision()`（见 3.7 的坑） | ✅ 返回注解写 union 即可 |
| 能结束整张图 | 连到 `g.end_node` | `return End(x)` |
| 支持 `.map()` / `.broadcast()` / `.transform()` | ✅ 边上的操作都支持 | 边由推导生成，不方便加边操作 |
| 支持流式（`@g.stream`） | ✅ | ❌ |
| 默认节点 ID | 函数名 | 类名 |
| 适合的场景 | 数据处理流水线、并行 map/reduce、ETL | 状态机、审批流、有明确"状态"概念的流程 |
| 心智模型 | "函数组合" | "状态转移" |

**怎么选？一句话：**

- 流程里的每一步都在**加工同一份数据** → `@g.step`
- 流程里有明确的**状态**概念（待审批 / 已通过 / 已驳回） → `BaseNode`
- **不确定就用 `@g.step`**，它更简单，而且并行/分支/转换等高级边操作都在它这边

### 3.4 混用：`as_node()` + `Annotated`

两者可以在同一张图里混着用。已经见过一个方向：`@g.step` 返回一个 `BaseNode`（README 里的 `start` 就是）。

反方向——`BaseNode` 要跳到一个 `@g.step`——需要用 `step.as_node(数据)`，并且返回注解要写成 `Annotated[StepNode[StateT, DepsT], 那个step]`：

```python
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from typing import Annotated
from pydantic_graph import (
    BaseNode, End, GraphBuilder, GraphRunContext, StepContext, StepNode,
)


@dataclass
class TicketState:
    trail: list[str]


g = GraphBuilder(state_type=TicketState, input_type=str, output_type=str)


# 函数式 step
@g.step
async def close_ticket(ctx: StepContext[TicketState, None, str]) -> str:
    ctx.state.trail.append('关单')
    return f'工单 {ctx.inputs} 已关闭'


# 声明式 BaseNode，可以跳到 Escalate（另一个 BaseNode）或 close_ticket（一个 step）
@dataclass
class Triage(BaseNode[TicketState, None, str]):
    ticket: str

    async def run(
        self, ctx: GraphRunContext[TicketState, None]
    ) -> Escalate | Annotated[StepNode[TicketState, None], close_ticket]:
        ctx.state.trail.append('分诊')
        if '崩溃' in self.ticket:
            return Escalate(self.ticket)
        return close_ticket.as_node(self.ticket)      # ← 跳到一个 step


@dataclass
class Escalate(BaseNode[TicketState, None, str]):
    ticket: str

    async def run(self, ctx: GraphRunContext[TicketState, None]) -> End[str]:
        ctx.state.trail.append('升级')
        return End(f'工单 {self.ticket} 已升级给二线')


@g.step
async def entry(ctx: StepContext[TicketState, None, str]) -> Triage:
    return Triage(ctx.inputs)


g.add(
    g.edge_from(g.start_node).to(entry),
    g.node(Triage),
    g.node(Escalate),
    g.edge_from(close_ticket).to(g.end_node),
)

graph = g.build()


async def main():
    for t in ('登录页崩溃', '文案错别字'):
        st = TicketState(trail=[])
        print(await graph.run(state=st, inputs=t), '|', st.trail)
```

实跑输出：

```text
工单 登录页崩溃 已升级给二线 | ['分诊', '升级']
工单 文案错别字 已关闭 | ['分诊', '关单']
```

`render()` 输出：

```text
stateDiagram-v2
  entry
  Triage
  state decision <<choice>>
  Escalate
  close_ticket

  [*] --> entry
  entry --> Triage
  Triage --> decision
  decision --> Escalate
  decision --> close_ticket
  Escalate --> [*]
  close_ticket --> [*]
```

`Annotated[StepNode[...], close_ticket]` 这个写法有点丑，原因是 Python 类型系统没法在类型里表达"这是 `close_ticket` 这个具体的 step"，所以要把 step 对象本身当作元数据挂在 `Annotated` 上。库在读注解时会把它挑出来。

> ⚠️ **坑**：如果你写了 `-> StepNode[S, D]` 却忘了套 `Annotated[..., 那个step]`，**在 `g.add()` / `g.node()` 注册这一步就会抛** `GraphSetupError`（不用等到 `build()`），提示你 "return type hint includes a `StepNode` without a `Step` annotation"。

> 👉 **PM 视角**：混用其实很自然——**主干用状态机（BaseNode）画清楚"单子现在在哪一站"，具体每一站的活儿用 step 写**。就像审批流的主干是"待提交 → 待审批 → 待打款 → 已完成"，但"待打款"这一站内部要调三方支付接口、写流水、发通知，这些用 step 更顺手。

### 3.5 `@g.stream`：流式节点

普通 step 是"算完了一次性返回"，流式 step 是"边算边往下发"。它接受一个 **async 生成器**：

```python
import asyncio
from pydantic_graph import GraphBuilder, StepContext, reduce_list_append

g = GraphBuilder(output_type=list[str])


@g.stream
async def pull_leads(ctx: StepContext[None, None, None]):
    for i in range(1, 4):
        await asyncio.sleep(0.05)      # 模拟：分批从 CRM 拉线索
        yield f'线索{i}'                # ← 一条一条 yield 出去


@g.step
async def score(ctx: StepContext[None, None, str]) -> str:
    return f'{ctx.inputs} -> 评分完成'


collect = g.join(reduce_list_append, initial_factory=list[str])

g.add(
    g.edge_from(g.start_node).to(pull_leads),
    g.edge_from(pull_leads).map().to(score),   # ← 对流出来的每一条都并行处理
    g.edge_from(score).to(collect),
    g.edge_from(collect).to(g.end_node),
)

graph = g.build()


async def main():
    print(sorted(await graph.run()))
```

实跑输出：

```text
['线索1 -> 评分完成', '线索2 -> 评分完成', '线索3 -> 评分完成']
```

`render()` 输出（注意 `pull_leads` 在图里跟普通 step 长得一样）：

```text
stateDiagram-v2
  pull_leads
  state map <<fork>>
  score
  state reduce_list_append <<join>>

  [*] --> pull_leads
  pull_leads --> map
  map --> score
  score --> reduce_list_append
  reduce_list_append --> [*]
```

**流式节点的本质**：`@g.stream` 内部会把你的生成器包一层，让这个 step 的"返回值"变成一个 `AsyncIterable`。配合 `.map()`，**每 yield 一个值就立刻起一个下游并行任务**，不用等生成器跑完。

> 👉 **PM 视角**：这对应"**边到边处理**"的产品体验。比如批量导入 1 万条客户数据做 AI 打标：
> - 普通 step：等 1 万条全查出来（30 秒），再开始打标 → 用户干等 30 秒进度条不动
> - 流式 step：查出来一批就打一批 → 进度条从第 1 秒就开始动
>
> 用户感知的完成时间可能一样，但**感知的响应速度**天差地别。

### 3.6 节点 ID 和标签

两个可选参数，都影响可视化：

```python
@g.step(label='拉取用户画像', node_id='profile')
async def fetch_profile(ctx: StepContext[None, None, None]) -> str:
    return 'PM小李'


@g.step(label='生成推荐语')
async def make_copy(ctx: StepContext[None, None, str]) -> str:
    return f'你好 {ctx.inputs}'


g.add(g.edge_from(g.start_node).to(fetch_profile))
g.add_edge(fetch_profile, make_copy, label='带上画像')
g.add(g.edge_from(make_copy).to(g.end_node))
```

`render(title='推荐语生成', direction='TB')` 实跑输出：

```text
---
title: 推荐语生成
---
stateDiagram-v2
  direction TB
  profile: 拉取用户画像
  make_copy: 生成推荐语

  [*] --> profile
  profile --> make_copy: 带上画像
  make_copy --> [*]
```

| 参数 | 作用 | 默认值 |
|---|---|---|
| `node_id=` | 节点在图里的唯一 ID，**必须全图唯一** | step 用函数名，BaseNode 用类名 |
| `label=` | 给人看的中文名，渲染成 `节点ID: 标签` | 无 |
| `g.add_edge(A, B, label=)` | 给**边**加标签，渲染成 `A --> B: 标签` | 无 |

还可以直接看图里有哪些节点：

```python
for nid, node in graph.nodes.items():
    print(f'{nid:20} {type(node).__name__}')
```

```text
__start__            StartNode
profile              Step
make_copy            Step
__end__              EndNode
```

注意起点和终点的 ID 是固定的 `__start__` / `__end__`。

> ⚠️ **坑**：`node_id` 冲突**在 `g.add()` 注册时就会抛** `GraphBuildingError: All nodes must have unique node IDs.`（不用等到 `build()`）。如果你有两个同名函数（比如在不同模块里都叫 `process`），必须手动指定 `node_id`。

> 👉 **PM 视角**：`label` 是你能直接施加影响的地方。让工程师给每个节点写中文 label，`render()` 出来的图业务方就能直接看懂，不用再翻译一遍。这是**最低成本的流程文档**。

### 3.7 ⚠️ 一个真实的坑：step 返回 union of BaseNode 会在运行时炸

这是本版本一个必须知道的行为差异。前面说"边由返回类型注解推导"，但**推导出来的分支逻辑，`@g.step` 和 `BaseNode` 不一样**。

先看会炸的写法：

```python
@dataclass
class Approve(BaseNode[None, None, str]):
    who: str
    async def run(self, ctx: GraphRunContext) -> End[str]:
        return End(f'{self.who} 已通过')


@dataclass
class Reject(BaseNode[None, None, str]):
    who: str
    async def run(self, ctx: GraphRunContext) -> End[str]:
        return End(f'{self.who} 被驳回')


g = GraphBuilder(input_type=int, output_type=str)

@g.step
async def judge(ctx: StepContext[None, None, int]) -> Approve | Reject:   # ⚠️ union
    return Approve('小张') if ctx.inputs >= 60 else Reject('小张')

g.add(
    g.edge_from(g.start_node).to(judge),
    g.node(Approve),
    g.node(Reject),
)
graph = g.build()          # build() 不报错

import asyncio
asyncio.run(graph.run(inputs=90))   # ← 跑到这一步才炸
```

实跑报错：

```text
RuntimeError: No branch matched inputs Approve(who='小张') for decision node
Decision(id='decision', branches=[
  DecisionBranch(source=<class 'NoneType'>, matches=None, ...destinations=[NodeStep(id='Approve'...)]),
  DecisionBranch(source=<class 'NoneType'>, matches=None, ...destinations=[NodeStep(id='Reject'...)]),
])
```

**原因**（我读了源码 `graph_builder.py` 的 `_edge_from_return_hint`）：当返回注解是多个节点类型的 union 时，库会自动建一个 decision 节点，但它的分支条件是占位用的 `NoneType`。源码里的注释原话是：

> `# We don't actually use this decision mechanism, but we need to build the edges for parent-fork finding`

也就是说，这个 decision **只是为了在图结构上把边画出来**（供 fork/join 分析和渲染），**不打算在运行时真的用**。

- 走 `BaseNode` 路线时（`g.node(X)`）：节点跑完，调度器走的是 `_handle_node()` 分支——**直接看返回对象是哪个类，路由到对应节点**，根本不经过那个 decision。✅ 所以能正常工作。
- 走 `@g.step` 路线时：节点跑完，调度器走 `_handle_edges()` → 命中那个占位 decision → 拿 `NoneType` 去 `isinstance()` 比对 → **一个都不匹配 → 抛 RuntimeError**。❌

**两个正确写法：**

**方案 A（推荐）：把分流逻辑挪进 `BaseNode`**

```python
@dataclass
class Judge(BaseNode[None, None, str]):
    score: int
    async def run(self, ctx: GraphRunContext) -> Approve | Reject:
        return Approve('小张') if self.score >= 60 else Reject('小张')


@g.step
async def entry(ctx: StepContext[None, None, int]) -> Judge:
    return Judge(ctx.inputs)


g.add(
    g.edge_from(g.start_node).to(entry),
    g.node(Judge), g.node(Approve), g.node(Reject),
)
```

**方案 B：step 返回普通值，用显式 `g.decision()` 分流**

```python
@g2.step
async def score_it(ctx: StepContext[None, None, int]) -> int:      # ← 返回普通 int
    return ctx.inputs

@g2.step
async def approve(ctx: StepContext[None, None, int]) -> str:
    return '已通过'

@g2.step
async def reject(ctx: StepContext[None, None, int]) -> str:
    return '被驳回'

g2.add(
    g2.edge_from(g2.start_node).to(score_it),
    g2.edge_from(score_it).to(
        g2.decision()
        .branch(g2.match(int, matches=lambda s: s >= 60).to(approve))
        .branch(g2.match(int).to(reject))
    ),
    g2.edge_from(approve, reject).to(g2.end_node),
)
```

两个方案实跑输出：

```text
A: 小张 已通过 / 小张 被驳回
B: 已通过 / 被驳回
```

方案 A 的 `render()`：

```text
stateDiagram-v2
  entry
  Judge
  state decision <<choice>>
  Approve
  Reject

  [*] --> entry
  entry --> Judge
  Judge --> decision
  decision --> Approve
  decision --> Reject
  Approve --> [*]
  Reject --> [*]
```

**记忆口诀：**

| 你想做的 | 用什么 |
|---|---|
| step 返回**一个**确定的下游节点 | ✅ 直接写 `-> NextNode`，自动连边 |
| step 要在**多个 BaseNode** 之间分流 | ❌ 别写 union → 改成方案 A 或 B |
| BaseNode 要在多个下游之间分流 | ✅ 直接写 `-> A \| B \| End[X]` |
| step 要在**多个 step** 之间分流 | ✅ 用显式 `g.decision()` |

> ⚠️ **坑**：这个坑最难受的地方是 **`build()` 不会报错**，图也能画出来，看起来一切正常，只有跑到那一步才炸。写完记得**每条分支都跑一次单测**。

---

## 四、状态与依赖：四个泛型参数

`GraphBuilder` 有四个类型参数，它们贯穿整张图。这一节讲清楚每个是什么、什么时候用、怎么区分。

先列一下要讲的：

1. 四个参数总览表
2. `state_type`：整条流程共享的可变数据
3. `deps_type`：注入的外部资源
4. `input_type` / `output_type`：图的进出口
5. `StepContext` vs `GraphRunContext` 的差别
6. `state` 和 `deps` 到底怎么选

### 4.1 四个参数总览

```python
g = GraphBuilder(
    name='报销审批流',          # 可选，日志/追踪里的名字
    state_type=AuditState,      # 状态
    deps_type=Deps,             # 依赖
    input_type=Expense,         # 输入
    output_type=str,            # 输出
    auto_instrument=True,       # 是否自动打 OpenTelemetry span，默认 True
)
```

| 参数 | 默认值 | 生命周期 | 可变吗 | 谁提供 | 类比 |
|---|---|---|---|---|---|
| `state_type` | `NoneType` | 一次 run 内 | ✅ 节点可以随便改 | 调用方 `run(state=...)` | **单据本身**（报销单、订单） |
| `deps_type` | `NoneType` | 一次 run 内 | ⚠️ 技术上能改，但不该改 | 调用方 `run(deps=...)` | **办公设备**（数据库连接、支付网关客户端） |
| `input_type` | `NoneType` | 进入图的那一刻 | — | 调用方 `run(inputs=...)` | **发起流程时填的表单** |
| `output_type` | `NoneType` | 离开图的那一刻 | — | 图自己产出 | **流程的最终结论** |

> 👉 **PM 视角**：这四个东西对应审批流后台的四个配置项：
> - `input_type` = "发起人要填哪些字段"
> - `state_type` = "这张单子上会被各节点写入的字段"（审批意见、时间戳、附件）
> - `deps_type` = "这条流程要连哪些外部系统"（HR 系统、财务系统）
> - `output_type` = "流程结束后返回什么"

### 4.2 `state_type`：整条流程共享的可变数据

**特征：每次 run 一份新的，所有节点都能读能写，跑完你还能拿回来看。**

```python
import asyncio
from dataclasses import dataclass
from pydantic_graph import GraphBuilder, StepContext


@dataclass
class OrderState:
    log: list[str]


g = GraphBuilder(state_type=OrderState, input_type=int, output_type=str)


@g.step
async def check_stock(ctx: StepContext[OrderState, None, int]) -> int:
    ctx.state.log.append(f'查库存: 订单 {ctx.inputs}')     # ← 写状态
    return ctx.inputs


@g.step
async def charge(ctx: StepContext[OrderState, None, int]) -> str:
    ctx.state.log.append(f'扣款: 订单 {ctx.inputs}')
    return f'订单 {ctx.inputs} 已完成'
```

跑完之后，**外面的 `state` 对象已经被改过了**：

```python
state = OrderState(log=[])
result = await order_graph.run(state=state, inputs=1001)
print(result)       #> 订单 1001 已完成
print(state.log)    #> ['查库存: 订单 1001', '扣款: 订单 1001']
```

这是 state 最有价值的用法：**图的返回值只有一个，但过程中产生的所有副产品，都可以攒在 state 里带出来**。

> 👉 **PM 视角**：state 就是**审批单上的流转记录**。图的 `output` 是"最终批了还是没批"，而 state 里存的是"每一步谁在什么时间做了什么"——这个东西对客诉处理、对账、合规审计的价值，往往比结论本身还大。
>
> 设计新流程时，值得专门问工程师一句：**"这条流程跑完，我能从 state 里拿到哪些审计信息？"**

⚠️ **并行时的 state 是共享的**。所有并行任务改的是**同一个 state 对象**，没有加锁。官方文档的例子：

```python
@g.step
async def track_and_square(ctx: StepContext[CounterState, None, int]) -> int:
    ctx.state.values.append(ctx.inputs)      # ← 3 个并行任务同时 append
    return ctx.inputs * ctx.inputs
```

Python 的 `list.append` 本身是原子的所以没问题，但如果你写 `ctx.state.counter = ctx.state.counter + 1` 这种"读-改-写"，并行下就可能丢更新。

> ⚠️ **坑**：并行分支里改 state，只做**追加型**操作（`append` / `dict[k]=v`），别做"读出来算一下再写回去"。要累加就用 Join 的 reducer（第五节）。

### 4.3 `deps_type`：注入的外部资源

**特征：每次 run 传进来，节点只读，用来做环境隔离。**

```python
import asyncio
from dataclasses import dataclass
from pydantic_graph import GraphBuilder, StepContext


@dataclass
class Deps:
    db_url: str
    notify_channel: str


g = GraphBuilder(deps_type=Deps, input_type=int, output_type=str)


@g.step
async def load(ctx: StepContext[None, Deps, int]) -> str:
    return f'从 {ctx.deps.db_url} 读取用户 {ctx.inputs}'


@g.step
async def notify(ctx: StepContext[None, Deps, str]) -> str:
    return f'{ctx.inputs}, 并推送到 {ctx.deps.notify_channel}'


g.add(
    g.edge_from(g.start_node).to(load),
    g.edge_from(load).to(notify),
    g.edge_from(notify).to(g.end_node),
)
graph = g.build()


async def main():
    prod = Deps(db_url='prod-db', notify_channel='#alerts')
    test = Deps(db_url='sqlite://memory', notify_channel='#dev-null')
    print(await graph.run(deps=prod, inputs=42))
    print(await graph.run(deps=test, inputs=42))
```

实跑输出：

```text
从 prod-db 读取用户 42, 并推送到 #alerts
从 sqlite://memory 读取用户 42, 并推送到 #dev-null
```

**同一张图，换个 `deps` 就从生产切到测试。** 这就是依赖注入的全部意义。

官方文档里还有个更实际的例子——把 CPU 密集的计算丢给进程池：

```python
@dataclass
class GraphDeps:
    executor: ProcessPoolExecutor


@dataclass
class Increment(BaseNode[None, GraphDeps]):
    foo: int

    async def run(self, ctx: GraphRunContext[None, GraphDeps]) -> DivisibleBy5:
        loop = asyncio.get_running_loop()
        compute_result = await loop.run_in_executor(ctx.deps.executor, self.compute)
        return DivisibleBy5(compute_result)

    def compute(self) -> int:
        return self.foo + 1
```

> 👉 **PM 视角**：deps 是**"同一套流程，不同环境"**的开关。它带来的直接产品价值：
> - **可测试**：测试环境用假的支付网关，跑 100 遍不花一分钱
> - **可灰度**：新老风控引擎做成两个 deps，5% 流量走新的
> - **多租户**：A 客户连 A 的数据库，B 客户连 B 的，流程定义只有一份

### 4.4 `state` 和 `deps` 到底怎么选？

新手最容易搞混的地方。判断标准：

| 问题 | 答 yes → state | 答 yes → deps |
|---|---|---|
| 这个东西是**这一次业务发生的事实**吗？（这张订单的金额） | ✅ | |
| 这个东西是**基础设施**吗？（数据库连接） | | ✅ |
| 跑完之后我想**拿出来看**吗？ | ✅ | |
| 换个环境（测试/生产）它会**变**吗？ | | ✅ |
| 流程中途会**被改写**吗？ | ✅ | |
| 它能被**多次 run 共享**吗？ | ❌ 每次一份新的 | ✅ 可以复用同一个 |

一句话：**state 是"这单子的内容"，deps 是"办这单子用的工具"。**

### 4.5 `input_type` / `output_type`：图的进出口

```python
g = GraphBuilder(input_type=Expense, output_type=str)
result: str = await graph.run(inputs=Expense('小王', 300.0))
```

| 参数 | 流向 | 谁消费 |
|---|---|---|
| `input_type` | `run(inputs=X)` → `g.start_node` → 第一个节点的 `ctx.inputs` | 从 start_node 连出去的那个节点 |
| `output_type` | 最后一个节点的返回值 → `g.end_node` → `run()` 的返回值 | 调用方 |

对于 `BaseNode` 路线，图的输出是 `End(x)` 里的那个 `x`。

**关于 `g.start_node` 和 `g.end_node`：**

- 它们是内置的虚拟节点，ID 固定为 `__start__` / `__end__`
- 在 mermaid 里渲染成 `[*]`
- 每张图**必须**至少有一条从 start 出去的边和一条进 end 的边（否则 `build()` 报错）

### 4.6 `StepContext` vs `GraphRunContext`

这是两种节点写法最直接的差别：

| | `StepContext[StateT, DepsT, InputT]` | `GraphRunContext[StateT, DepsT]` |
|---|---|---|
| 谁拿到它 | `@g.step` / `@g.stream` 函数的第一个参数 | `BaseNode.run()` 的 `ctx` 参数 |
| `.state` | ✅ | ✅ |
| `.deps` | ✅ | ✅ |
| `.inputs` | ✅ **有** | ❌ **没有** |
| 泛型个数 | 3 个 | 2 个 |
| 为什么这样设计 | step 是无状态函数，输入必须从外面给 | BaseNode 是有状态对象，输入就是 `self` 的字段 |

补充：`.transform(lambda ctx: ...)` 里的那个 `ctx` 也是 `StepContext`，所以边上的转换函数同样能读 `state` / `deps` / `inputs`。

`ReducerContext[StateT, DepsT]`（reducer 函数拿到的上下文）是第三种，只有 `.state` / `.deps` 和一个 `.cancel_sibling_tasks()` 方法，第五节讲。

### 4.7 完整的四参数示例

把四个参数一起用上：

```python
import asyncio
from dataclasses import dataclass
from pydantic_graph import GraphBuilder, StepContext, TypeExpression


@dataclass
class Expense:              # ← input_type
    who: str
    amount: float


@dataclass
class AuditState:           # ← state_type
    trail: list[str]


g = GraphBuilder(
    state_type=AuditState,
    input_type=Expense,
    output_type=str,        # ← output_type
)


@g.step
async def submit(ctx: StepContext[AuditState, None, Expense]) -> Expense:
    ctx.state.trail.append(f'{ctx.inputs.who} 提交 {ctx.inputs.amount} 元')
    return ctx.inputs


@g.step
async def lead_approve(ctx: StepContext[AuditState, None, Expense]) -> str:
    ctx.state.trail.append('组长审批')
    return f'{ctx.inputs.who} 的 {ctx.inputs.amount} 元由组长批准'


@g.step
async def director_approve(ctx: StepContext[AuditState, None, Expense]) -> str:
    ctx.state.trail.append('总监审批')
    return f'{ctx.inputs.who} 的 {ctx.inputs.amount} 元由总监批准'


g.add(
    g.edge_from(g.start_node).to(submit),
    g.edge_from(submit).to(
        g.decision(note='金额 <= 1000 走组长')
        .branch(
            g.match(TypeExpression[Expense], matches=lambda e: e.amount <= 1000)
            .label('小额').to(lead_approve)
        )
        .branch(
            g.match(TypeExpression[Expense], matches=lambda e: e.amount > 1000)
            .label('大额').to(director_approve)
        )
    ),
    g.edge_from(lead_approve, director_approve).to(g.end_node),
)

approval_graph = g.build()


async def main():
    for amount in (300.0, 5000.0):
        state = AuditState(trail=[])
        result = await approval_graph.run(state=state, inputs=Expense('小王', amount))
        print(result)
        print(state.trail)
```

实跑输出：

```text
小王 的 300.0 元由组长批准
['小王 提交 300.0 元', '组长审批']
小王 的 5000.0 元由总监批准
['小王 提交 5000.0 元', '总监审批']
```

`render()` 输出（注意 `note` 渲染成了图上的注释）：

```text
stateDiagram-v2
  submit
  state decision <<choice>>
  note right of decision
    金额 <= 1000 走组长
  end note
  director_approve
  lead_approve

  [*] --> submit
  submit --> decision
  decision --> director_approve: 大额
  decision --> lead_approve: 小额
  director_approve --> [*]
  lead_approve --> [*]
```

> 👉 **PM 视角**：这张图基本可以直接贴进 PRD。`note` 里写的是业务规则，边上的 label 是分支名称，一眼就能看懂"1000 块是分水岭"。规则改了（比如提到 2000），图上的 note 也跟着改——因为它就在代码里。

---

## 五、控制流：图的五种形状

这是最核心的一节。任何流程图无非五种形状：**顺序、分支、循环、并行扇出、并行扇入**。这一节把每一种都讲透，每个都配 `render()` 出来的真实 mermaid 图。

先列一下这一节的知识点清单：

| # | 形状 | API | 小节 |
|---|---|---|---|
| 1 | 顺序 | `g.edge_from(A).to(B)` / `g.add_edge(A, B)` | 5.1 |
| 2 | 分支 | `g.decision()` + `.branch(g.match(...))` | 5.2 |
| 3 | 分支：按类型 | `g.match(int)` | 5.2.1 |
| 4 | 分支：按 union / Literal | `g.match(TypeExpression[...])` | 5.2.2 |
| 5 | 分支：自定义谓词 | `g.match(T, matches=lambda x: ...)` | 5.2.3 |
| 6 | 分支：优先级与兜底 | 分支顺序 + `g.match(TypeExpression[object])` | 5.2.4 |
| 7 | 分支：按节点类型 | `g.match_node(SomeNode)` | 5.2.5 |
| 8 | 分支：嵌套 | 多个 `g.decision()` 串起来 | 5.2.6 |
| 9 | 分支：注释与标签 | `g.decision(note=)` / `.label()` | 5.2.7 |
| 10 | 循环 | 一条边指回上游 | 5.3 |
| 11 | 并行扇出：广播 | `.to(A, B, C)` / `.broadcast()` | 5.4 |
| 12 | 并行扇出：映射 | `.map()` / `g.add_mapping_edge()` | 5.5 |
| 13 | 并行扇入 | `g.join(reducer, initial=/initial_factory=)` | 5.6 |
| 14 | 内置 reducer（6 个） | `reduce_*` / `ReduceFirstValue` | 5.6.2 |
| 15 | 自定义 reducer + 提前中断 | `ReducerContext.cancel_sibling_tasks()` | 5.6.3 |
| 16 | 边上转换 | `.transform(lambda ctx: ...)` | 5.7 |
| 17 | 空集合的坑 | `downstream_join_id=` | 5.8 |
| 18 | 嵌套并行 | map 套 broadcast、连续 map | 5.9 |
| 19 | 多个独立 join | `node_id=` 区分 | 5.10 |

### 5.1 顺序

最简单的形状，两种等价写法：

```python
# 写法一：edge_from().to()
g.add(
    g.edge_from(g.start_node).to(step_a),
    g.edge_from(step_a).to(step_b),
    g.edge_from(step_b).to(g.end_node),
)

# 写法二：add_edge()（更短，但只能连简单边）
g.add_edge(g.start_node, step_a)
g.add_edge(step_a, step_b, label='从 a 到 b')
g.add_edge(step_b, g.end_node)
```

`g.edge_from()` 还可以接**多个源**，表示"这几个节点都连到同一个目标"：

```python
g.edge_from(lead_approve, director_approve).to(g.end_node)
# 等价于两条边：lead_approve → end，director_approve → end
```

这在分支合流的时候特别常用。

> 👉 **PM 视角**：`g.edge_from(A, B, C).to(D)` 就是泳道图里"三条支线汇总到同一个终点"。注意它**不是** join——不需要等三条都跑完，谁先到谁先走。真正的"等所有人都到齐"是 `g.join()`（5.6）。

### 5.2 分支：`decision` + `match`

分支的基本形状：

```python
g.edge_from(某个节点).to(
    g.decision(note='规则说明')
    .branch(g.match(条件1).to(目标1))
    .branch(g.match(条件2).to(目标2))
    .branch(g.match(条件3).to(目标3))
)
```

**执行逻辑**（源码 `_handle_decision`）：从上到下依次试每个分支，**第一个匹配的赢**，走它的路径。**一个都不匹配就抛 `RuntimeError`**。

这跟 Python 的 `if / elif / elif` 完全一样，只是没有隐式的 `else`——**没写兜底就会炸**。

#### 5.2.1 按类型匹配

最简单的形态，直接传一个类：

```python
g.edge_from(return_int).to(
    g.decision()
    .branch(g.match(int).to(handle_int))
    .branch(g.match(str).to(handle_str))
)
```

内部用 `isinstance(输入值, int)` 判断。

#### 5.2.2 按 union / Literal 匹配：需要 `TypeExpression`

Python 不允许把 `int | str` 或 `Literal['a']` 当成运行时的 `type` 值传参，所以需要一个包装器 `TypeExpression`：

```python
from pydantic_graph import TypeExpression

g.match(TypeExpression[int | float]).to(handle_number)      # union
g.match(TypeExpression[Literal['退款']]).to(refund)          # 字面量
g.match(TypeExpression[object]).to(catch_all)               # 兜底
```

| 匹配目标 | 写法 | 内部判断逻辑 |
|---|---|---|
| 普通类 | `g.match(int)` | `isinstance(v, int)` |
| union | `g.match(TypeExpression[int \| float])` | `isinstance(v, (int, float))` |
| 字面量 | `g.match(TypeExpression[Literal['a', 'b']])` | `v in ('a', 'b')` |
| 兜底 | `g.match(TypeExpression[object])` 或 `TypeExpression[Any]` | 恒为 True |

完整例子——客服工单按意图分流：

```python
import asyncio
from dataclasses import dataclass
from typing import Literal
from pydantic_graph import GraphBuilder, StepContext, TypeExpression


@dataclass
class S:
    pass


g = GraphBuilder(state_type=S, input_type=str, output_type=str)


@g.step
async def classify(ctx: StepContext[S, None, str]) -> Literal['退款', '换货', '咨询']:
    if '坏' in ctx.inputs:
        return '换货'
    if '钱' in ctx.inputs:
        return '退款'
    return '咨询'


@g.step
async def refund(ctx: StepContext[S, None, object]) -> str:
    return '走退款流程'


@g.step
async def exchange(ctx: StepContext[S, None, object]) -> str:
    return '走换货流程'


@g.step
async def faq(ctx: StepContext[S, None, object]) -> str:
    return '转 FAQ 机器人'


g.add(
    g.edge_from(g.start_node).to(classify),
    g.edge_from(classify).to(
        g.decision()
        .branch(g.match(TypeExpression[Literal['退款']]).to(refund))
        .branch(g.match(TypeExpression[Literal['换货']]).to(exchange))
        .branch(g.match(TypeExpression[object]).to(faq))       # ← 兜底
    ),
    g.edge_from(refund, exchange, faq).to(g.end_node),
)
graph = g.build()


async def main():
    for msg in ('杯子坏了', '想退钱', '怎么用'):
        print(msg, '->', await graph.run(state=S(), inputs=msg))
```

实跑输出：

```text
杯子坏了 -> 走换货流程
想退钱 -> 走退款流程
怎么用 -> 转 FAQ 机器人
```

`render()` 输出：

```text
stateDiagram-v2
  classify
  state decision <<choice>>
  exchange
  faq
  refund

  [*] --> classify
  classify --> decision
  decision --> exchange
  decision --> faq
  decision --> refund
  exchange --> [*]
  faq --> [*]
  refund --> [*]
```

> 👉 **PM 视角**：这就是"意图识别 → 分流"的标准做法。`classify` 那一步完全可以换成一个 Agent（让模型来分类），但**分流的规则依然是硬编码的**——模型只负责回答"这是哪一类"，不负责决定"该走哪条流程"。这个职责分离非常重要：模型的输出被约束成三个字面量之一，出不了幺蛾子。

#### 5.2.3 自定义谓词：`matches=`

类型判断不够用时（"金额 > 1000"这种），传一个 `matches` 函数：

```python
g.decision(note='金额 <= 1000 走组长')
 .branch(
     g.match(TypeExpression[Expense], matches=lambda e: e.amount <= 1000)
     .label('小额').to(lead_approve)
 )
 .branch(
     g.match(TypeExpression[Expense], matches=lambda e: e.amount > 1000)
     .label('大额').to(director_approve)
 )
```

`matches` 是一个 `Callable[[Any], bool]`，参数就是流到这个 decision 的**值本身**。

> ⚠️ **坑**：`matches` **只能拿到值，拿不到 `ctx.state` 和 `ctx.deps`**。如果你的分支条件要看状态（比如"这是第几次重试"），必须把那个信息塞进流转的值里（做成 dataclass 的一个字段），或者在上游 step 里先算好。

#### 5.2.4 优先级与兜底

**分支从上到下依次尝试，第一个匹配的赢。** 官方例子：

```python
g.decision()
 .branch(g.match(TypeExpression[int], matches=lambda x: x >= 5).to(branch_a))
 .branch(g.match(TypeExpression[int], matches=lambda x: x >= 0).to(branch_b))
```

输入 `10` 时两个分支都成立，但走 `branch_a`（先写的那个）。

**兜底分支写在最后：**

```python
.branch(g.match(TypeExpression[object]).to(catch_all))
```

或者一个不带 `matches` 的同类型分支（`isinstance` 恒成立）：

```python
.branch(g.match(TypeExpression[int], matches=lambda x: x >= 5).to(branch_a))
.branch(g.match(TypeExpression[int]).to(branch_b))   # ← 剩下所有 int 都走这里
```

> ⚠️ **坑**：**没有兜底分支 + 输入不匹配任何分支 = 运行时抛 `RuntimeError: No branch matched inputs ...`**。而且这个错误 `build()` 时发现不了。
>
> 稳妥做法：**每个 decision 的最后一条都写兜底**，哪怕兜底目标只是一个"记录异常并转人工"的 step。

> 👉 **PM 视角**：这就是需求评审时最容易漏的"**else 分支**"。PM 写 PRD 常写"金额 <1000 走 A，>5000 走 B"，中间 1000~5000 忘了写。在这个库里，这种遗漏会变成**线上运行时崩溃**，而不是静默走错分支。某种意义上这是好事——问题会立刻暴露。
>
> 建议在流程评审 checklist 里加一条：**每个判断节点，所有情况都覆盖到了吗？兜底走哪？**

#### 5.2.5 按节点类型匹配：`g.match_node()`

当流转的值是 `BaseNode` 实例时，用 `g.match_node(SomeNode)`，它是 `g.match(SomeNode).to(SomeNode)` 的快捷写法：

```python
g.decision()
 .branch(g.match_node(Approve))
 .branch(g.match_node(Reject))
```

⚠️ 但注意 3.7 讲的那个坑——如果上游 step 的返回注解已经是 `Approve | Reject`，自动生成的占位 decision 会抢先命中并报错。所以 `match_node` 主要用在**上游返回注解不是节点 union** 的场合。

#### 5.2.6 嵌套分支

decision 可以串起来，形成多级判断：

```python
import asyncio
from pydantic_graph import GraphBuilder, StepContext, TypeExpression

g = GraphBuilder(input_type=int, output_type=str)


@g.step
async def get_amount(ctx: StepContext[None, None, int]) -> int:
    return ctx.inputs


@g.step
async def need_approval(ctx: StepContext[None, None, int]) -> int:
    return ctx.inputs


@g.step
async def auto_pass(ctx: StepContext[None, None, int]) -> str:
    return f'{ctx.inputs} 元自动通过'


@g.step
async def lead(ctx: StepContext[None, None, int]) -> str:
    return f'{ctx.inputs} 元组长审批'


@g.step
async def director(ctx: StepContext[None, None, int]) -> str:
    return f'{ctx.inputs} 元总监审批'


g.add(
    g.edge_from(g.start_node).to(get_amount),
    # 第一层：要不要审批
    g.edge_from(get_amount).to(
        g.decision(note='500 以下免审')
        .branch(g.match(TypeExpression[int], matches=lambda x: x < 500).label('免审').to(auto_pass))
        .branch(g.match(TypeExpression[int]).label('需审批').to(need_approval))
    ),
    # 第二层：谁来审批
    g.edge_from(need_approval).to(
        g.decision(note='5000 以上升总监')
        .branch(g.match(TypeExpression[int], matches=lambda x: x < 5000).label('组长').to(lead))
        .branch(g.match(TypeExpression[int]).label('总监').to(director))
    ),
    g.edge_from(auto_pass, lead, director).to(g.end_node),
)
graph = g.build()


async def main():
    for a in (100, 2000, 90000):
        print(a, '->', await graph.run(inputs=a))
```

实跑输出：

```text
100 -> 100 元自动通过
2000 -> 2000 元组长审批
90000 -> 90000 元总监审批
```

`render()` 输出（两个菱形，`decision` 和 `decision_2`，各自带注释）：

```text
stateDiagram-v2
  get_amount
  state decision <<choice>>
  note right of decision
    500 以下免审
  end note
  auto_pass
  need_approval
  state decision_2 <<choice>>
  note right of decision_2
    5000 以上升总监
  end note
  director
  lead

  [*] --> get_amount
  get_amount --> decision
  decision --> auto_pass: 免审
  decision --> need_approval: 需审批
  auto_pass --> [*]
  need_approval --> decision_2
  decision_2 --> director: 总监
  decision_2 --> lead: 组长
  director --> [*]
  lead --> [*]
```

> 👉 **PM 视角**：这张图直接就是一张标准的审批矩阵。注意 `need_approval` 这个中间 step——它本身什么都没干（只是把值原样返回），但它的存在让第二级判断有了一个"挂载点"。这跟审批流后台里加一个"空节点"来承接分支是一个道理。

#### 5.2.7 注释和标签

两个纯粹为了可视化的参数：

| 参数 | 位置 | 渲染成 |
|---|---|---|
| `g.decision(note='...')` | decision 上 | `note right of decision \n ... \n end note` |
| `.label('...')` | 分支路径上 | `decision --> 目标: 标签` |
| `g.decision(node_id='...')` | decision 上 | 覆盖默认的 `decision` / `decision_2` ID |

> 👉 **PM 视角**：`note` 是给业务规则写"为什么"的地方，`label` 是给分支起"业务名字"的地方。这两个东西成本几乎为零，但让 `render()` 出来的图从"工程师能看懂"变成"业务方能看懂"。**这是 PM 唯一需要直接向工程师提的关于这个库的要求。**

### 5.3 循环

循环不需要特殊 API——**一条指回上游的边就是循环**。

```python
import asyncio
from dataclasses import dataclass, field
from pydantic_graph import GraphBuilder, StepContext, TypeExpression


@dataclass
class Draft:
    topic: str
    round: int
    score: int


@dataclass
class DraftState:
    history: list[str] = field(default_factory=list)


g = GraphBuilder(state_type=DraftState, input_type=str, output_type=str)


@g.step
async def start(ctx: StepContext[DraftState, None, str]) -> Draft:
    return Draft(topic=ctx.inputs, round=0, score=0)


@g.step
async def write(ctx: StepContext[DraftState, None, Draft]) -> Draft:
    d = ctx.inputs
    new = Draft(topic=d.topic, round=d.round + 1, score=d.score + 40)
    ctx.state.history.append(f'写第{new.round}稿, 评分{new.score}')
    return new


@g.step
async def publish(ctx: StepContext[DraftState, None, Draft]) -> str:
    return f'《{ctx.inputs.topic}》第{ctx.inputs.round}稿发布, 评分{ctx.inputs.score}'


g.add(
    g.edge_from(g.start_node).to(start),
    g.edge_from(start).to(write),
    g.edge_from(write).to(
        g.decision(note='评分 >= 80 才发布')
        .branch(g.match(TypeExpression[Draft], matches=lambda d: d.score >= 80)
                .label('达标').to(publish))
        .branch(g.match(TypeExpression[Draft]).label('回炉重写').to(write))   # ← 指回 write
    ),
    g.edge_from(publish).to(g.end_node),
)

graph = g.build()


async def main():
    st = DraftState()
    print(await graph.run(state=st, inputs='2026 年产品路线图'))
    print(st.history)
```

实跑输出：

```text
《2026 年产品路线图》第2稿发布, 评分80
['写第1稿, 评分40', '写第2稿, 评分80']
```

`render()` 输出：

```text
stateDiagram-v2
  start
  write
  state decision <<choice>>
  note right of decision
    评分 >= 80 才发布
  end note
  publish

  [*] --> start
  start --> write
  write --> decision
  decision --> write: 回炉重写
  decision --> publish: 达标
  publish --> [*]
```

**循环的三个注意点：**

| 注意点 | 说明 |
|---|---|
| 没有内置的最大轮次限制 | 条件永远不满足 = **死循环**。必须自己在数据或 state 里带计数器 |
| 循环变量放哪 | 放在**流转的值里**（上例的 `Draft.round`），因为 `matches` 拿不到 state |
| 每一轮都会重新执行节点 | 不是"回到上次的现场"，是真的重新跑一遍 |

> ⚠️ **坑**：一定要加轮次上限。上例可以改成：
> ```python
> .branch(g.match(TypeExpression[Draft], matches=lambda d: d.round >= 5)
>         .label('超过5轮强制发布').to(publish))
> ```
> 放在"回炉"分支前面，就是熔断。

> 👉 **PM 视角**：这就是"**改稿循环**"——写稿 → 评审 → 不过 → 重写 → 再评审。产品设计上必须回答两个问题：**最多改几轮？改到第几轮还不过怎么办？** 这两个问题不回答，线上就是死循环烧钱（每一轮都要调一次大模型）。

### 5.4 并行扇出：广播（broadcast）

**同一份数据，同时发给多个下游。**

写法就是 `.to()` 传多个目标：

```python
g.edge_from(intake).to(risk_check, credit_check, blacklist_check)
```

完整例子——开户三查并行：

```python
import asyncio
from dataclasses import dataclass
from pydantic_graph import GraphBuilder, StepContext, reduce_dict_update


@dataclass
class S:
    pass


g = GraphBuilder(state_type=S, input_type=str, output_type=dict[str, str])


@g.step
async def intake(ctx: StepContext[S, None, str]) -> str:
    return ctx.inputs


@g.step
async def risk_check(ctx: StepContext[S, None, str]) -> dict[str, str]:
    await asyncio.sleep(0.02)
    return {'风控': f'{ctx.inputs} 无异常'}


@g.step
async def credit_check(ctx: StepContext[S, None, str]) -> dict[str, str]:
    await asyncio.sleep(0.01)
    return {'征信': f'{ctx.inputs} 分数 720'}


@g.step
async def blacklist_check(ctx: StepContext[S, None, str]) -> dict[str, str]:
    return {'黑名单': f'{ctx.inputs} 不在名单内'}


merge = g.join(reduce_dict_update, initial_factory=dict[str, str])

g.add(
    g.edge_from(g.start_node).to(intake),
    g.edge_from(intake).to(risk_check, credit_check, blacklist_check),   # ← 广播
    g.edge_from(risk_check, credit_check, blacklist_check).to(merge),    # ← 汇总
    g.edge_from(merge).to(g.end_node),
)

kyc_graph = g.build()


async def main():
    result = await kyc_graph.run(state=S(), inputs='用户9527')
    print({k: result[k] for k in sorted(result)})
```

实跑输出：

```text
{'征信': '用户9527 分数 720', '风控': '用户9527 无异常', '黑名单': '用户9527 不在名单内'}
```

`render()` 输出（注意自动生成的 `broadcast` fork 节点）：

```text
stateDiagram-v2
  intake
  state broadcast <<fork>>
  blacklist_check
  credit_check
  risk_check
  state reduce_dict_update <<join>>

  [*] --> intake
  intake --> broadcast
  broadcast --> blacklist_check
  broadcast --> credit_check
  broadcast --> risk_check
  blacklist_check --> reduce_dict_update
  credit_check --> reduce_dict_update
  risk_check --> reduce_dict_update
  reduce_dict_update --> [*]
```

**注意：`broadcast` 这个节点你没写，是 `build()` 时自动插进去的。** 它在 mermaid 里渲染成 `<<fork>>`（一条粗横线）。

还有一个更显式的写法 `.broadcast()`，用于每条支路需要不同处理（比如各自加 label / transform）的情况：

```python
g.edge_from(source).broadcast(lambda b: [
    b.label('走风控').to(risk_check),
    b.label('走征信').to(credit_check),
])
```

> 👉 **PM 视角**：广播 = **并联审批**。三个部门同时审同一份材料，不用排队。产品收益是直接的：串行 3 次各 2 秒 = 6 秒，并行 = 2 秒。
>
> 反过来，**串行的地方一定要问一句"能不能并？"** 用户等待时间是产品指标，而这个库让并行几乎零成本（改一行 `.to(A, B, C)`）。

### 5.5 并行扇出：映射（map）

**一个列表，每个元素起一个并行任务。**

写法是在边上插一个 `.map()`：

```python
g.edge_from(split_items).map().to(review_one)
```

完整例子——批量审核文案：

```python
import asyncio
from dataclasses import dataclass, field
from pydantic_graph import GraphBuilder, StepContext, reduce_list_append


@dataclass
class ReviewState:
    reviewed: list[str] = field(default_factory=list)


g = GraphBuilder(state_type=ReviewState, input_type=list[str], output_type=list[str])


@g.step
async def split_items(ctx: StepContext[ReviewState, None, list[str]]) -> list[str]:
    return ctx.inputs


@g.step
async def review_one(ctx: StepContext[ReviewState, None, str]) -> str:
    await asyncio.sleep(0.01)
    ctx.state.reviewed.append(ctx.inputs)
    return f'{ctx.inputs}: 通过'


collect = g.join(reduce_list_append, initial_factory=list[str])

g.add(
    g.edge_from(g.start_node).to(split_items),
    g.edge_from(split_items).map().to(review_one),   # ← 扇出
    g.edge_from(review_one).to(collect),
    g.edge_from(collect).to(g.end_node),
)

review_graph = g.build()


async def main():
    state = ReviewState()
    result = await review_graph.run(state=state, inputs=['文案A', '文案B', '文案C'])
    print(sorted(result))
    print(sorted(state.reviewed))
```

实跑输出：

```text
['文案A: 通过', '文案B: 通过', '文案C: 通过']
['文案A', '文案B', '文案C']
```

`render()` 输出：

```text
stateDiagram-v2
  split_items
  state map <<fork>>
  review_one
  state reduce_list_append <<join>>

  [*] --> split_items
  split_items --> map
  map --> review_one
  review_one --> reduce_list_append
  reduce_list_append --> [*]
```

**`map` 和 `broadcast` 的区别：**

| | `.map()` | `.to(A, B, C)` / `.broadcast()` |
|---|---|---|
| 输入必须是 | 可迭代对象（list / AsyncIterable） | 任何值 |
| 并行任务数 | = 列表长度（**运行时才知道**） | = 目标节点数（**编译期就确定**） |
| 每个任务收到 | 列表的一个元素 | 完整的原值 |
| 下游节点 | 同一个（也可以是多个，见 5.9） | 不同的 |
| mermaid 里 | `state map <<fork>>` | `state broadcast <<fork>>` |
| 类比 | 一批订单，每单一个处理线程 | 一份材料，三个部门同时看 |

**`.map()` 也吃 `AsyncIterable`**，配合 `@g.stream` 就是"边产边消费"（见 3.5）。

**便捷写法 `g.add_mapping_edge()`：**

```python
g.add_mapping_edge(
    generate,
    process,
    pre_map_label='拆分前',      # map 之前的边标签
    post_map_label='拆分后',     # map 之后的边标签
    fork_id='my_fork',           # 自定义 fork 节点 ID
    downstream_join_id=collect.id,   # 空列表时跳到哪个 join（见 5.8）
)
```

> 👉 **PM 视角**：map = **批量任务并发**。"给这 500 个客户各生成一封个性化邮件"——串行要 500×2 秒 = 16 分钟，map 一下几秒钟。
>
> 但要注意**并发度是不受控的**：list 有多长就起多少个任务。500 个并发调 OpenAI 会直接被限流。这个库本身没有并发上限参数，要限流得在 step 内部自己加信号量。**这是上线前必须跟工程师确认的一件事。**

### 5.6 并行扇入：`join` 与 reducer

扇出之后必须扇入，否则并行的结果没法汇总。这就是 `Join`。

#### 5.6.1 join 的基本形状

```python
collect = g.join(reduce_list_append, initial_factory=list[str])

g.add(
    g.edge_from(review_one).to(collect),      # 所有并行任务都连到 join
    g.edge_from(collect).to(g.end_node),      # join 输出一个值，继续往下
)
```

`g.join()` 的参数：

| 参数 | 必填 | 说明 |
|---|---|---|
| `reducer` | ✅ | 合并函数，签名 `(current, inputs) -> current` 或 `(ctx, current, inputs) -> current` |
| `initial=` 或 `initial_factory=` | ✅ 二选一 | 累加器的初始值。**可变类型（list/dict）必须用 `initial_factory`**，否则多次 run 之间会串数据 |
| `node_id=` | ❌ | 自定义 ID，默认从 reducer 函数名生成 |
| `parent_fork_id=` | ❌ | 手动指定这个 join 对应哪个 fork |
| `preferred_parent_fork=` | ❌ | `'farthest'`（默认）或 `'closest'`，嵌套 fork 时用来消歧 |

**join 的工作机制**（官方文档原文翻译）：

1. 找到自己的"父 fork"（哪一次扇出产生了这些并行任务）
2. 等这个 fork 产生的所有任务都到达
3. 每来一个值就调一次 `reducer(current, 新值)`
4. 全部到齐后，把累加结果发给下游

> ⚠️ **坑**：`initial=[]` 和 `initial_factory=list` 是**完全不同的**。前者是所有 run 共享**同一个** list 对象（第二次跑会带着第一次的数据），后者每次 run 新建一个。**可变类型永远用 `initial_factory`。**

#### 5.6.2 六个内置 reducer

| reducer | 签名 | 初始值 | 作用 | 类比 |
|---|---|---|---|---|
| `reduce_list_append` | `(list[T], T) -> list[T]` | `initial_factory=list` | 把每个结果 append 进列表 | 收集所有人的回答 |
| `reduce_list_extend` | `(list[T], Iterable[T]) -> list[T]` | `initial_factory=list` | 每个结果本身是列表，摊平合并 | 合并多份名单 |
| `reduce_dict_update` | `(dict, Mapping) -> dict` | `initial_factory=dict` | 字典合并 | 各部门填同一张表的不同栏 |
| `reduce_sum` | `(N, N) -> N` | `initial=0` | 求和（任何支持 `+` 的类型） | 汇总金额 |
| `reduce_null` | `(None, Any) -> None` | `initial=None` | 全丢掉，只要副作用 | 只关心"都跑完了" |
| `ReduceFirstValue[T]()` | `(ctx, T, T) -> T` | `initial=None` | 取第一个到达的，**取消其余任务** | 抢答 / 竞速 |

实跑验证（四个一起）：

```python
print('reduce_sum       ->', await gg1.run(inputs=[10, 20, 30, 40]))
print('reduce_list_extend ->', sorted(await gg2.run(inputs=[1, 2, 3])))
print('ReduceFirstValue ->', await gg3.run(inputs=[1, 5, 9]))
```

```text
reduce_sum       -> 100
reduce_list_extend -> [0, 0, 0, 1, 1, 2]
ReduceFirstValue -> 供应商1先报价
```

（`reduce_list_extend` 的例子里，每个任务返回 `list(range(n))`，1→`[0]`、2→`[0,1]`、3→`[0,1,2]`，摊平合并后排序就是 `[0,0,0,1,1,2]`。）

**`ReduceFirstValue` 是最有产品价值的一个** ——"多方竞速，谁快用谁"。上面例子里三个供应商模拟不同延迟（0.1s / 0.5s / 0.9s），最快的赢，**另外两个任务被直接取消**（不会白白烧钱）。

**`reduce_null` 的典型用法** ——并行任务只是为了写 state，不关心返回值：

```python
@dataclass
class CounterState:
    total: int = 0


@g.step
async def accumulate(ctx: StepContext[CounterState, None, int]) -> int:
    ctx.state.total += ctx.inputs      # ← 副作用（注意：这里安全，原因见下方说明）
    return ctx.inputs


ignore = g.join(reduce_null, initial=None)    # ← 丢掉所有返回值
# 说明：4.2 节警告过"并行分支里别做读-改-写"，这里的 += 为什么安全？
# 因为 asyncio 是单线程，而 `ctx.state.total += ctx.inputs` 这一行中间没有 await 点，
# 不会被其他任务插进来。但只要中间出现 await（查库、调 API），就会真的丢更新——
# 那时必须改用 join 的 reducer 来累加，不能直接改 state。


@g.step
async def get_total(ctx: StepContext[CounterState, None, None]) -> int:
    return ctx.state.total             # ← 从 state 里取


g.add(
    g.edge_from(g.start_node).to(generate),
    g.edge_from(generate).map().to(accumulate),
    g.edge_from(accumulate).to(ignore),
    g.edge_from(ignore).to(get_total),
    g.edge_from(get_total).to(g.end_node),
)
```

实跑输出（输入 `[1,2,3,4,5]`）：

```text
reduce_null -> 15
```

这里 `reduce_null` 起的是**同步栅栏**的作用："等所有并行任务都跑完，再往下走"。

> 👉 **PM 视角**：reducer 就是"**汇总规则**"。同样是"三个部门并行审批"，汇总规则决定了业务语义：
> - `reduce_list_append` → 收集三份意见，都留着
> - `reduce_dict_update` → 三个部门填同一张表的不同栏
> - `ReduceFirstValue` → 一票通过制（谁先批了就算过，其余撤销）
> - 自定义 → 一票否决制（见下面）
>
> **PRD 里写并行审批时，必须明确写清汇总规则**，否则工程师会随便选一个。

#### 5.6.3 自定义 reducer + `cancel_sibling_tasks()`

reducer 有两种签名，库会根据参数个数自动识别：

```python
# 简单版：2 个参数
def reduce_sum(current: int, inputs: int) -> int:
    return current + inputs

# 带上下文版：3 个参数，能读 state/deps，能取消兄弟任务
def reduce_find(ctx: ReducerContext[SearchState, None], current: str | None, inputs: str) -> str | None:
    ...
```

**"一票否决 / 找到就停"的完整例子：**

```python
import asyncio
from dataclasses import dataclass
from pydantic_graph import GraphBuilder, StepContext, ReducerContext


@dataclass
class SearchState:
    done: int = 0


def reduce_find(ctx: ReducerContext[SearchState, None], current: str | None, inputs: str) -> str | None:
    if current is not None:
        return current                  # 已经找到了，忽略后来的
    if '命中' in inputs:
        ctx.cancel_sibling_tasks()      # ← 找到了！取消所有还在跑的兄弟任务
        return inputs
    return None


g = GraphBuilder(state_type=SearchState, output_type=str | None)


@g.step
async def candidates(ctx: StepContext[SearchState, None, None]) -> list[str]:
    return ['渠道A', '渠道B', '渠道C命中', '渠道D', '渠道E']


@g.step
async def query(ctx: StepContext[SearchState, None, str]) -> str:
    await asyncio.sleep(0.1 if ctx.inputs not in {'渠道D', '渠道E'} else 1.0)
    ctx.state.done += 1
    return ctx.inputs


find = g.join(reduce_find, initial=None)

g.add(
    g.edge_from(g.start_node).to(candidates),
    g.edge_from(candidates).map().to(query),
    g.edge_from(query).to(find),
    g.edge_from(find).to(g.end_node),
)

graph = g.build()


async def main():
    st = SearchState()
    print('结果:', await graph.run(state=st))
    print('实际执行的查询数:', st.done)
```

实跑输出：

```text
结果: 渠道C命中
实际执行的查询数: 3
```

**5 个候选渠道，只真的跑了 3 个**——找到目标后，剩下两个慢任务被取消了。

`ReducerContext` 上有什么：

| 成员 | 说明 |
|---|---|
| `.state` | 图的状态（可读可写） |
| `.deps` | 图的依赖 |
| `.cancel_sibling_tasks()` | 取消同一个 fork 产生的所有其他并行任务 |

**reducer 也可以写 state**，官方例子（实跑验证）：

```python
def reduce_metrics_sum(ctx: ReducerContext[MetricsState, None],
                       current: ReducedMetrics, inputs: int) -> ReducedMetrics:
    ctx.state.total_count += 1        # ← 全局计数
    ctx.state.total_sum += inputs
    return ReducedMetrics(count=current.count + 1, sum=current.sum + inputs)
```

配合"奇偶分流 → 各自 reduce → 再 reduce 取最大值"的三层 join，实跑输出：

```text
Result: ReducedMetrics(count=5, sum=200)
state.total_count: 9
state.total_sum: 275
```

`render()` 输出（三个 `<<join>>`）：

```text
stateDiagram-v2
  generate
  state map <<fork>>
  state decision <<choice>>
  process_even
  process_odd
  state metrics_even <<join>>
  state metrics_odd <<join>>
  state metrics_max <<join>>

  [*] --> generate
  generate --> map
  map --> decision
  decision --> process_even: 偶数
  decision --> process_odd: 奇数
  process_even --> metrics_even
  process_odd --> metrics_odd
  metrics_even --> metrics_max
  metrics_odd --> metrics_max
  metrics_max --> [*]
```

> 👉 **PM 视角**：`cancel_sibling_tasks()` 是**省钱开关**。场景：让 3 个不同的模型同时回答同一个问题，谁先给出可用答案就用谁，其余立刻掐掉。如果不掐，你要为 3 次调用全额付费；掐了，只付大约 1 次多一点。
>
> 在做"多模型兜底"、"多供应商比价"这类设计时，**一定要问工程师：慢的那些请求取消了吗？**

### 5.7 边上的转换：`.transform()`

有时候上游的输出格式和下游要的对不上，为此专门写一个 step 太重。`.transform()` 让你在**边上**做一次转换：

```python
g.edge_from(fetch_orders)
 .transform(lambda ctx: [o['id'] for o in ctx.inputs])    # 提取 id
 .label('取出订单号')
 .map()                                                    # 再扇出
 .to(notify)
```

实跑（输入 `[{'id': 101, 'amount': 30}, {'id': 102, 'amount': 80}]`）：

```text
['已通知订单 101', '已通知订单 102']
```

`render(title='订单通知流程', direction='LR')` 输出：

```text
---
title: 订单通知流程
---
stateDiagram-v2
  direction LR
  fetch_orders
  state map <<fork>>
  notify
  state reduce_list_append <<join>>

  [*] --> fetch_orders
  fetch_orders --> map: 取出订单号
  map --> notify
  notify --> reduce_list_append
  reduce_list_append --> [*]
```

`.transform()` 的函数签名是 `(StepContext) -> 新值`，注意：

| 特点 | 说明 |
|---|---|
| 参数是 `StepContext` | 所以能读 `ctx.state` / `ctx.deps` / `ctx.inputs` |
| **是同步函数** | 不是 async，不能在里面 `await` |
| 不产生图节点 | 在 mermaid 里看不到，转换是"隐形"的 |
| 可以链式组合 | `.transform().label().map().to()` |

边上可用的链式方法一览：

| 方法 | 作用 | 是否产生节点 |
|---|---|---|
| `.to(A)` / `.to(A, B, C)` | 指定目标（多个 = 广播） | 多目标时产生 `<<fork>>` |
| `.map(fork_id=, downstream_join_id=)` | 扇出 | 产生 `<<fork>>` |
| `.broadcast(lambda b: [...], fork_id=)` | 显式广播，每支路可独立配置 | 产生 `<<fork>>` |
| `.transform(func)` | 转换数据 | ❌ 不产生 |
| `.label('...')` | 给边打标签 | ❌ 不产生 |

> ⚠️ **坑**：`.transform()` 是同步的。如果你需要 `await`（查数据库、调 API），必须老老实实写一个 `@g.step`。

> 👉 **PM 视角**：transform 是**格式适配**，不是业务逻辑。判断标准：如果这段转换需要写进 PRD、需要业务方确认、可能会变，那它就该是一个有名字的 step（这样它会出现在流程图上）。如果只是"把 dict 里的 id 取出来"这种纯技术胶水，用 transform，别污染流程图。

### 5.8 空集合的坑：`downstream_join_id`

`.map()` 一个**空列表**会怎样？没有任何并行任务被创建，那么下游的 join **永远等不到东西，这条支路会被整个跳过**。

解决办法是告诉 map："如果我是空的，直接跳到这个 join"：

```python
collect2 = g2.join(reduce_list_append, initial_factory=list[str])

g2.add(g2.edge_from(g2.start_node).to(fetch_nothing))
g2.add_mapping_edge(fetch_nothing, handle, downstream_join_id=collect2.id)   # ← 关键
g2.add(
    g2.edge_from(handle).to(collect2),
    g2.edge_from(collect2).to(g2.end_node),
)
```

实跑输出：

```text
[]
```

正确地拿到了空列表，而不是抛 `RuntimeError`。

用 `.map()` 链式写法时同样可以传：

```python
g.edge_from(source).map(downstream_join_id=collect.id).to(handle)
```

> ⚠️ **坑**：这是一个**极容易漏、且在测试环境很难复现**的问题。开发时列表总是有数据的，上线后遇到"这个用户一条订单都没有"就挂了。
>
> **规则：只要边上有 `.map()`，就把 `downstream_join_id` 填上。** 成本为零，能省掉一次线上事故。

> 👉 **PM 视角**：这就是经典的"**空状态没考虑**"。PM 在评审时可以直接问工程师一句："这个批量处理，如果一条数据都没有会怎样？" 在这个库里，答案要么是"配了 `downstream_join_id`，正常返回空"，要么是"没配——**简单图形直接抛 `RuntimeError: Graph run completed, but no result was produced`；多分支图形更糟，那条支路的数据被静默丢掉，结果对不上却不报错**"。后者是真正危险的那种。

### 5.9 嵌套并行

fork 可以嵌套，库会自动追踪每个任务属于哪一层 fork（内部叫 `fork_stack`）。

**map 之后再 broadcast** ——每个元素都发给两个下游：

```python
g.edge_from(gen2).map().to(add_one, add_two)
```

输入 `[10, 20]`，实跑输出：

```text
[11, 12, 21, 22]
```

（10→11、10→12、20→21、20→22，一共 4 个并行任务。）

`render()` 输出（两个 fork 串起来）：

```text
stateDiagram-v2
  gen2
  state map <<fork>>
  state broadcast <<fork>>
  add_one
  add_two
  state reduce_list_append <<join>>

  [*] --> gen2
  gen2 --> map
  map --> broadcast
  broadcast --> add_one
  broadcast --> add_two
  add_one --> reduce_list_append
  add_two --> reduce_list_append
  reduce_list_append --> [*]
```

**连续两次 map** ——列表的列表：

```python
g3.edge_from(pairs).map().to(unpack)        # [(1,2),(3,4)] → 2 个任务
g3.edge_from(unpack).map().to(stringify)    # 每个 tuple 拆成 2 个 → 共 4 个任务
```

实跑输出：

```text
['num:1', 'num:2', 'num:3', 'num:4']
```

`render()` 输出（`map` 和 `map_2`）：

```text
stateDiagram-v2
  pairs
  state map <<fork>>
  unpack
  state map_2 <<fork>>
  stringify
  state reduce_list_append <<join>>

  [*] --> pairs
  pairs --> map
  map --> unpack
  unpack --> map_2
  map_2 --> stringify
  stringify --> reduce_list_append
  reduce_list_append --> [*]
```

> 👉 **PM 视角**：嵌套并行 = "**对每个门店的每个 SKU 都算一遍**"。任务数是乘法关系（10 个门店 × 200 个 SKU = 2000 个并行任务），**很容易失控**。做这类需求时，务必让工程师给出并发上限和预估耗时/成本。

### 5.10 多个独立的 join

一张图里可以有多个互不相干的 join，用 `node_id=` 区分：

```python
join_t = g.join(reduce_list_append, initial_factory=list[int], node_id='join_tmall')
join_j = g.join(reduce_list_append, initial_factory=list[int], node_id='join_jd')
```

完整例子——两个电商平台并行比价：

```python
g.add(
    g.edge_from(g.start_node).to(crawl_tmall, crawl_jd),   # 广播：两条流水线
    g.edge_from(crawl_tmall).map().to(price_tmall),        # 各自 map
    g.edge_from(crawl_jd).map().to(price_jd),
    g.edge_from(price_tmall).to(join_t),                   # 各自 join
    g.edge_from(price_jd).to(join_j),
    g.edge_from(join_t).to(store_t),
    g.edge_from(join_j).to(store_j),
    g.edge_from(store_t, store_j).to(report),              # 合流
    g.edge_from(report).to(g.end_node),
)
```

实跑输出：

```text
{'京东': [30, 60], '天猫': [2, 4, 6]}
```

`render()` 输出：

```text
stateDiagram-v2
  state broadcast <<fork>>
  crawl_jd
  crawl_tmall
  state map <<fork>>
  state map_2 <<fork>>
  price_jd
  price_tmall
  state join_jd <<join>>
  state join_tmall <<join>>
  store_j
  store_t
  report

  [*] --> broadcast
  broadcast --> crawl_jd
  broadcast --> crawl_tmall
  crawl_jd --> map_2
  crawl_tmall --> map
  map --> price_tmall
  map_2 --> price_jd
  price_jd --> join_jd
  price_tmall --> join_tmall
  join_jd --> store_j
  join_tmall --> store_t
  store_j --> report
  store_t --> report
  report --> [*]
```

> 💡 **提示**：多个 join 用同一个 reducer 时，默认 ID 会自动加后缀（`reduce_list_append`、`reduce_list_append_2`），**不会报错**。但图上认不出谁是谁——建议手动给业务化的 `node_id`。

> 👉 **PM 视角**：这张图是"**多渠道数据聚合**"的标准结构——各渠道独立采集、独立汇总、最后合并出报表。图上一眼能看出"天猫和京东这两条线是完全隔离的"，出问题时能快速定位是哪条线挂了。

---

## 六、观察与控制执行

`graph.run()` 是黑盒——扔进去，等结果出来。但真实业务里你经常需要：

- 看到流程走到哪一步了（进度条、审计日志）
- 在某一步之前拦一下（人工干预、灰度实验）
- 某一步失败了，走另一条路（降级、转人工）
- 提前结束（熔断、超时）

这些都靠 `graph.iter()` 和 `GraphRun` 完成。这一节讲：

1. `iter()` 的基本用法
2. `GraphRun` 上有什么
3. `next_task` 偷看下一步
4. `override_next()` 改写下一步（人工干预）
5. `ErrorMarker` 错误恢复
6. `EndMarker` 提前熔断

### 6.1 `iter()`：逐步执行

```python
import asyncio
from dataclasses import dataclass
from pydantic_graph import GraphBuilder, StepContext


@dataclass
class CounterState:
    value: int = 0


g = GraphBuilder(state_type=CounterState, output_type=int)


@g.step
async def increment(ctx: StepContext[CounterState, None, None]) -> int:
    ctx.state.value += 1
    return ctx.state.value


@g.step
async def double_it(ctx: StepContext[CounterState, None, int]) -> int:
    return ctx.inputs * 2


g.add(
    g.edge_from(g.start_node).to(increment),
    g.edge_from(increment).to(double_it),
    g.edge_from(double_it).to(g.end_node),
)

graph = g.build()


async def main():
    state = CounterState()
    async with graph.iter(state=state) as run:
        print(f'开始前 state.value={state.value}')
        print(f'即将执行: {run.next_task}')
        async for event in run:
            print(f'state.value={state.value} | event={event}')
        print(f'最终输出: {run.output}')
```

实跑输出：

```text
开始前 state.value=0
即将执行: [GraphTask(node_id='__start__', inputs=None)]
state.value=0 | event=[GraphTask(node_id='increment', inputs=None)]
state.value=1 | event=[GraphTask(node_id='double_it', inputs=1)]
state.value=1 | event=[GraphTask(node_id='__end__', inputs=2)]
state.value=1 | event=EndMarker(_value=2)
最终输出: 2
```

**读法**：每次 `async for` 拿到的 `event` 是"**下一批要执行的任务**"，不是"刚执行完的结果"。

- 第 1 次：`[GraphTask(node_id='increment', ...)]` → 起点跑完了，下一步要跑 `increment`
- 第 2 次：`[GraphTask(node_id='double_it', inputs=1)]` → `increment` 跑完返回 1，下一步跑 `double_it`
- 第 3 次：`[GraphTask(node_id='__end__', inputs=2)]` → 下一步到终点
- 第 4 次：`EndMarker(_value=2)` → 结束，输出是 2

注意 `event` 是一个**列表**——并行时会有多个任务同时待执行。

> ⚠️ **注意**：`iter()` 必须用 `async with`。它是一个异步上下文管理器，退出时会清理内部的任务组。

> 👉 **PM 视角**：这就是**流程实例的实时状态**。有了它你可以做：
> - 前端进度条："正在核验身份（2/5）"
> - 审计日志：每一步的时间戳、输入、输出全落库
> - 超时告警：某一步卡了 30 秒就报警
>
> 这些能力在 `graph.run()` 那个黑盒模式下是拿不到的。

### 6.2 `GraphRun` 面板

| 成员 | 类型 | 说明 |
|---|---|---|
| `.state` | `StateT` | 这次运行的状态对象 |
| `.deps` | `DepsT` | 这次运行的依赖 |
| `.inputs` | `InputT` | 初始输入 |
| `.next_task` | `EndMarker \| ErrorMarker \| Sequence[GraphTask]` | **下一步要执行什么**（可以在执行前偷看） |
| `.output` | `OutputT \| None` | 跑完了就是结果，没跑完是 `None` |
| `await .next(value=None)` | | 手动推进一步，可选地塞一个值进去 |
| `.override_next(value)` | | **改写下一步**（关键能力） |
| `async for x in run` | | 自动推进直到结束 |

`GraphTask` 的字段：

| 字段 | 说明 |
|---|---|
| `.node_id` | 要跑哪个节点（字符串 ID） |
| `.inputs` | 传给它的数据 |
| `.fork_stack` | 内部用，标记它属于哪次 fork（`repr` 里隐藏了） |
| `.task_id` | 内部用的唯一任务 ID |

**两种驱动方式：**

```python
# 方式一：async for，自动推进
async for event in run:
    ...

# 方式二：await run.next()，手动推进（能在中间插手）
while True:
    try:
        event = await run.next()
    except StopAsyncIteration:
        break
    ...
```

方式二更啰嗦，但只有它能配合 `override_next()`。

### 6.3 `override_next()`：人工干预

**场景：流程本来要走 A，但基于某些运行时信息（风控、灰度、人工介入），我要它改走 B。**

```python
import asyncio
from dataclasses import dataclass
from pydantic_graph import EndMarker, GraphBuilder, GraphTaskRequest, StepContext


@dataclass
class S:
    trail: list[str]


g = GraphBuilder(state_type=S, input_type=float, output_type=str)


@g.step
async def submit(ctx: StepContext[S, None, float]) -> float:
    ctx.state.trail.append('提交')
    return ctx.inputs


@g.step
async def auto_approve(ctx: StepContext[S, None, float]) -> str:
    ctx.state.trail.append('自动通过')
    return f'{ctx.inputs} 元自动通过'


@g.step
async def human_approve(ctx: StepContext[S, None, float]) -> str:
    ctx.state.trail.append('人工审批')
    return f'{ctx.inputs} 元人工批准'


g.add(
    g.edge_from(g.start_node).to(submit),
    g.edge_from(submit).to(auto_approve),
    g.edge_from(auto_approve).to(g.end_node),
    g.edge_from(human_approve).to(g.end_node),      # human_approve 不在主干上
)

# ⚠️ human_approve 从起点不可达，必须关掉结构校验
graph = g.build(validate_graph_structure=False)


async def main():
    state = S(trail=[])
    async with graph.iter(state=state, inputs=8888.0) as run:
        while True:
            try:
                event = await run.next()
            except StopAsyncIteration:
                break
            print(f'event={event}')
            tasks = run.next_task
            if isinstance(tasks, list) and tasks and tasks[0].node_id == 'auto_approve':
                print('>>> 拦截: 金额太大，改走人工')
                run.override_next([
                    GraphTaskRequest(node_id='human_approve', inputs=tasks[0].inputs, fork_stack=())
                ])
            if run.output is not None:
                break
    print('输出:', run.output)
    print('轨迹:', state.trail)
```

实跑输出：

```text
event=[GraphTask(node_id='auto_approve', inputs=8888.0)]
>>> 拦截: 金额太大，改走人工
event=[GraphTask(node_id='__end__', inputs='8888.0 元人工批准')]
event=EndMarker(_value='8888.0 元人工批准')
输出: 8888.0 元人工批准
轨迹: ['提交', '人工审批']
```

**`auto_approve` 完全没有执行**——它被拦截并替换成了 `human_approve`。

`GraphTaskRequest` 的三个字段：

| 字段 | 填什么 |
|---|---|
| `node_id` | 目标节点的 ID（step 的函数名 / BaseNode 的类名 / 自定义 `node_id`） |
| `inputs` | 传给它的数据 |
| `fork_stack` | 非并行场景填 `()`；并行场景要沿用原任务的 `fork_stack`，否则 join 会等不到 |

> ⚠️ **坑 1**：如果被跳转的目标节点从起点**不可达**（像上面的 `human_approve`），`build()` 会直接报错：
>
> ```text
> GraphValidationError: The following nodes are not reachable from the start node:
> ['human_approve']. If this is intentional, you can suppress this error by passing
> `validate_graph_structure=False` to the call to `GraphBuilder.build`.
> ```
>
> 报错信息本身给了解法：`g.build(validate_graph_structure=False)`。

> ⚠️ **坑 2**：`override_next()` **只能在两次迭代之间调用**，不能在某一步执行到一半的时候调。

> 👉 **PM 视角**：这是"**人在回路（human-in-the-loop）**"的技术底座。产品形态可以是：
> - 大额订单自动暂停，等运营在后台点"批准"再继续
> - AI 生成的内容先进人工审核队列，通过了才发布
> - A/B 实验：5% 的流量在某个节点被劫持到新流程
>
> 注意：这个库**没有内置"暂停等人工，几天后再继续"的能力**（没有持久化，见第十节）。你能做的是"在同一个进程内、同一次运行中拦截并改道"。真正的长时间挂起需要额外方案。

### 6.4 `ErrorMarker`：错误恢复

**场景：某个节点抛异常了，我不想整条流程崩掉，想走降级路径。**

这个库的做法很特别：节点抛异常时，不是立刻往上抛，而是**先 yield 一个 `ErrorMarker`**，给你一次接管的机会。源码注释原话：

> "Yielded by the graph iterator instead of raising immediately, allowing the caller to recover by sending new tasks via `GraphRun.next()` or `GraphRun.override_next()`. **If the caller does not override, the error is re-raised on the next iteration.**"

翻译：错误会先被包成 `ErrorMarker` 交给你。如果你不处理，下一次迭代时它会真的被抛出来。

```python
import asyncio
from dataclasses import dataclass
from pydantic_graph import GraphBuilder, GraphTaskRequest, StepContext


@dataclass
class PayState:
    attempts: int = 0


g = GraphBuilder(state_type=PayState, input_type=str, output_type=str)


@g.step
async def call_gateway(ctx: StepContext[PayState, None, str]) -> str:
    ctx.state.attempts += 1
    raise RuntimeError(f'支付网关超时 (第 {ctx.state.attempts} 次)')


@g.step
async def manual_review(ctx: StepContext[PayState, None, str]) -> str:
    return f'{ctx.inputs} 转人工处理'


g.add(
    g.edge_from(g.start_node).to(call_gateway),
    g.edge_from(call_gateway).to(g.end_node),
    g.edge_from(manual_review).to(g.end_node),
)

graph = g.build(validate_graph_structure=False)


async def main():
    state = PayState()
    async with graph.iter(state=state, inputs='订单8888') as run:
        while True:
            try:
                event = await run.next()
            except StopAsyncIteration:
                break
            except RuntimeError as exc:                    # ← 节点抛的异常在这里被捕获
                print(f'捕获异常: {exc}')
                print(f'出错时的 next_task: {run.next_task}')
                run.override_next([                        # ← 改道到降级流程
                    GraphTaskRequest(node_id='manual_review', inputs='订单8888', fork_stack=())
                ])
                continue
            print(f'event={event}')
            if run.output is not None:
                print(f'最终输出: {run.output}')
                break
```

实跑输出：

```text
捕获异常: 支付网关超时 (第 1 次)
出错时的 next_task: ErrorMarker(error=RuntimeError('支付网关超时 (第 1 次)'))
event=[GraphTask(node_id='__end__', inputs='订单8888 转人工处理')]
event=EndMarker(_value='订单8888 转人工处理')
最终输出: 订单8888 转人工处理
```

**关键点：**

| 点 | 说明 |
|---|---|
| 异常从 `await run.next()` 抛出 | 用普通的 `try/except` 捕获 |
| `run.next_task` 变成 `ErrorMarker(error=...)` | 可以从里面拿到原始异常对象 |
| 恢复方式 | 在 `except` 块里调 `override_next([...])`，然后 `continue` |
| 不恢复会怎样 | 下一次 `next()` 时错误被重新抛出，整个 run 结束 |
| **重试**怎么做 | `override_next` 到**同一个** `node_id`，就是重试。自己数次数 |

> 👉 **PM 视角**：这是"**失败降级**"的技术底座。PRD 里写"支付失败转人工"、"AI 生成失败回退到模板文案"、"三方接口超时用缓存数据"，靠的都是这个机制。
>
> 评审时值得逐个节点问：**"这一步失败了怎么办？重试几次？重试完还不行走哪？"** 在这个库里，这三个问题的答案就是 `except` 块里的那几行代码。

### 6.5 `EndMarker`：提前熔断

`override_next()` 除了接受任务列表，还能接受一个 `EndMarker`，表示"**别跑了，直接用这个值结束**"：

```python
import asyncio
from pydantic_graph import EndMarker, GraphBuilder, StepContext

g = GraphBuilder(input_type=int, output_type=str)


@g.step
async def s1(ctx: StepContext[None, None, int]) -> int:
    return ctx.inputs + 1


@g.step
async def s2(ctx: StepContext[None, None, int]) -> str:
    return f'走完了全流程, 值={ctx.inputs}'


g.add(
    g.edge_from(g.start_node).to(s1),
    g.edge_from(s1).to(s2),
    g.edge_from(s2).to(g.end_node),
)
graph = g.build()


async def main():
    async with graph.iter(inputs=1) as run:
        while True:
            try:
                event = await run.next()
            except StopAsyncIteration:
                break
            print('event =', event)
            tasks = run.next_task
            if isinstance(tasks, list) and tasks and tasks[0].node_id == 's2':
                print('>>> 提前熔断，不跑 s2 了')
                run.override_next(EndMarker('人工提前终止'))     # ← 直接结束
            if run.output is not None:
                break
        print('输出:', run.output)
```

实跑输出：

```text
event = [GraphTask(node_id='s2', inputs=2)]
>>> 提前熔断，不跑 s2 了
输出: 人工提前终止
```

`s2` 一次都没跑。而且如果当时有并行任务在跑，**它们会被一起取消**（源码里 `EndMarker` 分支会调 `task_group.cancel_scope.cancel()`）。

> 👉 **PM 视角**：熔断的三个典型触发条件——**超时、超预算、人工叫停**。
> - 超时：跑了 30 秒还没完，返回"处理中，稍后通知"
> - 超预算：这一次运行已经烧了 5 块钱的 token，停
> - 人工叫停：运营在后台点了"终止"
>
> 这三个都是产品需求，实现上都是同一个 `override_next(EndMarker(...))`。

### 6.6 三种执行控制的对照

| 我想 | 用什么 | 结果 |
|---|---|---|
| 只想看进度，不干预 | `async for event in run` | 拿到每一步的 `GraphTask` 列表 |
| 想在某步之前改道 | `run.next()` 循环 + `override_next([GraphTaskRequest(...)])` | 原定节点不执行，改跑新节点 |
| 某步失败了想降级 | `try/except` 捕获 + `override_next([...])` | 错误被吞掉，走降级路径 |
| 想立刻结束 | `override_next(EndMarker(值))` | 剩余任务全取消，`output` 就是那个值 |
| 想重试同一步 | `override_next([GraphTaskRequest(同一个 node_id, ...)])` | 该节点再跑一次 |

---

## 七、可视化：`render()`

前面每一节都在用它了，这一节系统讲一遍。

### 7.1 基本用法

```python
mermaid_source: str = graph.render()
print(mermaid_source)

# 或者更短
print(graph)      # Graph.__str__ 就是 render()
```

`render()` 返回一个**字符串**（mermaid 的 `stateDiagram-v2` 源码）。它不生成图片、不写文件、不联网——就是一段文本。你需要把这段文本粘到任何支持 mermaid 的地方：

| 工具 | 支持情况 |
|---|---|
| GitHub / GitLab 的 Markdown | ✅ 原生支持 mermaid 代码块（代码块语言标注为 `mermaid`） |
| Notion | ✅ 代码块选 Mermaid |
| 飞书文档 | ✅ 支持 |
| VS Code | ✅ 装 Markdown Preview Mermaid Support 插件 |
| mermaid.live | ✅ 在线粘贴即渲染 |

### 7.2 两个参数

```python
graph.render(title='订单通知流程', direction='LR')
```

| 参数 | 取值 | 效果 |
|---|---|---|
| `title=` | 任意字符串 | 在开头加一个 YAML front matter 的标题块 |
| `direction=` | `'TB'` / `'LR'` / `'RL'` / `'BT'` | 图的方向：上下 / 左右 / 右左 / 下上 |

实跑输出：

```text
---
title: 订单通知流程
---
stateDiagram-v2
  direction LR
  fetch_orders
  state map <<fork>>
  notify
  state reduce_list_append <<join>>

  [*] --> fetch_orders
  fetch_orders --> map: 取出订单号
  map --> notify
  notify --> reduce_list_append
  reduce_list_append --> [*]
```

> 💡 经验：**节点少用 `TB`（默认，上下），节点多用 `LR`（左右）**。上下排列超过 10 个节点就会很长，左右排更适合宽屏和 PPT。

### 7.3 各类节点在 mermaid 里长什么样

这张表是读图的钥匙：

| 图元素 | mermaid 语法 | 视觉 | 对应什么 |
|---|---|---|---|
| 起点 / 终点 | `[*]` | 实心圆 / 同心圆 | `g.start_node` / `g.end_node` |
| 普通步骤 | `节点ID` | 圆角矩形 | `@g.step` / `@g.stream` |
| 带标签的步骤 | `节点ID: 中文标签` | 圆角矩形，显示标签 | `@g.step(label='...')` |
| BaseNode 节点 | `类名` | 圆角矩形 | `g.node(X)` 注册的 `BaseNode` |
| 判定 | `state 节点ID <<choice>>` | **菱形** | `g.decision()` 或返回类型 union 自动生成 |
| 判定的说明 | `note right of 节点ID ... end note` | 便签 | `g.decision(note='...')` |
| 扇出 | `state 节点ID <<fork>>` | **粗横线** | `.map()` / `.broadcast()` / `.to(A,B,C)` |
| 扇入 | `state 节点ID <<join>>` | **粗横线** | `g.join(...)` |
| 边 | `A --> B` | 箭头 | 任何连接 |
| 带标签的边 | `A --> B: 标签` | 箭头 + 文字 | `.label('...')` / `g.add_edge(..., label=)` |

**自动生成的节点 ID 命名规律：**

| 类型 | 第一个 | 第二个 | 第三个 |
|---|---|---|---|
| 判定 | `decision` | `decision_2` | `decision_3` |
| map 扇出 | `map` | `map_2` | `map_3` |
| broadcast 扇出 | `broadcast` | `broadcast_2` | ... |
| join | reducer 函数名（如 `reduce_list_append`） | 冲突时需手动 `node_id=` | |

### 7.4 一个"全家福"图

把前面所有元素放一张图里（这是 5.6.3 那个例子的真实输出）：

```text
stateDiagram-v2
  generate
  state map <<fork>>
  state decision <<choice>>
  process_even
  process_odd
  state metrics_even <<join>>
  state metrics_odd <<join>>
  state metrics_max <<join>>

  [*] --> generate
  generate --> map
  map --> decision
  decision --> process_even: 偶数
  decision --> process_odd: 奇数
  process_even --> metrics_even
  process_odd --> metrics_odd
  metrics_even --> metrics_max
  metrics_odd --> metrics_max
  metrics_max --> [*]
```

读法：起点 → `generate` 产出一个列表 → `map` 扇出（每个数字一个任务）→ `decision` 判断奇偶 → 分别处理 → 各自 join → 再 join 一次取最大值 → 终点。

### 7.5 顺便：看图里有哪些节点

```python
for nid, node in graph.nodes.items():
    print(f'{nid:20} {type(node).__name__}')
```

```text
__start__            StartNode
profile              Step
make_copy            Step
__end__              EndNode
```

`graph.nodes` 是一个 `dict[节点ID, 节点对象]`，可以用来做自动化检查（比如 CI 里断言"关键节点必须存在"）。

> 👉 **PM 视角**：`render()` 的最大价值是**让流程文档自动化**。建议推动的三件事：
>
> 1. **CI 里自动更新流程图**：每次代码合并，自动把 `render()` 的结果写进文档仓库。流程图永不过期。
> 2. **要求每个节点有中文 `label`**：这是把工程图变成业务图的唯一成本。
> 3. **关键判断点写 `note`**：把业务规则（"1000 元是分水岭"）写在图上，评审时一目了然。
>
> 做到这三点，你的流程 PRD 和线上实现就永远是一致的——这在传统研发流程里几乎不可能做到。

---

## 八、杀手级认知：Agent 循环本身就是一张图

前面七节讲的都是"你怎么用这个库画图"。这一节讲一件更重要的事：**你在第二部分用的 `pydantic_ai.Agent`，它内部就是用 `pydantic_graph` 搭出来的。**

这不是类比，是字面意义上的——`pydantic_ai/_agent_graph.py` 里有一个函数叫 `build_agent_graph()`，里面就是 `GraphBuilder(...)` + `g.add(...)` + `g.build()`。

理解了这件事，你对 Agent 的认知会从"一个黑盒"变成"一张我能看懂、能观察、能干预的图"。

### 8.1 把 Agent 的图打印出来

三行代码：

```python
from pydantic_ai._agent_graph import build_agent_graph

print(build_agent_graph(name='MyAgent', deps_type=type(None), output_type=str).render())
```

实跑输出：

```text
stateDiagram-v2
  UserPromptNode
  state decision <<choice>>
  CallToolsNode
  ModelRequestNode
  state decision_2 <<choice>>
  state decision_3 <<choice>>
  SetFinalResult

  [*] --> UserPromptNode
  UserPromptNode --> decision
  decision --> CallToolsNode
  decision --> ModelRequestNode
  CallToolsNode --> decision_3
  ModelRequestNode --> decision_2
  decision_2 --> CallToolsNode
  decision_2 --> ModelRequestNode
  decision_3 --> ModelRequestNode
  decision_3 --> [*]
  SetFinalResult --> [*]
```

**这就是每一个 pydantic-ai Agent 内部真实跑的流程图。**

把它整理成人话：

```text
      [用户发起]
          │
          ▼
  ┌─────────────────┐
  │ UserPromptNode  │  处理用户输入、系统提示词、instructions
  └────────┬────────┘
           │  ◇ 判断：有历史待处理的响应吗？
     ┌─────┴─────┐
     ▼           ▼
┌──────────────┐ ┌──────────────────┐
│CallToolsNode │ │ ModelRequestNode │  ←──────┐
└──────┬───────┘ └────────┬─────────┘         │
       │                  │                    │
       │                  │ ◇ 流式出结果了？    │
       │            ┌─────┴─────┐              │
       │            ▼           ▼              │
       │      CallToolsNode  ModelRequestNode ─┘
       │            │
       │◇ 模型说完了 vs 还要调工具
   ┌───┴────┐
   ▼        ▼
[结束]  ModelRequestNode ──┐
                            └──→ 回到上面，循环
```

**注意那个 `SetFinalResult --> [*]`**：它是一条"孤岛边"，从起点不可达。这也是为什么源码里 `build_agent_graph` 最后一行是 `return g.build(validate_graph_structure=False)` ——它明确关掉了"所有节点必须从起点可达"的校验。`SetFinalResult` 只有在流式场景下由 `agent_run.next(SetFinalResult(...))` 手动注入才会被执行，正好就是第六节讲的 `override_next` 那套机制。

### 8.2 四个节点各自在干嘛

我从 `pydantic_ai/_agent_graph.py` 里把每个节点类的 docstring 原文摘出来了：

| 节点 | 源码 docstring 原文 | 人话 | 类比 |
|---|---|---|---|
| `UserPromptNode` | "The node that handles the user prompt and instructions." | 组装第一条请求：把用户输入、system prompt、instructions（含动态生成的）、历史消息拼成一个 `ModelRequest` | **前台接待**：收单、贴标签、补齐资料 |
| `ModelRequestNode` | "The node that makes a request to the model using the last message in `state.message_history`." | 真正发 HTTP 请求给大模型，拿回 `ModelResponse` | **对外发函**：把材料寄给专家，等回信 |
| `CallToolsNode` | "The node that processes a model response, and decides whether to end the run or make a new request." | 解析模型响应：有工具调用就执行工具，把结果拼成新请求；没有就产出最终输出 | **分拣室**：拆开回信，看是"要补材料"还是"结论出了" |
| `SetFinalResult` | "A node that immediately ends the graph run after a streaming response produced a final result." | 流式场景专用：流里已经识别出最终结果了，直接结束 | **快速通道**：结论已经在传真的过程中拿到了，不用等信到 |

**几个关键细节：**

`UserPromptNode` 有两条出边（`decision` → `CallToolsNode` 或 `ModelRequestNode`）。为什么会直接去 `CallToolsNode`？因为**恢复历史对话**的场景——如果 `message_history` 的最后一条已经是模型响应了（比如上次运行中断在工具调用前），就不用再请求模型，直接去处理工具。

`ModelRequestNode` 也有两条出边（`decision_2`）：正常路径去 `CallToolsNode`；但如果是流式且中途遇到需要续跑的情况（比如 Anthropic 的 `pause_turn`、OpenAI 的 background mode），会回到 `ModelRequestNode` 自己。

`CallToolsNode` 的两条出边（`decision_3`）是整个循环的心脏：

- `→ ModelRequestNode`：模型要调工具 → 工具执行完 → 把结果塞回去再问一次 → **这就是 Agent 循环**
- `→ [*]`：模型给出了最终输出 → 结束

> 👉 **PM 视角**：这四个节点，正好对应你在 Agent 产品里关心的四个指标：
>
> | 节点 | 你该关心的指标 |
> |---|---|
> | `UserPromptNode` | prompt 有多长？（影响成本）动态 instructions 拼对了吗？ |
> | `ModelRequestNode` | 调了几次模型？（`ModelRequestNode` 出现几次 = 花了几次钱）延迟多少？ |
> | `CallToolsNode` | 调了哪些工具？工具失败率多少？ |
> | 循环次数 | `ModelRequestNode ↔ CallToolsNode` 转了几圈？转太多圈说明模型在"打转"，要优化 prompt 或工具描述 |
>
> **"Agent 转了几圈"是一个非常实用的产品指标**，它同时反映成本、延迟和 Agent 设计质量。而它就是这张图上的循环次数。

### 8.3 实际跑一次，看它经过哪些节点

用 `TestModel`（离线的假模型，不联网不花钱）跑一次带工具的 Agent：

```python
import asyncio
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel
from pydantic_graph import End

agent = Agent(TestModel(custom_output_text='上海今天多云，26 度。'))


@agent.tool_plain
def get_weather(city: str) -> str:
    return f'{city}: 多云 26C'


async def main():
    async with agent.iter('上海天气怎么样？') as run:
        node = run.next_node                  # 第一个节点
        trace = []
        while not isinstance(node, End):
            trace.append(type(node).__name__)
            node = await run.next(node)       # ← 手动推进（注意不是 async for）
        trace.append(f'End({node.data.output!r})')
        for i, t in enumerate(trace, 1):
            print(f'{i}. {t}')
        print('最终输出:', run.result.output)
```

实跑输出：

```text
1. UserPromptNode
2. ModelRequestNode
3. CallToolsNode
4. ModelRequestNode
5. CallToolsNode
6. End('上海今天多云，26 度。')
最终输出: 上海今天多云，26 度。
```

**完全对应上面那张图**：

- 1 → 2：接待 → 发第一次请求
- 2 → 3：模型说"我要调 get_weather"
- 3 → 4：工具执行完，带着结果再问一次（**这是第二次调模型，第二次花钱**）
- 4 → 5：模型这次给了最终文本
- 5 → End：结束

`agent.iter()` 拿到的 `AgentRun` 跟 `pydantic_graph` 的 `GraphRun` 是同一套东西的封装：

| `AgentRun` 成员 | 说明 |
|---|---|
| `.next_node` | 下一个要跑的 Agent 节点 |
| `await .next(node)` | 手动推进一步 |
| `.result` | 跑完了就是 `AgentRunResult`，没跑完是 `None` |
| `.usage` | token 用量、请求次数 |
| `.all_messages()` | 到目前为止的完整消息历史 |
| `.ctx.state` / `.ctx.deps` | 底层 graph 的 state / deps |
| `async for node in run` | 自动推进（⚠️ 见下一小节的坑） |

> 👉 **PM 视角**：这段代码你可以直接拿给工程师，说："我要在后台看到每个 Agent 请求经过了哪些节点、转了几圈、每一步花了多久。" 这是**Agent 可观测性**的最小实现，也是排查"为什么这个用户的回答特别慢/特别贵"的唯一手段。

### 8.4 ⚠️ 一个必须知道的坑：裸 `async for` 不触发 capability 的 node hooks

`AgentRun` 支持两种推进方式，**它们行为不一样**：

```python
# 方式 A：裸 async for
async for node in agent_run:
    ...

# 方式 B：手动 next()
node = agent_run.next_node
while not isinstance(node, End):
    node = await agent_run.next(node)
```

**方式 A 不会触发 capability 注册的节点级 hooks**（`before_node_run` / `wrap_node_run` / `after_node_run` / `on_node_run_error`）。

源码 `pydantic_ai/run.py` 的 `AgentRun.__anext__` 上写得明明白白：

> "Note: this uses the graph run's internal iteration which **does NOT call node hooks** (`before_node_run`, `wrap_node_run`, `after_node_run`, `on_node_run_error`). Use `next()` for capability-hooked iteration, or use `agent.run()` which drives via `next()` automatically."

实测验证：

```python
import asyncio, warnings
from pydantic_ai import Agent
from pydantic_ai.capabilities import Hooks
from pydantic_ai.models.test import TestModel
from pydantic_graph import End

hooks = Hooks()
seen = []


@hooks.on.node_run
async def trace_node(ctx, *, node, handler):
    seen.append(type(node).__name__)
    return await handler(node)


agent = Agent(TestModel(custom_output_text='好的'), capabilities=[hooks])


async def main():
    # 1) 裸 async for
    seen.clear()
    async with agent.iter('你好') as run:
        async for node in run:
            pass
    print('裸 async for 触发的 hook:', seen)

    # 2) run.next(node)
    seen.clear()
    async with agent.iter('你好') as run:
        node = run.next_node
        while not isinstance(node, End):
            node = await run.next(node)
    print('用 run.next() 触发的 hook:', seen)

    # 3) agent.run()
    seen.clear()
    await agent.run('你好')
    print('agent.run() 触发的 hook:', seen)
```

实跑输出：

```text
裸 async for 触发的 hook: []
用 run.next() 触发的 hook: ['UserPromptNode', 'ModelRequestNode', 'CallToolsNode']
agent.run() 触发的 hook: ['UserPromptNode', 'ModelRequestNode', 'CallToolsNode']
```

**裸 `async for` 一个 hook 都没触发。**

好消息是库会警告你。实测捕获到的完整警告文本：

```text
UserWarning: A capability has `wrap_node_run` hooks, but bare `async for node in agent_run`
does not fire them. Use `agent_run.next(node)` to advance the run, or use `agent.run()`
which drives via `next()` automatically.
```

还有一个更严重的相关行为：如果你用了 `enqueue` 之类依赖 `after_node_run` 的能力，裸迭代跑到 `End` 时会直接抛 `UndrainedPendingMessagesError`，而不是静默丢消息。

**结论表：**

| 驱动方式 | 触发 node hooks | 什么时候用 |
|---|---|---|
| `await agent.run(...)` | ✅ | **默认用这个**，99% 的场景 |
| `agent_run.next(node)` | ✅ | 需要在节点之间插手时 |
| `async for node in agent_run` | ❌ | 只做**只读观察**、且确定没有装 capability 时 |

> ⚠️ **坑总结**：如果你的团队装了 capability（比如做审计日志、限流、成本统计、内容过滤），然后有人在别处用了 `async for node in agent_run` 来"看看流程"，**那些 capability 会静默失效**。审计日志会缺、限流会失灵、成本统计会漏。
>
> 这类 bug 极难排查——功能都正常，只是"有些请求没记日志"。

> 👉 **PM 视角**：这条坑值得直接写进团队的技术规范。翻译成产品语言：**"观察流程"和"驱动流程"是两件事，用错了 API，你的所有横切能力（审计、风控、计费）都会在那条路径上失效。**
>
> 如果你们有合规要求（每次 AI 调用必须留痕），这就是一个真实的合规风险点。

### 8.5 这对 PM 意味着什么

把这一节的认知总结成三条：

**1. Agent 不是黑盒，是一张只有 4 个节点的图。**

你完全可以在需求文档里画出它，跟业务方解释"AI 是怎么工作的"。四个节点、两个循环入口，就这么多。

**2. "Agent 转了几圈" = 成本 = 延迟 = 设计质量。**

图上 `ModelRequestNode ↔ CallToolsNode` 的循环次数，直接等于模型调用次数。一次简单问答是 1 圈，带一次工具调用是 2 圈。如果你发现线上平均 5 圈，那说明模型在反复试错——通常是工具描述写得不清楚，或者 prompt 没给够上下文。**这是一个可以直接优化、且优化效果可量化的产品指标。**

**3. Agent 和显式 Graph 可以嵌套。**

既然 Agent 内部是一张图，那"在你自己的图里放一个 Agent 节点"就非常自然——一个 `@g.step` 里面 `await some_agent.run(...)` 就行了。

```python
@g.step
async def draft_reply(ctx: StepContext[TicketState, Deps, str]) -> str:
    result = await ctx.deps.reply_agent.run(ctx.inputs)
    return result.output
```

**外层是硬编码的 SOP（你控制），内层是 Agent 的自由发挥（模型控制）。** 这是目前最主流、也最稳的 AI 产品架构：

```text
┌────────────────────────────────────────────────────┐
│  你的显式 Graph（SOP，可审计，规则硬编码）           │
│                                                    │
│   收单 → 校验 → ┌──────────────────┐ → 人工复核 → 发出 │
│                │ Agent（自由发挥） │                  │
│                │  写回复文案       │                  │
│                └──────────────────┘                  │
└────────────────────────────────────────────────────┘
```

---

## 九、选型：什么时候该用 Graph

官方那句"别为了用钉枪而用钉枪"不是客套。这一节给一个可操作的判断框架。

### 9.1 三层方案对比

| | 单个 Agent | 多 Agent 协作 | 显式 Graph |
|---|---|---|---|
| 官方比喻 | 锤子 | 大锤 | 钉枪 |
| 下一步谁决定 | 模型 | 模型 | **你** |
| 搭建成本 | 低 | 中 | **高** |
| 流程可视化 | ❌ | ❌ | ✅ `render()` |
| 严格顺序保证 | ❌ | ❌ | ✅ |
| 真并行 | ❌ | 部分 | ✅ `.map()` / `.broadcast()` |
| 每步可干预 | 靠 capability hooks | 难 | ✅ `iter()` + `override_next()` |
| 分支规则可审计 | ❌ 藏在 prompt 里 | ❌ | ✅ 在代码和图上 |
| 出错后降级 | 靠 capability | 难 | ✅ `ErrorMarker` |
| 改需求的成本 | 改 prompt（分钟级） | 改 prompt | 改代码 + 改类型注解（小时级） |
| 适合 | 问答、写作、检索 | 分工明确的协作 | SOP、审批、履约、批处理 |

### 9.2 决策清单：满足几条就该上 Graph

逐条打勾，**≥ 3 条**就值得上 Graph：

- [ ] 流程有**明确的、不能变的步骤顺序**（合规要求、业务规则）
- [ ] 需要**真并行**（多个耗时操作同时跑，不能串行等）
- [ ] 分支规则是**业务硬规则**（金额阈值、地区、用户等级），不能让模型自由裁量
- [ ] 每一步都需要**审计留痕**，事后要能回答"当时为什么走了这条路"
- [ ] 需要**人工介入**（暂停、审批、改道）
- [ ] 失败需要**明确的降级路径**，不是简单重试
- [ ] 需要把流程**画给非技术人员看**（业务方、合规、客户）
- [ ] 流程里有**多个不同的 AI 调用**，各自职责不同，需要编排
- [ ] 需要对**批量数据**做扇出处理（几百上千条并行）

反过来，出现下面任何一条，**先别上 Graph**：

- [ ] 流程只有 1~3 步，而且是纯线性的 → 直接写函数
- [ ] "下一步做什么"本来就该让模型判断 → 用 Agent + tools
- [ ] 需求还在快速迭代，流程一周变三次 → Graph 的类型注解会拖慢你
- [ ] 团队没人熟悉 Python 泛型和类型注解 → 学习成本会吃掉收益

### 9.3 三个真实场景的判断

**场景 A：智能客服问答**

> 用户问问题，AI 查知识库、查订单，然后回答。

**判断：不用 Graph。** 用 Agent + 两个 tool。查哪个、查几次，让模型自己决定才灵活。硬编码"先查知识库再查订单"反而会答得更差。

**场景 B：AI 辅助的退款审批**

> 用户申请退款 → AI 判断是否符合退款政策 → 金额 <100 自动通过 → 100~1000 转客服主管 → >1000 转财务 → 无论哪条路都要留审计记录 → 失败转人工。

**判断：必须用 Graph。** 打勾的条件：明确顺序 ✅、硬规则分支 ✅、审计留痕 ✅、人工介入 ✅、降级路径 ✅ = 5 条。

结构大致是：

```text
[*] --> 收单
收单 --> AI政策判断（这一步内部是个 Agent）
AI政策判断 --> decision
decision --> 自动通过: <100
decision --> 主管审批: 100~1000
decision --> 财务审批: >1000
自动通过 --> 写审计
主管审批 --> 写审计
财务审批 --> 写审计
写审计 --> [*]
```

注意"AI 政策判断"那一步内部可以是个 Agent——**模型只负责给出判断依据，不负责决定走哪条分支**。分支阈值是硬编码的，改起来要走发版流程，这正是合规想要的。

**场景 C：批量生成 500 个商品的营销文案**

> 拉取商品列表 → 每个商品并行调 AI 生成文案 → 敏感词过滤 → 汇总入库 → 生成报告。

**判断：用 Graph。** 打勾条件：真并行 ✅、批量扇出 ✅、多个 AI 调用 ✅ = 3 条。

结构：

```text
拉取商品 --> map(500 个并行) --> 生成文案（Agent）--> 敏感词过滤 --> join(汇总) --> 入库 --> 报告
```

这里 Graph 的核心价值是 `.map()` + `join` ——500 个任务并行，自动汇总。用 Agent 循环做这件事会串行跑 500 次，慢 100 倍。

> ⚠️ 但记得问：**500 个并发会不会被模型 API 限流？** 这个库不管限流，得在 step 里自己加信号量。

### 9.4 渐进式采用路径

不要一上来就把整个系统图化。推荐顺序：

```text
第 1 步：先用 Agent 把功能跑通
   ↓  发现"某几步必须固定顺序"
第 2 步：把那几步抽成一张小 Graph，Agent 作为其中一个 step
   ↓  发现"要并行 / 要审计 / 要人工介入"
第 3 步：扩展这张 Graph，加 map/join、加 iter() 观察
   ↓  发现"要暂停几天等审批"
第 4 步：需要持久化 → 见第十节
```

> 👉 **PM 视角**：最实用的一条经验——**先问"这个流程的失败需要谁负责"**。
> - 答"AI 答错了就答错了，用户重问一次" → Agent
> - 答"这一步错了要赔钱 / 要上合规报告 / 要有人签字" → Graph
>
> 这条判据比任何技术指标都准。

---

## 十、本版本的局限（如实说明）

写教程最忌讳只讲好的。这一节讲清楚这个版本**做不到什么**。

### 10.1 最大的局限：没有持久化，不能中断续跑

`pydantic_graph.persistence` 模块在 2.x 被**整个删掉了**，没有等价物。

官方文档 `graph/builder/index.md` 的原文：

> **"No Native Persistence"**
> Unlike the original Graph API, the graph builder API does not include built-in state persistence. This is due to the **complexity of achieving consistent snapshotting with parallel execution**.
> For workflows that need to preserve progress across failures, restarts, or long-running operations, use one of the supported **durable execution** solutions.

翻译：builder API **没有内置状态持久化**，原因是"在并行执行下做一致性快照太复杂"。需要跨故障/重启/长时间运行保存进度的，请用官方支持的 durable execution 方案。

**这意味着什么（说人话）：**

| 你想做的 | 能不能做 |
|---|---|
| 流程跑到一半，把进度存到数据库 | ❌ 没有内置 API |
| 服务重启后从上次的地方继续跑 | ❌ |
| "提交审批 → 等领导三天后点批准 → 继续跑" | ❌ 不能跨进程/跨时间挂起 |
| 同一个进程内暂停、改道、继续 | ✅ `iter()` + `override_next()` |
| 崩溃后从头重跑 | ✅（只要你的 step 是幂等的） |

> 👉 **PM 视角**：这是一个**产品级的硬约束**，必须在需求阶段就明确。
>
> 如果你的 PRD 里写了"提交后等待审批人处理，审批人可能三天后才来点"，那这个库**开箱即用满足不了**。所有需要"人类思考时间"的流程节点，都要拆成两个独立的 run：
>
> ```text
> ❌ 一张图跑完：提交 → [挂起等审批 3 天] → 打款
> ✅ 拆成两张图：
>    图1：提交 → 校验 → 写入待办库 → 结束
>    （人类三天后在后台点了批准，触发）
>    图2：读取待办 → 打款 → 通知 → 结束
> ```
>
> 这个拆分本身不复杂，但**必须在设计阶段就决定**，不能等到开发完了才发现。

### 10.2 如果一定要做中断续跑，思路是什么

官方推荐用 durable execution 方案（Temporal 之类）。如果要自己糊，思路是：

```text
1. 用 graph.iter() 驱动，不用 graph.run()
2. 每推进一步，把这些东西序列化存库：
     - run.next_task  →  [(node_id, inputs, fork_stack), ...]
     - run.state      →  你的状态对象
3. 恢复时：
     - 反序列化出 state
     - 开一个新的 graph.iter(state=恢复的state, ...)
     - 立刻用 run.override_next([GraphTaskRequest(存下来的 node_id, inputs, fork_stack)])
     - 继续跑
```

**难点在哪：**

| 难点 | 说明 |
|---|---|
| `inputs` 要能序列化 | 如果是任意 Python 对象，得自己写 encoder |
| `fork_stack` 要一起存 | 并行场景下这个不存，join 会等不到 |
| 并行状态难以一致快照 | 5 个任务并行，存的时候 3 个跑完 2 个在跑，这个中间态很难正确恢复 |
| 步骤必须幂等 | 恢复可能重跑某一步，"扣款"这种操作重跑会出大事 |

**这正是官方说"太复杂所以删掉"的原因。** 不建议自己造轮子，除非流程是纯线性的（没有 map/broadcast），那样 `fork_stack` 恒为 `()`，会简单很多。

### 10.3 其他局限与坑（汇总）

| # | 局限 / 坑 | 影响 | 应对 |
|---|---|---|---|
| 1 | **无持久化** | 不能跨进程续跑 | 拆成多个 run，或上 durable execution |
| 2 | **`@g.step` 返回 BaseNode 的 union 会运行时崩** | `build()` 不报错，跑到才炸 | 把分流逻辑挪进 `BaseNode`，或用显式 `g.decision()`（见 3.7） |
| 3 | **decision 没有兜底会崩** | `RuntimeError: No branch matched` | 每个 decision 最后加 `g.match(TypeExpression[object])` |
| 4 | **`.map()` 空列表导致 join 收不到值** | 简单图形抛 `RuntimeError`；多分支图形**静默丢数据**（结果对不上却不报错，最危险） | 永远填 `downstream_join_id=` |
| 5 | **没有并发上限** | list 多长就起多少并行任务，可能打爆下游 | 在 step 内部自己加信号量 |
| 6 | **循环没有最大轮次** | 条件不满足就死循环 | 在流转的数据里带计数器，加熔断分支 |
| 7 | **`matches` 拿不到 state/deps** | 分支条件不能依赖状态 | 把需要的信息塞进流转的值里 |
| 8 | **`.transform()` 是同步的** | 不能在里面 `await` | 需要异步就写成 `@g.step` |
| 9 | **并行时 state 无锁** | "读-改-写"会丢更新 | 只做追加操作，累加用 reducer |
| 10 | **`initial=[]` 会跨 run 串数据** | 第二次跑带着第一次的结果 | 可变类型永远用 `initial_factory=` |
| 11 | **`run_sync` 不能在 async 里调** | `RuntimeError: This event loop is already running` | async 环境用 `await graph.run()` |
| 12 | **裸 `async for node in agent_run` 不触发 node hooks** | 审计/计费/限流静默失效 | 用 `agent.run()` 或 `agent_run.next(node)` |
| 13 | **节点 ID 冲突** | `GraphBuildingError` | 多个同名函数（如不同模块都叫 `process`）要手动 `node_id=` |
| 14 | **不可达节点导致 build 失败** | 想留一个"只能被 override_next 跳转到"的节点时会报错 | `g.build(validate_graph_structure=False)` |
| 15 | **学习曲线陡** | 官方原话："designed for advanced users and makes heavy use of Python generics and type hints. It is not designed to be as beginner-friendly as Pydantic AI." | 评估团队能力，渐进式采用 |

### 10.4 上线前的检查清单

给 PM 用的、可以直接在评审会上逐条问的清单：

| # | 问题 | 为什么问 |
|---|---|---|
| 1 | 每个判断节点，所有情况都覆盖了吗？兜底走哪？ | 防 `No branch matched` 崩溃 |
| 2 | 有循环吗？最多转几轮？超了怎么办？ | 防死循环烧钱 |
| 3 | 有批量并行吗？最多多少个？会被限流吗？ | 防打爆下游 |
| 4 | 批量的输入如果是空的会怎样？ | 防 `downstream_join_id` 漏配 |
| 5 | 每一步失败了怎么办？重试几次？重试完走哪？ | 明确降级路径 |
| 6 | 这条流程跑完，我能从 state 里拿到哪些审计信息？ | 保证可追溯 |
| 7 | 流程中有需要人类思考时间的节点吗？ | 触发"拆成多个 run"的设计 |
| 8 | 每个节点有中文 `label` 吗？关键判断有 `note` 吗？ | 保证图能给业务方看 |
| 9 | 装了 capability 吗？有没有地方用了裸 `async for`？ | 防审计/计费静默失效 |
| 10 | 并行分支里有改 state 的"读-改-写"操作吗？ | 防丢更新 |

---

## 附录 A：API 速查表

### A.1 构建期

| API | 签名要点 | 说明 |
|---|---|---|
| `GraphBuilder(...)` | `name=, state_type=, deps_type=, input_type=, output_type=, auto_instrument=True` | 创建构建器 |
| `g.start_node` | 属性 | 内置起点，ID = `__start__` |
| `g.end_node` | 属性 | 内置终点，ID = `__end__` |
| `@g.step` | `(node_id=, label=)` | 定义函数式节点 |
| `@g.stream` | `(node_id=, label=)` | 定义流式节点（async 生成器） |
| `g.node(X)` | `X` 是 `BaseNode` 子类 | 注册声明式节点 + 自动连边 |
| `g.join(reducer, ...)` | `initial=` 或 `initial_factory=`，`node_id=`, `parent_fork_id=`, `preferred_parent_fork=` | 创建汇总节点 |
| `g.decision(...)` | `note=`, `node_id=` | 创建判定节点 |
| `g.match(T, matches=)` | `T` 可以是类或 `TypeExpression[...]` | 创建分支条件 |
| `g.match_node(X)` | `X` 是 `BaseNode` 子类 | 按节点类型分支 |
| `g.edge_from(*sources)` | 返回 `EdgePathBuilder` | 开始构造边 |
| `g.add(*edges)` | | 把边加进图 |
| `g.add_edge(A, B, label=)` | | 简单边的快捷写法 |
| `g.add_mapping_edge(A, B, ...)` | `pre_map_label=, post_map_label=, fork_id=, downstream_join_id=` | map 边的快捷写法 |
| `g.build(validate_graph_structure=True)` | 返回 `Graph` | 编译 |

### A.2 边上的链式方法

| 方法 | 说明 |
|---|---|
| `.to(A)` / `.to(A, B, C)` | 指定目标，多个 = 广播 |
| `.map(fork_id=, downstream_join_id=)` | 扇出 |
| `.broadcast(lambda b: [...], fork_id=)` | 显式广播 |
| `.transform(func)` | 同步转换，`func(StepContext) -> 新值` |
| `.label('...')` | 边标签（仅可视化） |

### A.3 运行期

| API | 说明 |
|---|---|
| `await graph.run(state=, deps=, inputs=)` | 跑完拿结果 |
| `graph.run_sync(...)` | 同步版本，⚠️ 不能在 async 里调 |
| `async with graph.iter(...) as run:` | 逐步执行 |
| `graph.render(title=, direction=)` | 输出 mermaid 源码 |
| `graph.nodes` | `dict[节点ID, 节点对象]` |
| `run.state` / `run.deps` / `run.inputs` | 本次运行的上下文 |
| `run.next_task` | 下一步要执行什么 |
| `run.output` | 结果，未完成时为 `None` |
| `await run.next(value=None)` | 手动推进一步 |
| `run.override_next(值)` | 改写下一步，值可以是 `[GraphTaskRequest(...)]` 或 `EndMarker(...)` |
| `async for event in run` | 自动推进 |

### A.4 上下文对象

| 对象 | 在哪拿到 | 有什么 |
|---|---|---|
| `StepContext[S, D, I]` | `@g.step` / `@g.stream` / `.transform()` | `.state` `.deps` `.inputs` |
| `GraphRunContext[S, D]` | `BaseNode.run()` | `.state` `.deps` |
| `ReducerContext[S, D]` | 三参数的 reducer 函数 | `.state` `.deps` `.cancel_sibling_tasks()` |

### A.5 内置 reducer

| 名字 | 初始值写法 | 作用 |
|---|---|---|
| `reduce_list_append` | `initial_factory=list[T]` | append 收集 |
| `reduce_list_extend` | `initial_factory=list[T]` | 摊平合并 |
| `reduce_dict_update` | `initial_factory=dict[K,V]` | 字典合并 |
| `reduce_sum` | `initial=0` | 求和 |
| `reduce_null` | `initial=None` | 全丢，只做同步栅栏 |
| `ReduceFirstValue[T]()` | `initial=None` | 取最快的，取消其余任务 |

### A.6 异常类型

| 异常 | 基类 | 什么时候抛 |
|---|---|---|
| `GraphSetupError` | `TypeError` | 图配置错误（缺返回注解、`StepNode` 没配 `Annotated`） |
| `GraphBuildingError` | `ValueError` | 构建期错误（节点 ID 冲突） |
| `GraphValidationError` | `ValueError` | 结构校验失败（有不可达节点） |
| `GraphRuntimeError` | `RuntimeError` | 运行期错误 |

---

## 附录 B：验证环境

本文所有代码在以下环境实跑通过：

| 项 | 版本 |
|---|---|
| `pydantic-graph` | 2.17.0 |
| `pydantic-ai` | 2.17.0 |
| Python | 3.11 |
| 平台 | Linux |

代码来源与验证方式：

- 官方 README（嵌在 `pydantic_graph-2.17.0.dist-info/METADATA` 里）
- 官方文档 `docs/graph.md`、`docs/graph/builder/{index,steps,joins,decisions,parallel}.md`
- 源码 `pydantic_graph/{graph_builder,step,join,decision,basenode,node,paths,util,exceptions}.py`
- Agent 图部分：源码 `pydantic_ai/_agent_graph.py`、`pydantic_ai/run.py`、`pydantic_ai/agent/abstract.py`

所有 `render()` 输出、异常信息、警告文本，均为实际运行的原始输出，未经修改。

---

## 一句话总结

**`pydantic-graph` 把"流程图"变成了"能跑的代码"，而且反过来——代码就是那张永不过期的流程图。**

它的三个核心价值，按重要性排序：

1. **边由返回类型注解推导** → 流程图和实现永远一致，`render()` 随时出图
2. **`.map()` / `g.join()` 的真并行** → 批量任务从串行变并行，是数量级的性能差异
3. **`iter()` + `override_next()`** → 每一步都能观察、能干预、能降级，是所有"人在回路"产品形态的底座

它的三个代价：

1. **没有持久化** → 长时间挂起的流程要拆成多个 run
2. **学习曲线陡** → 官方明说"designed for advanced users"
3. **改流程要改代码** → 不像拖拽式工作流那样能让运营自助改

最后再重复一遍官方那句话：**如果你不确定图是不是个好主意，那它多半是不必要的。**
