# Pydantic 全栈教程 · PM 视角

一本写给**产品经理**的中文技术教程，覆盖 `pydantic` → `pydantic-ai` → `pydantic-graph` 三层。

**成品**：[`Pydantic全栈教程-PM视角.pdf`](./Pydantic全栈教程-PM视角.pdf)（约 300 页）

## 这本书是什么

读者不需要会写生产代码，但希望**看懂代码和概念**、能做技术判断。所以每个知识点都按同一个三段式展开：

1. **它解决什么问题**（一句话，产品语言）
2. **代码示例**（真实可运行，附实际输出）
3. **👉 PM 视角**（把特性挂到已有的产品直觉上：表单校验、审批流、权限设计、SaaS 分级……）

结构上**先给架构地图，再逐块下钻**；能力清单一律"先列总表，再逐个精讲"。

## 目录结构

| 部分 | 文件 | 内容 |
|---|---|---|
| 导读 | `src/00-导读.md` | 三层关系、Unix 哲学之辨、版本基准、阅读路线 |
| 第一部分 | `src/01-pydantic.md` | 数据校验地基：BaseModel / Field / 校验器 / 序列化 / **JSON Schema** / 判别联合 / ConfigDict / TypeAdapter |
| 第二部分 A | `src/02a-agent-tools.md` | Agent 架构总览 / Agent 核心 / 输出模式 / run 方法家族 / Tools 全套 |
| 第二部分 B | `src/02b-capabilities-harness.md` | Deps 依赖注入 / **Capabilities 能力卡体系** / Hooks / Harness 扩展包 |
| 第三部分 | `src/03-graph.md` | 图引擎：Step / BaseNode / 控制流 / 并行 / **Agent 循环就是一张图** |
| 第四部分 | `src/04-shizhan.md` | 综合实战：多租户 SaaS 客服 AI，三层贯通 |
| 附录 | `src/05-fulu.md` | v1→v2 变更速查 / 常见坑速查 / 决策树 |

## 版本基准

全书以**官方最新版本**为准，**每段代码都在下列版本实测运行验证**：

| 库 | 版本 |
|---|---|
| `pydantic` | 2.13.4 |
| `pydantic-ai` | **2.17.0（v2）** |
| `pydantic-graph` | **2.17.0**（builder 架构重写版） |
| `pydantic-ai-harness` | 0.10.0（Alpha） |

> 注意：Pydantic AI v2 相比 v1 有大量破坏性变更，网上多数教程已过时。本书附录 A 提供完整的 v1→v2 变更速查表。

## 重新构建 PDF

```bash
python build_pdf.py     # 读 src/*.md → 生成 book.html → 渲染成 PDF
python check_code.py    # 自动校验：代码块语法、章节编号、结构指标
```

依赖：`markdown-it-py`、`pygments`、`playwright`（复用系统 Chromium）、`pypdf`；中文字体需 `fonts-noto-cjk`。
