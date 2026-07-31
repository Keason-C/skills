# Contract — 渠道无关内核 API

宪法原则 VI:内核不感知调用者。CLI 与将来的企业微信适配器都通过本 API 使用系统。

```python
from procurement_bot.core import AskService
from procurement_bot.llm.mock import KeywordMockDriver

svc = AskService.load(
    corpus_root="/mnt/share/采购知识库",
    roster_path="/mnt/share/采购知识库/roster.csv",
    state_dir="./.pbot",
    driver=KeywordMockDriver(),
    secret_dir_name="保密",
)

answer = svc.ask(question="电解铜归谁管?", employee_id="P1001")
```

## `AskService`

| 方法 | 签名 | 说明 |
|------|------|------|
| `load` | `(corpus_root, roster_path, state_dir, driver, *, secret_dir_name="保密", top_k=12) -> AskService` | 从已有索引加载;索引缺失抛 `IndexMissingError` |
| `build_index` | `(corpus_root, state_dir, *, secret_dir_name="保密") -> IngestReport` | 扫描并写索引(`pbot ingest` 的实现) |
| `ask` | `(question: str, employee_id: str) -> Answer` | **唯一问答入口** |
| `gaps` | `(limit: int = 50) -> GapReport` | |
| `rejected` | `() -> tuple[RejectedFile, ...]` | |
| `audit_tail` | `(limit: int = 50) -> tuple[AuditRecord, ...]` | |

## 契约

- **CA-1**:`ask` **MUST NOT** 读取任何环境变量、`sys.argv`、当前工作目录或终端状态来
  确定身份。身份只能来自 `employee_id` 参数(宪法原则 VI)。
- **CA-2**:`ask` **MUST NOT** 打印任何内容到 stdout/stderr。渲染是渠道的职责。
- **CA-3**:`ask` 的返回值 `Answer` 完全 JSON 可序列化,不含文件句柄、不含 Passage 全文
  以外的内部对象。
- **CA-4**:`ask` 是**幂等**的:同一 `(question, employee_id, driver, index)` 组合
  返回相同 `Answer`(`escalation_id` 与时间戳除外)。这使端到端测试可断言精确输出。
- **CA-5**:`ask` 内部的调用顺序是契约的一部分,**MUST** 为:
  `roster.lookup → authz.partition → retrieval.score → conflict.resolve →
   prompting.build → driver.generate → verifier.check → escalation/audit`。
  `authz.partition` **MUST** 早于 `prompting.build`(宪法原则 II)。
- **CA-6**:未知 `employee_id` 抛 `UnknownRequesterError`,**不得**降级为匿名最小权限
  (静默降级会制造玄学权限故障,D-10)。
- **CA-7**:`ask` 不抛出因模型行为导致的异常。驱动异常 → 捕获 → 返回
  `status=unknown` 并生成转人工记录(可用性优先于报错)。
