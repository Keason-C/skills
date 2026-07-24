---
name: git-commit
description: Manages git commits with automatic CHANGELOG.md maintenance. Use this skill whenever the user asks to commit, push, record a version, says "提交", "commit", "记录版本", "git commit", "update changelog", or any variation of wanting to save their work to git. On the first commit in a repo, creates a CHANGELOG.md to track the project history. On every subsequent commit, appends a new entry to CHANGELOG.md. Always generates an English Conventional Commits message. Do NOT skip this skill for simple commits — it must always run when the user wants to commit.
---

# Git Commit Skill

You manage git commits with two responsibilities: maintaining a Chinese-language `CHANGELOG.md` that records project history, and generating a proper English Conventional Commits message.

## Step 1: Assess the situation

Run these to understand the current state:
```bash
git log --oneline 2>/dev/null | head -20   # see commit history
git status                                   # see what's changed
git diff --staged                            # see staged changes
git diff                                     # see unstaged changes
```

Determine:
- Is this the **first commit** (no prior commits, or CHANGELOG.md doesn't exist)?
- What files have changed, and what do those changes do?

If there are no staged changes, stage everything: `git add -A` — unless the user explicitly said to stage only specific files.

## Step 2: Update CHANGELOG.md

### First commit

Create `CHANGELOG.md` in the project root with this structure:

```markdown
# 变更日志

本文档记录项目的所有重要变更，包含功能说明、版本信息和更新时间。

---

## [初始版本] - YYYY-MM-DD HH:MM

### 项目概述
[用 2-3 句话描述这个项目是做什么的，基于你对文件结构和代码的理解]

### 初始功能
- [列出主要功能点，每条一行]
- [从文件结构、README、代码注释等推断]
- [尽量具体，避免空洞描述]

### 技术栈
- [从代码文件推断使用的主要技术/框架]
```

### Subsequent commits

Append a new section **at the top** (below the header and introductory paragraph, above existing entries):

```markdown
## [vX.X.X 或简短标识] - YYYY-MM-DD HH:MM

### 变更内容
- [每条变更一行，基于 git diff 内容]
- [说明做了什么，不是说文件名变了]

### 涉及文件
- `path/to/file.ext` — [一句话说明这个文件发生了什么变化]
```

For the version label:
- If the repo has tags, use the latest tag as reference
- Otherwise, count commits: first=v0.1.0, then increment the patch number (v0.1.1, v0.1.2...) for fixes/small changes; minor (v0.2.0) for new features; major (v1.0.0) for breaking changes

Always use actual current date/time — do not make up times. Use: `date "+%Y-%m-%d %H:%M"` to get it.

## Step 3: Stage CHANGELOG.md and commit

```bash
git add CHANGELOG.md
git commit -m "<type>(<scope>): <description>"
```

### Conventional Commits format

```
<type>[optional scope]: <description>

[optional body]

[optional footer]
```

**Types:**
| Type | When to use |
|------|-------------|
| `feat` | New feature or capability |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `style` | Formatting, whitespace (no logic change) |
| `refactor` | Code restructure without feature change |
| `perf` | Performance improvement |
| `test` | Adding/fixing tests |
| `chore` | Build, config, dependencies |
| `ci` | CI/CD changes |

**Rules for the description line:**
- Lowercase, imperative mood ("add" not "added" or "adds")
- No period at the end
- Max ~72 characters
- Be specific: `fix(auth): handle token expiry on refresh` not `fix: bug fix`

**Scope** (optional): the module/area affected, e.g. `feat(api)`, `fix(ui)`, `chore(deps)`

**First commit**: always use `feat: initial commit` or `chore: initial project setup`

**Body** (optional): add when the description alone doesn't explain *why*. Separate from description by a blank line.

**Breaking changes**: add `BREAKING CHANGE:` in the footer, or `!` after type: `feat!: redesign API response format`

### Examples

```
feat(parser): add strikethrough cell filtering for xlsx files
fix(price-matcher): handle missing supplier column gracefully
docs: update README with new environment variables
chore: add CHANGELOG.md and initial project documentation
refactor(llm): extract retry logic into separate generator
feat: initial commit — ZF Sourcing Agent v1.0.0
```

## Step 4: Confirm

After committing, show the user:
1. The commit hash and message: `git log --oneline -1`
2. A brief summary of what was added to CHANGELOG.md

Keep the confirmation brief — one or two lines is enough.
