# 变更日志

本文档记录项目的所有重要变更，包含功能说明、版本信息和更新时间。

---

## [v0.1.2] - 2026-07-24 14:49

### 变更内容
- 同步工作流新增 Anthropic 官方技能仓库（anthropics/skills）：整个 `skills/` 目录下的每个技能逐一镜像到本仓库根目录，官方新增技能会自动跟进
- 清单格式升级为 `owner/repo|路径|目标`，目标 `*` 表示按子目录扇出，避免整目录 `--delete` 误删本仓库其它技能

### 涉及文件
- `.github/workflows/sync-upstream.yml` — 新增 anthropics/skills 上游，重构同步循环支持扇出模式

## [v0.1.1] - 2026-07-24 14:45

### 变更内容
- 新增 GitHub Actions 定时同步工作流：每天 03:00 UTC 从 pydantic 官方仓库稀疏拉取三个 skill（building-pydantic-ai-agents、pydantic、pydantic-ai-harness）并镜像到本仓库根目录，有变化才提交，commit message 携带各上游 SHA
- 支持手动触发（workflow_dispatch）用于测试

### 涉及文件
- `.github/workflows/sync-upstream.yml` — 新增上游 skill 同步工作流

## [初始版本] - 2026-07-24 12:00

### 项目概述
Claude Code 技能库（skills registry）。本仓库即 `~/.claude/skills` 目录本身，团队成员 clone/pull 后技能直接生效，无需额外安装步骤。

### 初始功能
- 收录 Anthropic 官方技能 17 个（docx、pptx、xlsx、pdf、mcp-builder、skill-creator、frontend-design 等）
- 收录 ZF 内部技能 2 个（zf-ai-gateway、zf-lifetec-presentation）
- 收录自定义技能 1 个（git-commit：提交时自动维护 CHANGELOG）

### 技术栈
- Claude Code Skills（SKILL.md 格式）
- Git 分发：仓库根即 skills 根，`git pull` 即更新
