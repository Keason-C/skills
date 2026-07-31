# /code-review — 固定点 `ee6bd58`(setup 提交)→ HEAD

命令:`git diff ee6bd58...HEAD`;58 个文件,+4450 行。
规格来源:`.scratch/commodity-qa-bot/spec.md` 与 `issues/01..10`。

**适配说明**:技能要求两个轴各起一个并行 sub-agent、互不污染上下文。本次由我
**串行**完成两轮,每轮只带该轴的输入,两份结论分开记录、**不合并也不重排**。
串行的代价是真实的:两轮之间我没法真正"忘掉"上一轮看到的东西,Standards 轮
的印象一定程度上污染了 Spec 轮的注意力。这是本次适配最大的一处失真。

---

## Standards

仓库没有 `CODING_STANDARDS.md`;成文标准只有 `CLAUDE.md` 里的工程红线
(Python 3.11 / uv、测试全离线、真实 LLM 调用置于驱动接口后、绝不 push)。
以下另加 Fowler 气味基线。

### 硬违反(有成文标准可引)

无。三条工程红线都守住了:测试 70 个全部离线通过;`AnthropicDriver.complete`
在测试中零调用;没有任何 push。

### 判断题(气味基线)

1. **Duplicated Code —— 确认,值得修**。`tests/conftest.py` 与
   `scripts/make_demo_corpus.py` 各有一份 `write_docx` / `write_xlsx` /
   `write_pdf` / `write_scanned_pdf`,函数体近乎逐字相同(约 45 行 × 2)。
   两边确实服务不同语料(临时夹具 vs 演示语料),但重复的是**文件写入机制**,
   不是语料。→ 抽到 `scripts/docgen.py`,两边都调它。

2. **Data Clumps + Feature Envy —— 确认,值得修**。
   `build_restricted_notice(hits, handover.to_name, handover.to_contact)`
   把一个 `Handover` 拆成两个字段传进去,函数体又只用这两个字段。
   → 直接传 `Handover`。

3. **Primitive Obsession —— 确认,轻度**。`Answer.abstain_reason` 和
   `SkippedFile.reason` 都是裸字符串,取值集合其实是封闭的
   (`driver_error` / `invalid_json` / `quote_not_found` / …)。测试里靠字面量
   断言,写错一个字母不会被发现。→ 收成常量或 `StrEnum`。

4. **缺类型标注 —— 与仓库自身风格不一致**。`answering.answer_question` 的
   `driver` / `roster`、`ingest.ingest_library` 的 `summariser`、
   `summarise.make_summariser` 的 `driver`、`answering._handover_for` 的
   `roster` 都没有标注,而同文件其它参数全都标了。`LlmDriver` 协议已经存在,
   `Roster` 也是具体类型,没有理由留白。→ 补上。
   (`roster` 留白还有个隐性代价:`Roster` 与 `answering` 之间的依赖只存在于
   运行期,读代码的人看不出来。)

5. **Speculative Generality —— 确认,轻度**。`relevant_withheld` 暴露了
   `keywords` 与 `threshold` 两个参数,当前只有一个调用方且从不覆盖默认值。
   基线建议删掉;但保密话题词表是**业务上一定会被调**的东西(采购部会想加
   "返利""佣金"),我判断保留 `keywords`、删掉 `threshold`。

6. **Mysterious Name —— 轻度**。`rehearsal._pick` / `_compose` 从名字看不出
   在处理哪一段 prompt。→ `_select_documents` / `_compose_answer`。

7. **不是气味,但值得记**:`_squash` + 子串匹配是出处核验的全部实现。它对
   "模型把两段不相邻的原文拼在一起当引文"是**无效**的(拼接后的串确实不出现在
   原文里,所以会被拦下 —— 结论是安全的,但靠的是巧合而非设计)。当前行为正确,
   不改;记在这里,免得以后有人"优化"成分段匹配从而打开这个洞。

---

## Spec

逐条比对 `spec.md` 的 26 条 user story、实现决策、测试决策与 Out of Scope。

