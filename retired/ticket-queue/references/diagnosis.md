# 修复与诊断

仅在本票未完成或门禁失败时读取。角色使用已确认配置，在本票现场工作。

回复明确有本票未完成项时，续接执行方完成它；续接操作见 [恢复会话](recovery.md)。门禁失败按下面的有限链处理，每次修复后重新验证：

1. 主执行方修复，最多两轮，使用该票原配置。任务：

   ```text
   Fix the failing checks in this worktree.
   ```

2. 仍失败，派新只读诊断子代理。任务：

   ```text
   Determine whether the failing checks are caused by the tests themselves or by the implementation; report which, or explain why the evidence is insufficient.
   ```

3. 测试问题：续接诊断子代理转为执行职责，修一次并验证：

   ```text
   Fix the test defects you identified and rerun the required checks.
   ```

4. 实现问题、混合原因，或修测试后仍失败：派备用执行方修复一次，使用第 1 步的任务提示词。
5. 仍失败、无法诊断或备用模型不可用：标记本票阻塞，保留 worktree、提交及已有分支，记下失败原因和已尝试阶段，返回队列调度。

诊断方根据票据、规范、实现和测试判断原因；指挥官按其结论派工。结论含糊时要求补足依据，不能由指挥官猜测测试是否应改。

只读诊断转为修复时，通过 `followup_task` 明确解除该角色的只读任务约束，并指定本票目录与已有写入授权；这不改变宿主权限。若宿主另有强制只读隔离，须先按其机制获得所需写权限，或新派具备相应权限的子代理并提供诊断证据。调用故障按 [恢复会话](recovery.md) 处理，不计作代码修复失败。

此分支结束于本票完成且验证通过，或明确阻塞。
