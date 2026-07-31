# 03 — 知识目录长出摘要(引入驱动 seam)

**What to build:** 摄取时为每份文档生成一句话摘要,写进知识目录 —— 这是两段式选材(ADR-0001)能工作的前提。摘要由 `LlmDriver` 生成:`AnthropicDriver` 是真实实现(**写,但测试永不跑**),`ScriptedDriver` 按预设脚本返回、测试全用它(ADR-0004)。驱动接口只有一个方法:prompt 进,文本出。

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] 摄取后每条知识目录条目都有摘要
- [ ] 驱动抛异常时摘要为空,摄取**不中断**,该文档仍然进目录
- [ ] `ScriptedDriver` 记录下它收到的全部 prompt,供后续测试做子串断言
- [ ] `AnthropicDriver` 存在、可被导入、不在任何测试中被调用