### (a) 规格要求但缺失或只做了一半

1. **Story 18「两份文档说法不一致时并排列出并标注日期,不替用户裁决」——
   只做了一半。** 排序(生效日期倒序)、prompt 里带日期、prompt 里的指令
   三样都有,并且都有测试;但**"并排列出"这个行为本身没有任何测试**,因为它
   完全取决于模型是否听话,而测试离线。这不是可以补测试解决的,是这条规格
   在当前架构下**本质上不可验证**。规格里没有承认这一点,建议在 spec 里
   把它标为"prompt 级尽力而为",避免以后被当成已验收能力。

2. **Story 23「等 5~15 秒可接受」缺乏任何度量。** 没有计时、没有 token 预算
   保护。两段式选材是为此设计的(ADR-0001),但实际耗时从没测过 —— 只能等
   真语料上手。属于已知的开口,不是遗漏实现。

3. **Story 4「Excel 或 CSV 都能填」已实现,但 XLSX 只读第一个工作表**
   (`wb.active`)。业主把名单放到第二个 sheet 就会静默读不到。规格没说,
   但"静默"这个行为和本项目"绝不静默丢弃"的基调冲突。→ 应当报错而不是沉默。

### (b) 规格没要求的东西(scope creep)

4. **`rehearsal.py`(排练驱动)整个模块是规格之外的。** 约 110 行,spec 的
   模块表里没有它,10 张票里也没有。它是为了"演示路径必须可跑"而加的 ——
   而"测试与演示不得联网"是环境红线,不是业主需求。**我认为这个增量是必要的**
   (否则完成标准里的"演示路径"无法达成),但它确实是规格外的东西,
   而且是本次最大的一处 scope creep,必须显式记账而不是混进"实现细节"。
   → 已在 README 显著位置说明它不是模型、不冒充模型。

5. **`pqa doctor` 命令规格外。** spec 的 CLI 清单是
   `ingest / ask / gaps / audit / whoami`,没有 `doctor`(它只出现在
   grilling notes 的 T9 里,没有升进 spec)。增量很小且直接服务 Story 3,
   但确实是规格漂移 —— 要么补进 spec,要么删掉。建议补进 spec。

6. **`config.py` 的知识库落盘(`library.json`)规格外。** spec 的模块表里没有
   持久化这一层。它是实现"不要每问一次就重新摄取 + 重新生成摘要"的必需品,
   合理,但同样属于规格没预见到的结构。

### (c) 看起来实现了但实现得可疑

7. **`_target_category` 的品类推断很脆。** 它按"品类名是不是问题的子串"来匹配,
   于是"**流程**上有什么要求?"会被判成「流程」品类(因为存在一个叫「流程」的
   目录)。后果仅限于转人工转错人,不影响权限,但会让缺口清单的分组变脏。
   规格只说"按品类转给对应的品类经理",没规定怎么认品类 —— 这是我填的空,
   填得不够好。已知缺陷,建议真语料上手后用名单里的品类白名单替代目录名。

8. **保密相关性判断的阈值(2 个二元组)是拍脑袋定的。** 有 4 个测试钉住了
   当前行为的边界,但没有任何真实问题样本支撑这个数字。误报会让采购员看到
   莫名其妙的"涉及保密",漏报会让他以为库里没有。这是全系统最需要真数据
   校准的一个常数。

---

## 汇总

- **Standards**:0 条硬违反,7 条判断题。其中最值得修的是 **#1 重复的文档
  生成函数**(约 45 行逐字重复)。
- **Spec**:8 条发现 —— 3 条缺失/半成品、3 条 scope creep、2 条实现可疑。
  其中最严重的是 **#1 Story 18 在当前架构下本质上不可验证**,而规格把它写得
  像一条已验收能力。

两个轴的结论不做合并排序 —— 分开看才有意义:这次的代码在标准上相当干净,
在规格忠实度上却有真实的漂移,合并成一个"总分"会把后者掩盖掉。
