---
name: git-commit
description: Generate high-quality English Conventional Commits messages whenever the user wants to commit or push ("提交", "commit", "记录版本", etc.), and — only when explicitly asked ("出个 changelog", "更新变更日志", "release notes", "发版") — generate or update a Chinese CHANGELOG.md by summarizing git history since the last release. Commits never touch the changelog; the changelog is a release-time artifact derived from commit history.
---

# Git Commit Skill

Two independent modes. Committing is the everyday path and stays lightweight; the changelog is generated on demand from git history, never maintained per commit.

## Mode 1 — Commit (default)

Triggered by any request to commit/push.

### Step 1: Assess

```bash
git status
git diff --staged
git diff
git log --oneline | head -5   # match repo's existing message style
```

If nothing is staged, stage everything with `git add -A` — unless the user asked to stage specific files only.

### Step 2: Commit with a Conventional Commits message

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

**Description line rules:**
- English, lowercase, imperative mood ("add" not "added"), no trailing period, ≤72 chars
- Be specific: `fix(auth): handle token expiry on refresh`, not `fix: bug fix`
- **Scope** (optional): module/area affected — `feat(api)`, `chore(deps)`
- **Body** (optional): only when the description alone doesn't explain *why*
- **Breaking changes**: `!` after type (`feat!: ...`) or `BREAKING CHANGE:` footer

### Step 3: Confirm

Show `git log --oneline -1`. One line is enough. Do **not** create or update CHANGELOG.md in this mode.

## Mode 2 — Changelog / release notes (only when explicitly requested)

Triggered by: "出个 changelog", "更新变更日志", "release notes", "发版", "打个版本" — never triggered by a plain commit request.

### Step 1: Determine the range

```bash
git describe --tags --abbrev=0 2>/dev/null   # last tag, if any
```

- If tags exist: summarize `git log <last-tag>..HEAD`
- Else if CHANGELOG.md has a dated entry: summarize commits since that date (`git log --since=...`)
- Else: summarize the full history

If the range is empty, say so and stop.

### Step 2: Write the entry (Keep a Changelog style, in Chinese)

Prepend to `CHANGELOG.md` (create with a `# 变更日志` header if missing):

```markdown
## [vX.Y.Z 或日期] - YYYY-MM-DD

### 新增
- [用户可感知的新功能，一条一行]

### 修复
- [修掉的问题]

### 变更
- [行为或接口变化；破坏性变更标注 **BREAKING**]
```

Rules:
- Only include sections that have content; aggregate related commits into one line
- Record **user-visible changes**, not file names or commit hashes
- Skip pure noise (`style`, merge commits); fold `chore`/`ci` into one line or omit unless significant
- Version: bump from the last tag by semver (breaking → major, feat → minor, fix only → patch); if the project doesn't use tags, use the date as the heading
- Use the real current date (`date "+%Y-%m-%d"`), never invent one

### Step 3: Offer to tag

After writing, ask whether to commit the changelog and tag the release (`git tag vX.Y.Z`). Don't tag without confirmation.
