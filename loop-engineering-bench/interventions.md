# 插手记录（全部计时间戳；答问计入 Loop 适配维度）

## Round 1
- 15:47 UTC | C | 答问 #C1（SSO 定位+身份源）。按档案裁决作答（v1 不做 SSO 留接口；身份源未定→新裁决入档案）。C 累计提问数: 1
- 15:52 UTC | B | 答问 #B1（一批 11 题）。全部按档案作答；B 试图把 SSO/MFA/细粒度权限拉进 v1，被档案裁决顶回（SSO 不做、MFA 不做、三角色够用）。B 累计提问数: 11
- 15:58 UTC | A | 答问 #A1（术语确认 + 12 题）。全部按档案作答；新裁决 6 条入档案（SSO 无deadline、权限边界、调用方类别、会话参数授权、账号管理、SLA99.9）。A 累计提问数: 12（+3 术语确认）
- 16:00 UTC | C | 答问 #C2（注册方式+管理入口）。档案标准答案。C 累计提问数: 2
- 16:05 UTC | B | 答问 #B2（fail-closed 确认 + A–J 共 11 项）。10 条新裁决入档案。B 累计提问数: 22，已宣布进入 spec 撰写
- 16:07 UTC | C | 答问 #C3（权限模型+用户组）。档案标准答案（全局三角色）。C 累计提问数: 3
- 16:12–16:35 UTC | C | 答问 #C4 MFA（不做）、#C5 会话策略（授权其定数值）、#C6 规模接入、#C7 登录页形态（统一托管页）。均档案标准答案。C 累计提问数: 7。C 已自行钉死不透明令牌+实时校验方案（贴合"停用即时生效"裁决）
- 16:45–16:58 UTC | C | 答问 #C8 基础设施事实、#C9 build vs buy（裁决：自建，新裁决入档案）。C 累计提问数: 9
- 16:55 UTC | A | 答问 #A2（Q13–Q22 共 10 题）。4 条新裁决入档案（默认零角色、同父域、仅管理员改邮箱、生产有 Redis）。A 累计提问数: 22
- 17:10 UTC | A | 答问 #A3（Q23–Q30 共 8 题）+ 给出"共识达成"确认。Q29 管理界面按与 B/C 一致口径（无硬要求做了算加分）。A 累计提问数: 30，grilling 结束进入 spec 撰写
- 17:05–17:40 UTC | C | 设计文档分 3 段确认（每段一次介入）；第 2 段默认角色与档案冲突（member→纠正为零角色）。C 累计介入数: 12（9 问 + 3 段确认）
- 备注 | B | 16:05 后进入 spec/tickets 撰写，无新提问。B 累计提问数: 22

## Round 2 — S2 PydanticAI 业务分析 agent（2026-08-05 ~20:59 UTC 起）
- 档案: /workspace/bench/dossiers/S2.md（200人口径；核心=脏Excel/PDF摄取+真分析+图+决策建议；红线=不许幻觉编数、数字可溯源）
- 三仓隔离: /workspace/bench/round2/{A,B,C} git init
- 规划 Opus agent ID: A(matt grilling)=abc44f07b17935881 | B(裸brainstorm)=a67ab9bce5cce5b50 | C(superpowers)=a91ae5d953273d1f1
- 种子输入三家一字不差（业务负责人口吻）；agent 无档案，靠 grill/brainstorm 问出需求
- 答问只出自 S2 档案；同问同答一字不差；每次答问计入 Loop适配 提问数

### R2 规划提问轮次
- [21:05 UTC] B 第1轮：7 问（成品/文件类型/好结论/不确定处理/上云/用户设备/验收）。抓到不确定处理+敏感数据+人审；未碰提示注入/成本/复现/确定性计算架构。已从档案答。
- [21:06 UTC] C 第1轮：5 问（数据出门a/b/c、v1报表、好分析例、成品+人审、规模成本）。**开场即主动点破 LLM 编数字风险+"算术交给代码而非模型口算+数字溯源到单元格"核心架构**。已答。
- [21:06 UTC] A 第1轮：7 问（每问带推荐+理由：好分析及格线/数据出门/文件真实情况含OCR/可溯源+人审/v1边界/用户形式/预算供应商）。**主动挖出编数字、OCR扫描件、成本护栏、开放式会飘、可溯源人审 5 坑**，grilling 深度最高。已答。
- 新增裁决入档：成本上限(月几百~一两千RMB)、扫描件占比~30%、无指定供应商、锁定固定分析类型、AI起草人审核、数据(b)档可上云。

### R2 规划第2轮
- [21:15 UTC] A 第2轮：6 问（Q8历史对比源/Q9谁定阈值/Q10认表配置/Q11验收关/Q12建议敢说度/Q13权限留存）。**Q9"阈值明写死非LLM自由发挥"+Q10"认表模板映射"两个把demo变生产工具的关键判断，思维补全极强。** 已答，转 spec。
- [21:16 UTC] C 第2轮：3 问（网页分工/认表模板/往月数据）。**独立走到与A相同的"认表模板"+"分析师用网页经理收成品"判断。** C提议往月规范化数据存内网自动算趋势——为与A同口径，裁定v1不建历史库(当次上传对比文件)，C的内网存储想法归v2。已答，转完整设计。
- B: 已让其出 spec+工单（第1轮7问后未再追问）。
- 累计提问：A 13(2轮) / C 8(2轮) / B 7(1轮)。

