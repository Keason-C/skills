## 附录 A：v1 → v2 变更速查表

本附录整理自官方 `docs/changelog.md`（文件标题实为 *Upgrade Guide*）。**v2.0 正式版发布于 2026-06-23。**

这张表的用途：**当你看到一段 Pydantic AI 代码，想判断它是新是旧时，对照这里查。** 左栏出现说明是 v1 写法，右栏是 v2 的正确写法。

### A.1 设计主线：配置向"能力卡"收敛

官方对 v2 的定位原话：

> "V2 leans into a **harness-first design** with capabilities as a core primitive: a single, composable unit that bundles an agent's tools, hooks, instructions, and model settings, reaching every layer of the agent through one concept."

翻译：**大量原本散落在 `Agent(...)` 参数上的配置，被统一收进 `capabilities=[...]`。** 这是理解 v2 全部变更的第一性原则。

| v1 写法 | v2 写法 |
|---|---|
| `Agent(instrument=...)` | `capabilities=[Instrumentation(...)]` |
| `Agent(prepare_tools=...)` | `capabilities=[PrepareTools(...)]` |
| `Agent(history_processors=...)` | `capabilities=[ProcessHistory(...)]` |
| `Agent(event_stream_handler=...)` | `capabilities=[ProcessEventStream(...)]` |
| `Agent(builtin_tools=[...])` | `capabilities=[NativeTool(...)]` |
| `Agent(mcp_servers=[...])` | `Agent(toolsets=[...])` |

> 👉 **PM 视角**：一眼判断代码新旧的诀窍——**看有没有 `capabilities=[...]`**。有，基本是 v2；配置全堆在 `Agent()` 参数里，基本是 v1。

### A.2 会"静默翻转"的行为变更（最危险，不报错但行为变了）

| 变更 | 影响 | 恢复 v1 行为的写法 |
|---|---|---|
| 裸 `openai:` 前缀改走 **Responses API** | 换了 API 通道 | 写 `openai-chat:` |
| `WebSearch`/`WebFetch` 变成 **native-only** | 模型不支持就直接抛错 | `WebSearch(local='duckduckgo')`、`WebFetch(local=True)` |
| `MCP(url=...)` 默认**本地运行** | 执行位置变了 | `MCP(url=..., native=True)` |
| `end_strategy` 默认 `'early'` → **`'graceful'`** | 模型在返回结果的同一轮里调用的工具**现在会真的执行**（含副作用） | 显式设 `end_strategy='early'` |

> ⚠️ **坑**：`end_strategy` 这条最容易出事。v1 里模型同时返回"最终答案"和"工具调用"时，工具会被跳过；**v2 里工具会真的执行**。如果那个工具有副作用（发消息、扣款、写库），行为差异是实质性的。升级时必须逐个 review 有副作用的工具。

### A.3 改名与删除对照表

**模型与供应商**

| v1 | v2 |
|---|---|
| `grok:` 前缀 / `GrokProvider` | `xai:` / `XaiProvider` + `XaiModel` |
| `google-gla:` / `google-vertex:` / `vertexai:` | `google:` / `google-cloud:` |
| `GoogleGLAProvider` / `GoogleVertexProvider` / 整个 `models.gemini` | `GoogleProvider` / `GoogleCloudProvider` + `GoogleModel` |
| `OpenAIModel` / `OpenAIModelSettings` | `OpenAIChatModel` / `OpenAIChatModelSettings` |
| `Agent('gpt-5')`（无前缀） | **抛 `UserError`**，必须 `Agent('openai:gpt-5')` |

**工具相关**

| v1 | v2 |
|---|---|
| `pydantic_ai.builtin_tools` | **`pydantic_ai.native_tools`** |
| `BuiltinToolCallPart` / `BuiltinToolReturnPart` / `AgentBuiltinTool` | `NativeToolCallPart` / `NativeToolReturnPart` / `AgentNativeTool` |
| `MCPServerStdio` / `SSE` / `StreamableHTTP` / `HTTP`、`FastMCPToolset` | `mcp.MCPToolset`、`mcp.load_mcp_toolsets` |
| `Agent.run_mcp_servers()` | `async with agent:` |
| `output.DeferredToolCalls` | `DeferredToolRequests` |
| `toolsets.external.DeferredToolset` | `ExternalToolset` |
| `native_tools.UrlContextTool` | `native_tools.WebFetchTool` |
| `Agent.sequential_tool_calls()` | `agent.parallel_tool_call_execution_mode('sequential')` |

