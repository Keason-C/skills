# Round 1 — S1 生产级认证服务

## 档案摘要
- 种子输入（三家一字不差）：生产级 auth 服务，邮箱+密码，SSO 有呼声，公网级安全，会话+密码重置，服务间查登录态/权限，拒绝玩具 demo。
- 关键预置裁决：SSO 本期不做只留架构缝；注册限公司邮箱域+邮箱验证；introspection 走 per-service API key 且权限查询须实时准确；RBAC 三角色起步；栈不指定（Python/TS 皆可，选手自选并说明理由）；生产 Postgres；邮件抽象（dev 落日志）；容器化交付 Dockerfile+文档。
- 验收标准 A1–A10 见 /workspace/bench/dossiers/S1.md（含无人值守硬指标 A10：spec 定稿后实现阶段零人工澄清）。
- 上限：规划软上限 90min/约8轮来回；实现硬上限 4h/家。

## 时间线与插手记录
- 15:25 UTC 环境初始化；A 资产=本地 matt skills，C 资产=obra/superpowers@shallow-clone，B=无 skill 对照组。
- ~15:45 UTC 三家 Opus 规划 agent 并行启动，输入为同一段种子原话。
- 15:45–16:10 规划面试期：A 三轮 30 问（附推荐答案+代价说明）；B 两批 22 问（附默认建议）；C 一次一问共 9 问 + 设计文档 3 段确认 + design.md 批准（共 13 次介入）。全部按档案作答，同题同答。
- ~16:05 A 规划完成（commit 5912d02：glossary + 8 ADR + spec(64 用户故事) + 12 tickets）。A 自我推翻初稿中"5 分钟访问令牌"设计，改为纯回源解析以满足"停用即时生效"（ADR 0008）。
- ~16:08 B 规划完成（commit 1ea0698：spec(19 条决策日志) + 15 tickets，TS 栈）。
- ~16:10 A-T01、B-T01 两个 Sonnet 实现 agent 启动（无人值守、禁提问）。
- 16:18 定时检查#1：A 在写平台层（logger/redact/migrations，带测试）；B 在写双端口 app 骨架；C design.md 定稿（a171d96 + 修订 d8826d5）正拆 phase 计划（writing-plans）。三家无卡死。
- （注：16:18 前的日志时间戳系估算，偏快约 1.5h；相对顺序准确，后续以真实时钟为准。）

## 分数表
（待打分）

## 代码级发现
（待验证后填写，证据=文件路径+行号）

## 结论
（待写）
