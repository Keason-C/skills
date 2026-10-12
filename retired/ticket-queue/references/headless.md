# Headless 启动

首次派工时读取。模型与 effort 使用 [入口的配置表](../SKILL.md#1-确认计划) 已解析值；本文件只负责运行机制。

## 配置与指令

核对本机 `codex exec --help` 和所需技能是否可发现。模型、effort、目录与运行权限用 CLI 参数显式设置，省略参数不代表继承主对话。写权限匹配对应工作目录及必要的 Git 公共目录；诊断使用只读约束。

Codex 按工作目录自动加载 AGENTS.md。新 worktree 使用检出版本，源目录未提交的规则不会自动带入。已有项目规则无需重复注入；会话专属授权或决定若确为任务所需，仅补最少必要信息。

将角色文档定义的提示词作为单个字符串参数发送。保留字面量 `$` 和 `&`，使用参数数组或正确的 shell 引用；不手工复制 skill 正文。各角色的材料查找由其自身完成。

## 工作目录

| 调用 | 目录与参数 |
|---|---|
| 首次执行一张票 | `-C <目标分支所在目录> --worktree`，由 Codex 创建并进入托管 worktree |
| 新诊断／备用执行会话 | `-C <该票已有 worktree>` |
| 合并会话 | `-C <目标分支所在目录>` |

仅第一种调用加 `--worktree`。启动前核对源目录的分支和 HEAD 与计划一致。

下面展示首次执行的参数形状。`role_prompt` 从对应任务模板填入真实值，运行权限参数按宿主和已有授权设置：

```bash
codex exec \
  -C "$ticket_source_dir" \
  --worktree \
  --model "$role_model" \
  -c "model_reasoning_effort=\"$role_effort\"" \
  --json \
  --output-last-message "$call_dir/final.txt" \
  "$role_prompt" \
  >"$call_dir/events.jsonl" 2>"$call_dir/stderr.log"
```

通过宿主后台或持久进程会话运行，每次调用使用独立日志目录。保存进程句柄、session/thread ID、退出结果与输出位置。`--json` 保存运行事件，最终回复保持自由文本；保留持久会话以便恢复。

## 登记 worktree

启动前后读取 `git worktree list --porcelain`，结合会话元数据定位新目录。启动一票并确认映射后，再启动下一票；已启动的执行进程继续并发运行。

只有一个明确新增目录且没有其他创建者时，才用列表差集认领；有多个候选时通过会话元数据核实。保存票号、实际绝对路径、起始 HEAD 与会话对应关系，不猜目录名。

托管 worktree 可以是 detached HEAD；其路径和最终 HEAD 足以定位工作，未要求命名分支时无需补建。进程退出后目录仍可能保留。

启动完成条件：后台句柄、会话与票据 worktree 已唯一对应，起始 HEAD 符合计划。