**用量与结果**

| v1 | v2 |
|---|---|
| `request_tokens` / `response_tokens` | `input_tokens` / `output_tokens` |
| `Usage` | `RunUsage` |
| `UsageLimits(request_tokens_limit=, response_tokens_limit=)` | `UsageLimits(input_tokens_limit=, output_tokens_limit=)` |
| `result.usage()` / `result.timestamp()`（方法） | `result.usage` / `result.timestamp`（**属性**） |
| `stream.get()` | `stream.response` |
| `ModelResponse.vendor_details` | `provider_details` |
| `vendor_id` / `provider_request_id` | `provider_response_id` |
| `FunctionToolCallEvent.call_id` | `.tool_call_id` |

**流式**

| v1 | v2 |
|---|---|
| `StreamedRunResult.stream` | `stream_output` |
| `.stream_structured` | `stream_response` |
| `.validate_structured_output` | `validate_response_output` |
| `stream_responses()`（复数） | `stream_response()`（单数） |

**Graph**

| v1 | v2 |
|---|---|
| `pydantic_graph.persistence` 整个包 | **已删除，无等价物** |
| `pydantic_graph.mermaid` / `graph.mermaid_code()` | `Graph.render()` |
| `from pydantic_graph.beta import ...` | `from pydantic_graph import GraphBuilder`（已提到顶层） |

**其他删除**

| 被删除 | 替代方案 |
|---|---|
| `Agent.to_a2a()` + 内置 fasta2a | 装 `fasta2a[pydantic-ai]>=0.6.1`，用 `agent_to_a2a` |
| `Agent.to_ag_ui()` / `AGUIApp` / `pydantic_ai.ag_ui` | `pydantic_ai.ui.ag_ui.AGUIAdapter` |
| `pydantic_ai.ext.aci` | 无替代，用 `Tool.from_schema` 自己包 |
| Outlines 集成（`models.outlines` 等） | 已删除 |
| `models.cached_async_http_client` | `models.create_async_http_client()` |

### A.4 其他需要注意的默认值变更

- **裸装 `pip install pydantic-ai` 的 extras 变精简**：`bedrock` / `groq` / `mistral` **不再默认包含**，要用得显式装。
- **默认 instrumentation 版本 → 5**：run span 的 token 用量改报在 `gen_ai.aggregated_usage.*`。
- **泛型默认参数 `None` → `object`**：裸 `Agent(...)` 现在推断为 `Agent[object, str]`。**仅影响类型检查，运行时不变。**
- **`ModelProfile` 从 dataclass 改为 `TypedDict`**：传参写法不变，只有读写字段 / 调 `.update()` 时受影响。
- **prepare callbacks 返回 `None` 现在抛 `TypeError`**：想表达"这轮不给工具"要返回 `[]`，不能返回 `None`。
- **`FunctionToolset.tool()` 首参非 `RunContext` 现在报错**：无 context 的要用 `tool_plain()`。

### A.5 官方推荐的升级路径

官方给的是三步走：

1. **先升到最新 V1**（≥ v1.100.0），此时会暴露出所有 deprecation warning
2. **逐条消除所有 warning**
3. **再升 V2**，只剩"未被 warning 覆盖"的行为变更需要人工判断

兼容性保证：V1 用 `ModelMessagesTypeAdapter` 序列化的消息历史，在 V2 仍可反序列化。

> 👉 **PM 视角**：这个"先清警告再升级"的路径值得你记住——**它把一次大风险迁移，拆成了一堆小的、有明确提示的修改**。以后遇到大版本升级的排期评估，这是个可以套用的思路：先问工程师"有没有一个中间版本能把问题提前暴露出来"。

---

## 附录 B：常见坑速查

按出现频率排序，都是官方文档明确标注或实测踩到的。

### B.1 Pydantic 层