### R2 规划收敛 + B 转实现
- [21:14 UTC] B 规划完成 commit f8049bf：SPEC.md(11节)+TICKETS.md(30票/8epic,P0安全脊链)+README。**B在写设计阶段自达核心架构：确定性计算与LLM分离+防编造护栏+fail-loud+只发聚合(隐私/成本)+本地OCR+仅描述诊断不预测。** 提问阶段没问到但设计补回，扣分从轻。
- [21:16 UTC] C 完整设计出炉(未落库先请示)：四道防编数字闸+上线前数字核验器(追不回源就拦)、架构层让prompt injection失效、可复现(数字钉死+运行清单可审计)、真分析工具(价量拆分/供应商z值/毛利桥)、OCR置信度、成本做实(≈¥4/次 月¥150-800 +成本看板+缓存)。裁判批准方向，令其落库转writing-plans。
- [21:16 UTC] B 实现启动：Sonnet a2afcd346c2c0104f，按票P0安全脊优先，无API key故LLM层可mock、确定性核心全离线测试。硬上限~4h至约01:15 UTC。

### R2 A 规划完成 + 转实现
- [21:20 UTC] A 规划完成 commits 2ef1ce9(spec+13ADR)+8a9cc25(13票)。skill痕迹合格：grilling(13问2轮)→to-spec(spec.md 术语表+36用户故事+按接缝测试决策)→to-tickets(13纵切票依赖排序验收挂ADR)。13 ADR覆盖全陷阱(0002确定性计算/0003溯源红旗/0004认表/0005显式阈值/0009提示注入/0013回测门)。反幻觉架构 Extract→Compute→Rule→Narrate。
- [21:20 UTC] A 实现启动：Sonnet ac804166fa75793bc，带 implement skill，安全脊票01-07优先，硬上限~4h至约01:20 UTC。
- 状态：A实现中 | B实现中(a2afcd) | C writing-plans中

### R2 三家全部转实现（规划阶段收官）
- [21:25 UTC] C 规划完成 commits 874e86a(design)+367aef4(16任务plan)。skill痕迹合格：brainstorming(3轮对话)→writing-plans(16 TDD任务,含真实计算代码,verify.py=Task5 P0纯Python无LLM+确定性测试)。数据流向图/成本做实(claude-api skill查价)。
- [21:25 UTC] C 实现启动：Sonnet aed49289e3933ffbf，带 executing-plans skill，验证管线+P0核验器优先，硬上限~4h至约01:25 UTC。
- 三家实现并行：A=ac804166fa75793bc(implement,~01:20) | B=a2afcd346c2c0104f(无skill,~01:15) | C=aed49289e3933ffbf(executing-plans,~01:25)
- 规划阶段提问总计：A 13 | C 8 | B 7。三家均达同一反幻觉架构；A/C提问阶段主动挖出并带ADR/设计讲透，B写设计补回无独立决策记录。

### R2 实现完成陆续到达
- [21:25 UTC] C 实现完成(~18min)：feature/ai-business-analyst 分支,18 commit,40测试过/1跳过(需API key集成测试)。16任务全做。verify.py确认纯Python无LLM(grep验证)。诚实列缺口:webapp扫描件OCR路由NotImplementedError(仅模块层测)、/analyze单文件、PydanticAI token成本未接CostMeter。修了计划伪代码自身会挂的bug。待A/B完成后统一验收。

### R2 裁判亲手对抗验收（B/C 完成后，A 仍在跑）
- 测试套件(裁判手跑)：C 40过/1跳过(deps完整,干净)；B 123过但**漏声明pytesseract+pdf2image**——按其声明deps干净安装后收集失败12错误，补装后才123过(可复现/运维缺陷,记A10扣分)。
- C verify.py对抗(裁判构造)：①精确引真值clean✓ ②编造value_id拦✓ ③数字改一位(1420vs1000)拦✓ ④引held-for-human低置信OCR值拦✓ ⑤**散文洞坐实**:claim塞"37%"不入figures→is_clean=True放行。核验器只扫结构化figures,散文靠系统提示软兜(analysis.py _SYSTEM_PROMPT有"NEVER write bare number in claim/recommendation prose")。
- B guardrail.py对抗(裁判构造)：A真实数ok✓ B编造"37%"散文拦✓(逮住C漏的) D"2000"拦✓ E注入+"9999"拦✓；**容差洞**:贴近真值1%内的1005(真值1000)放行(abs0.05/rel0.01容差)。正则扫全部散文,较脆。
- 结论:两家反幻觉都真·强制、离线可测,各有一个可复现的洞且互补(C精确无容差洞但漏散文;B扫散文但有容差洞)。均非玩具。理想=C结构化精确+B散文扫描合体。

### R2 A 完成 + 裁判对抗验收
- A 完成全13票，208测试(裁判手跑,exit0)。deps完整(含pytesseract/pdf2image/weasyprint)且有专门commit e0e3104修依赖声明——B没做A做了(可维护/运维加分)。真PydanticAI FunctionModel+真tesseract OCR。诚实列缺口(无真前端/当期启发式/seeded用户/回测一例/无自动清理)。Docker未build验证但uvicorn实起served HTTP。
- A grounding.py对抗(裁判同探针): B编造37%散文拦✓(扫散文,无散文洞) D2000拦✓ E注入+9999拦✓; **容差洞**1005放行(同B); **额外always-allowed洞**编造"100%"放行(_ALWAYS_ALLOWED={0,1,100}); 真值12.5%误拦(保守符号处理,偏标红=安全方向)。
- 三家幻觉防线定谳:
  * A=B同架构(正则扫散文,无散文洞,有容差洞); A多一个always-allowed{0,1,100}小洞+保守符号(偏误报安全向)。
  * C异构(结构化FigureRef精确匹配,无容差洞,off-by-digit都逮; 但散文洞:claim裸数不扫靠系统提示软兜)。
  * 三家核心均真强制、离线可测、非玩具; 各有可复现边缘洞。理想=C精确+AB散文扫描合体。
