# DECISIONS.md — 产品决策口径(评测私有,三组统一答案)

任何 agent 问到以下问题时,按此口径回答,保证三组公平:

1. **优先级档位**:P0/P1/P2/P3 四档。P0=服务不可用或安全事件;P1=阻塞用户核心操作(付款失败等);P2=一般问题;P3=咨询/建议。
2. **多语言**:支持中文+英文工单。MockDriver 的关键词规则需覆盖中英双语;其他语言归 OTHER 且 confidence 不得高于 0.5。
3. **置信度阈值**:0.6。低于 0.6 → 带工具上下文重试一次;重试后仍 < 0.6 → 升级人工。
4. **金额阈值**:1000,货币统一为 USD(fixture 中金额均为 USD,无需多币种)。金额 = 1000 不升级,> 1000 升级。
5. **TS CLI 形态**:单命令,如 `triage-view <result.json>`;默认美化输出,`--json` 输出规范化 JSON。无需子命令体系。
6. **注入检测处置**:检测到注入 → sentiment 照常分析,但工单强制 `escalated_to_human=True`,rationale 注明检测到注入,注入文本不得进入任何工具调用参数。
7. **重试语义**:"连续两次低置信度"指同一工单首次分类 + 一次重试均低于阈值,即升级;不做第三次。
8. **优先级与升级关系**:P0 一律升级人工(无论置信度)。
9. **其他细节**(命名、目录结构、fixture 内容、错误码等):技术决策,agent 自定并记录即可。

## 补充口径(superpowers 组首轮提问后新增,三组统一)

10. **priority 推导**:priority 由确定性规则从 category+amount+sentiment+守卫结果推导,LLM 建议仅作输入之一,不能直接决定 priority。
11. **sentiment 枚举**:ANGRY / FRUSTRATED / NEUTRAL / SATISFIED 四档。
12. **REFUND 政策冲突处置**:政策(确定性数据源)覆盖 LLM 建议,继续自动处理,rationale 记录"已被政策覆盖";不因此升级人工。
13. **AUTO_RESOLVED 准入**:同时满足 ①未触发任何守卫升级 ②confidence ≥ 0.6 ③priority ∈ {P1,P2,P3}(P0 一律人工) ④category ≠ OTHER(OTHER 转人工)。
14. **空/纯空白 body**:在 pydantic 边界直接拒绝(ValidationError)。**超长**:body 上限 20000 字符、subject 上限 200,超过边界拒绝(不截断)。
15. **未知 order_id**:继续分诊,"order not found" 写入 rationale;仅当 category ∈ {REFUND, BILLING} 时因证据缺失升级人工。
16. **TS CLI 细化**:位置参数 `<file.json>` 必须支持;输入为单个结果对象(数组/stdin 不要求,可选加);校验失败打印 zod 结构化错误路径并以非零退出码结束。

## 补充口径 2(mattpocock 组提问后新增,三组统一)

17. **recommended_action 为闭集枚举**(7 值):AUTO_REFUND / REQUEST_MORE_INFO / ROUTE_TO_BILLING / ROUTE_TO_TECH_SUPPORT / ROUTE_TO_ACCOUNT_TEAM / SEND_SELF_SERVE_GUIDE / ESCALATE_TO_HUMAN。不做自由文本。
18. **动钱动作不自动执行**:AUTO_REFUND 作为建议动作可以给出,但执行一律转人工;v1 不做小额自动退款。
19. **优先级矩阵**(规则推导):注入 → P0(安全事件);金额守卫触发 → 至少 P1;任何转人工 → 至少 P1;ANGRY 且 REFUND/BILLING → P1;TECHNICAL/ACCOUNT 常规 → P2;其余 → P3。

## 补充口径 3(spec-kit 组 clarify 后新增,三组统一)

20. **退款窗口已过的工单**:一律转人工,由人来说"不"(与口径 18 一致:机器不做拒绝/动钱类终局动作);窗口内的政策一致动作照常自动化。

回答风格:以产品负责人身份,只给决策,不给实现建议,不夹带对工作流的评价(避免污染 REFLECTION)。