| 坑 | 说明 | 正确做法 |
|---|---|---|
| **子类序列化丢字段** | Pydantic 按**声明的类型**序列化，不是运行时类型。字段声明为 `Base`，塞进 `Sub1` 实例，`model_dump()` 只会输出 `Base` 的字段 | 用判别联合（discriminated union）或泛型 |
| **`Annotated` 位置写错** | `Annotated[int, Field(deprecated=True)] \| None` ——字段级元数据必须作用于整个联合 | 写成 `Annotated[int \| None, Field(deprecated=True)]` |
| **滥用 `int \| str` 联合** | 若目的只是"把字符串转成数字"，联合是错的——Pydantic 默认本来就会强制转换 | 直接写 `int`，它接受 `'123'` |
| **用抽象集合类型** | `Sequence[str]` 只为了"同时接受 list 和 tuple"，但它效率低 | 直接写 `list[str]`，它本来就接受 tuple |
| **能用内置约束却写校验器** | 自定义验证器比内置约束慢且啰嗦 | 优先 `Field(gt=1)` / `annotated_types.Gt(1)` |

### B.2 Pydantic AI 层

| 坑 | 说明 |
|---|---|
| **`@agent.tool` 必须有 `ctx`，`@agent.tool_plain` 绝不能有** | 搞反了直接运行时报错 |
| **模型字符串必须带供应商前缀** | `'openai:gpt-5.2'` ✅ ／ `'gpt-5.2'` ❌ 抛 `UserError` |
| **`output_type` 里掺了 `str` 等于开后门** | 联合里有 `str`，模型可以选择"不填表，回句大白话就交差"。想强制填表就别掺 `str` |
| **`TestModel` 必须配 `agent.override()`** | 不要直接改 `agent.model`；用 `with agent.override(model=TestModel()):` |
| **`native=True` 的工具绕过 CodeMode** | 原生工具在服务端执行，沙箱里的 `run_code` 根本看不到它 |
| **沙箱管代码不管工具权限** | CodeMode 的沙箱只限制"AI 写的那段脚本"，脚本里调用的工具**仍有其原本的全部权限**。危险工具必须自己加校验 |
| 🔴 **`FileSystem` 的 `protected_patterns` 只挡写、不挡读** | 名字叫 "protected" 很容易理解成"完全屏蔽"，实际**只是只读**。把 `.env` 放进 `protected_patterns`，AI 照样能读出里面的密钥并送进模型上下文。**要真正屏蔽必须用 `denied_patterns`。**（已实测：`protected` 下 AI 读出 `API_KEY=sk-...`；`denied` 下报 `Path '.env' is denied by pattern '.env'.`） |
| **`Shell` 用白名单时必须显式清空黑名单** | 直觉上 `Shell(cwd=..., allowed_commands=['ls'])` 就够了，但它会在 **agent 装载工具时**（不是构造时）抛 `ValueError: Specify allowed_commands or denied_commands, not both.`——因为 `denied_commands` 自带一份默认黑名单，等于"两个都给了"。正确写法：`Shell(cwd=..., allowed_commands=['ls'], denied_commands=[])`（实测：只给 allowed ❌／allowed+空 denied ✅／allowed+非空 denied ❌） |
| **裸 `async for node in agent_run` 不触发 node hooks** | 要触发 capability 的 `before_node_run` 等钩子，得用 `agent_run.next(node)` 或直接 `agent.run()` |

### B.3 Pydantic Graph 层

| 坑 | 说明 |
|---|---|
| **网上教程大多过时** | 2.17 是 builder 架构重写版，`Graph(nodes=[...])`、`mermaid_code()`、`persistence` 都已不存在 |
| **`run_sync` 不能在 async 环境里调** | 它内部走 `loop.run_until_complete`，已有事件循环时会炸。async 里用 `await graph.run()` |
| **`Graph.run()` 全部参数是 keyword-only** | 必须写 `graph.run(inputs=..., state=..., deps=...)`，不能位置传参 |
| **`.broadcast()` 的分支顺序不确定** | 真并发执行，结果顺序不保证。依赖顺序就别用 broadcast |
| **本版本没有持久化** | 要中断续跑，得基于 `iter()` + `override_next()` 自己实现 |

### B.4 版本与文档层

| 坑 | 说明 |
|---|---|
| **skill 的版本号 ≠ 库的版本号** | 官方随包分发的教学 skill 标 `1.1.1`，那是**文档自己的版本号**；库是 2.17.0 |
| **官方 skill 有 v1 措辞残留** | 它提到 `history_processors` "will be removed in v2"，但实测 v2.17 里这个参数**已经没了**。以实际签名为准 |
| **`marketplace` 装的插件不会更新内容** | `ai@pydantic-skills` 插件包的是同一份 skill，版本一致，装了拿不到更新 |
| **harness 是 Alpha** | 0.10.0，PyPI 标 Development Status 3，官方明说 **0.x 小版本都可能破坏性变更** |

