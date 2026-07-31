# Contract — LLM 驱动接口

宪法原则 IV:所有模型调用收敛到这一个接口后面。

```python
@dataclass(frozen=True)
class PassageView:
    passage_id: str        # 模型在引用时必须原样回填的标识
    source_label: str      # "品类管理手册-电解铜.md — § 1 品类归属"
    text: str

@dataclass(frozen=True)
class LLMRequest:
    question: str
    passages: tuple[PassageView, ...]

@dataclass(frozen=True)
class LLMResponse:
    answer_text: str
    cited_passage_ids: tuple[str, ...]
    sufficient: bool

class LLMDriver(Protocol):
    name: str
    def generate(self, request: LLMRequest) -> LLMResponse: ...
```

## 驱动的义务

- **LD-1**:`generate` **MUST** 是纯函数式的:除模型调用外无副作用,不写文件、不改全局状态。
- **LD-2**:`sufficient=False` 表示"给的材料不足以回答"。此时 `answer_text` 与
  `cited_passage_ids` **会被内核丢弃**,驱动不必费心填写。
- **LD-3**:驱动 **MUST NOT** 自行拼接"出处"文字到 `answer_text` 里。出处由内核用
  `cited_passage_ids` 反查 Passage 后生成(D-05)——这样模型无法伪造一个好看的假引用。
- **LD-4**:驱动 **MUST NOT** 看到任何超出 `request.passages` 的内容。权限过滤已在上游完成。

## 内核对驱动的不信任(verifier 的职责)

内核**假定驱动可能说谎**,并在 `verifier.check` 中强制:

| 检查 | 失败后果 |
|------|----------|
| `sufficient is False` | → `status=unknown` |
| `cited_passage_ids` 为空 | → `status=unknown` |
| 存在不在 `request.passages` 中的引用 ID | → `status=unknown`,`fabrication_blocked=True` |
| `answer_text` 去空白后为空 | → `status=unknown` |

## 三个实现

| 实现 | 用途 | 是否联网 | 是否在测试中执行 |
|------|------|----------|------------------|
| `KeywordMockDriver` | 离线演示 + 端到端测试 | 否 | **是** |
| `ScriptedDriver` | 单元测试,可注入"说谎"响应 | 否 | **是** |
| `AnthropicDriver` | 生产 | 是 | **否(只写不跑)** |

### `KeywordMockDriver` 的确定性规则(必须可预测)

1. 对每个 `PassageView`,计算其文本与问题的词元重合分(复用 `retrieval` 的分词器)。
2. 分数最高者若 > 0:从该片段中挑出重合词元最多的**一个句子**作为 `answer_text`,
   `cited_passage_ids = (最高分片段,)`,`sufficient=True`。
3. 全部为 0:`sufficient=False`。
4. 平分时按 `passage_id` 字典序取最小者 —— **保证无随机性**。

### `AnthropicDriver`(只写不跑)

- 在 `generate` 内部才 `import anthropic`,使核心模块导入不依赖该 SDK 是否安装。
- 提示词要求模型输出严格 JSON:`{"sufficient": bool, "answer": str, "citations": [id...]}`。
- 系统提示中包含:"只能使用提供的材料;材料不足时把 sufficient 设为 false;
  citations 必须是给定的 passage_id 原文"。
- **注意**:这些提示词是**第二道防线**。第一道防线是 verifier 的确定性校验,
  它不依赖模型是否听话。
- **MUST NOT** 被任何测试导入执行;仅由 `pbot ask --driver anthropic` 在运行时加载。
