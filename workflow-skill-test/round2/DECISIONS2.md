# DECISIONS2.md — 第二轮(sqlite-utils validate)产品决策口径(评测私有,三组统一)

以 Iris(PM)身份答复,只给决策不给实现建议:

1. **JSON Schema 方言**:Draft 2020-12。允许新增 `jsonschema` 作为运行时依赖(这是"说得出理由"的那种)。
2. **NULL 语义**:SQLite NULL 按 JSON null 参与校验;想允许空就在 schema 里显式写(如 type: ["string","null"]),工具不放水。
3. **TEXT 单元格里存 JSON 文本**:当 schema 对该列期望 object/array 时,尝试解析后校验;解析失败本身就是一条违规。其他情况不解析,按存储值算。
4. **命令形态**:`sqlite-utils validate DATA.db TABLE SCHEMA.json`;`--limit N` 限制检查行数(默认全表);JSON 报告与 HTML 报告的开关/路径参数命名是技术决策。
5. **退出码**:0=无违规;1=有违规;2=用法或输入错误(表不存在、schema 非法等)。
6. **行标识**:报告中每条违规必须能定位到行(rowid 或主键)与列/路径。
7. **大表策略**:校验可跑全表(流式,别一次性载入);HTML 报告内嵌违规明细默认上限 1000 条(可参数覆盖),汇总统计始终基于全量;前端对明细做分页渲染(每页大小技术决策)。
8. **报告 JSON 内容底线**:summary(检查行数、违规行数/条数、按列统计、按错误类型统计)+ violations 明细(行标识、列/路径、消息、期望约束、实际值)。字段命名是技术决策。
9. **HTML**:单文件、全内联、零外部请求;浏览器兼容以现代 Chrome/Edge/Firefox 为准;暗色模式不要求。
10. **范围**:v1 单表单 schema;多表/全库、schema 自动推断都不做。
11. **运营侧交互底线**(验收会看):按列筛、按错误类型筛、关键字搜索、排序、单条详情展开(期望 vs 实际)。图表锦上添花不强制。
12. **框架/构建选型**(vite vs esbuild、原生 TS vs preact 等):技术决策,自己定并记录。

## 补充口径(R2 superpowers 提问后新增,三组统一)

13. **行标识**:优先用表主键(复合主键全部列出),无主键的表退回 rowid;报告单列显示。
14. **敏感数据展示**:HTML 报告默认只显示违规列的实际值(超长截断),不展示整行;整行展示需显式开关打开。
15. **类型严格度**:默认严格——schema 写 integer、单元格是 TEXT "42" 算违规(要暴露类型漂移);另提供宽松强转开关(命名技术决策)。
16. **表结构与 schema 不一致**:(a) 表里多出的列默认忽略,除非 schema 写了 additionalProperties:false——行为完全由 JSON Schema 决定,不发明私有规则;(b) required 的列在表结构里根本不存在 → 报一条表级错误,不逐行刷屏。
17. **大表默认**:全表扫描(计数必须准确),HTML 明细默认只保留前 1000 条并在顶部标注"共 N 条";同时要有"限制检查行数"的快速抽查参数(语义与明细上限分开,命名技术决策)。
18. **HTML 界面语言**:英文(上游开源项目惯例),不做语言开关,别增加维护面。
19. **范围确认**:一次一张表、一份 schema;多表映射不做。

## 补充口径(R2 mattpocock 提问后新增,三组统一)

20. **类型漂移单列错误类型**:"类型不符但可强转"(TEXT "42" vs integer)与"真垃圾"分成两种错误类型,报告里可分开筛。
21. **空字符串 ≠ 缺失**:'' 是合法字符串;NULL 的统一语义见口径 2 与 26。
26. **NULL 统一语义(三组必须一致,B 语义)**:SQLite NULL = "字段存在、值为 JSON null"——不触发 required 违规(列总是存在),但触发 type 违规,除非 schema 显式允许 "null"(如 ["string","null"])。想禁 NULL 就别在 type 里写 null,这让"允许为空"完全由 schema 表达。已向 mattpocock 组补发澄清纠正措辞歧义。
22. **跨行约束(唯一性/行数)v1 不做**:JSON Schema 没这词汇,不发明 DSL;仅行级校验 + 表级"schema 提到的列不存在"错误。
23. **HTML 报告必含**:表名、总行数、按列/按错误类型的违规计数、生成时间戳、schema 文件名(basename)、数据库文件名(basename);**禁止出现绝对路径**(泄露机器布局);team/ticket 链接不要。
24. **门禁语义**:任何违规即非零退出,不做百分比阈值。
25. **JSON Schema 支持面底线**(产品验收条件):我们现有 schema 常用的关键字必须支持——type(含 ["x","null"] 联合)、properties、required、enum、minimum/maximum、minLength/maxLength、pattern、additionalProperties;超出支持面的关键字必须**大声报错拒绝**,绝不允许"装作校验过了"。至于用 jsonschema 库还是库内实现,是技术决策。