> 👉 **PM 视角**：最后这一格值得单独说。**harness 虽然是官方出品、能力很全，但明确处于早期**——而且"让编码 agent 真正稳"的那些能力（自动验证循环、访问控制、审批流、防卡死）在官方 README 里**大多还标着施工中 🚧**。所以它的定位判断应该是：**做原型、内部工具没问题；做核心生产系统，要接受 API 抖动并自己加固。** 这是排期评估时必须说清楚的风险。

---

## 附录 C：一页纸速查

### C.1 三个库一句话

| 库 | 一句话 | 核心对象 |
|---|---|---|
| `pydantic` | 一张带校验规则的表 | `BaseModel` |
| `pydantic-ai` | 把表当合同递给大模型 | `Agent` + `capabilities` |
| `pydantic-graph` | 把流程显式画成图 | `GraphBuilder` → `Graph` |

### C.2 Agent 三件套（造 Agent 时必想）

```python
agent = Agent(
    'anthropic:claude-sonnet-4-6',   # ① 用哪个大脑（供应商:型号，前缀不能省）
    name='my_agent',                 # ② 叫什么（可观测性用）
    instructions='...',              # ③ 守什么规矩（人设/行为准则）
    output_type=MyModel,             # ④ 交什么格式（命门）
    deps_type=MyDeps,                # ⑤ 需要什么私密资料
    capabilities=[...],              # ⑥ 装哪些能力卡
)
```

### C.3 四个"关口"都能校验

| 关口 | 谁的数据 | 用什么 | 失败了谁来改 |
|---|---|---|---|
| 入参 | 人/系统 | `Field` / `model_validator` | 人 |
| 工具参数 | 大模型 | 类型 / `args_validator` | **AI 自己**（`ModelRetry`） |
| 输出 | 大模型 | `output_type` | **AI 自己**（框架自动重试） |
| 进出内容 | 双向 | `guardrails` | 拦截/打码/打回 |

### C.4 选型决策树

```text
需要 AI 输出能直接进系统？
  └─ 是 → 用 output_type 定义 BaseModel

需要 AI 自己动手（查数据、调接口）？
  └─ 是 → 加 Tools
       └─ 工具要用到当前用户/密钥？ → 用 @agent.tool + deps
       └─ 不需要任何私密信息？     → 用 @agent.tool_plain

不同用户要给不同能力？
  └─ 是 → DynamicCapability + ctx.deps 动态配发

流程有多步、要并行、要分支？
  └─ 简单串行  → Agent 循环够用
  └─ 复杂编排  → 上 Pydantic Graph

要让 AI 操作文件/命令行？
  └─ 只读写文件      → harness FileSystem
  └─ 要跑命令        → harness Shell（配白名单）
  └─ 危险/不可信操作 → harness ModalSandbox（一次性云环境）
```

---

## 结语

如果这本书只让你记住三句话，我希望是这三句：

**第一，Pydantic 系的核心哲学是"合同先行"。** 你先声明"什么样算合格"，框架负责在数据进门那一刻就把不合格的挡住——而不是等出了问题再去清洗。这跟你写 PRD 定验收标准，是同一件事。

**第二，v2 的核心是"能力卡"。** 给 Agent 加任何高级能力——上网、思考、记忆、埋点、沙箱——都收敛成同一个动作：造一张卡，插进 `capabilities=[...]`。你不用记几十种 API，只要记住"找到对应的卡，插上去"。

**第三，能力边界要靠框架物理隔离，不能靠提示词自律。** 免费用户看不到退款工具，是因为它压根没被配发；敏感数值走 `deps` 是因为模型碰不到那条通道。**"不给看"永远比"叮嘱不要用"可靠。** 这条判断，会在你做每一个 AI 产品的权限设计时用到。

---

*本书全部代码基于 pydantic 2.13.4 / pydantic-ai 2.17.0 / pydantic-graph 2.17.0 / pydantic-ai-harness 0.10.0 实测验证。*
