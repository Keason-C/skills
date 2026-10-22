# Session recovery

Read this only for continuation, runtime failures, or recovery after interruption. First inspect the run log, `collaboration.list_agents`, worktrees, and Git status to determine which role still owns write access.

If the original subagent is still accessible and its configuration is unchanged, resume it through `followup_task` using its exact ID or task name, supplying the next task and registered directory. Use `send_message` to provide additional information to a running role. If a replacement is needed, first use `interrupt_agent` and verify that the original role and any commands it started have stopped writing before handing off. Stop only the roles and commands belonging to this task.

If the subagent cannot be accessed across host sessions, or its model or effort needs to change, use `spawn_agent` again. Reuse the registered worktree and provide the original task, confirmed configuration and authorization, necessary diagnostic evidence, last reply, and completed stages. Update the mapping between old and new IDs; do not treat the old ID as a persistent session handle for recovery.

Allow one recovery attempt for the same startup, connection, or runtime interruption failure. If recovery also fails, mark that task blocked; replacing the subagent does not reset the count. This count is separate from application repair attempts. Evaluate tool errors, role state, the worktree, and the final reply together to determine whether an invocation ended normally.

After a first dispatch fails, check existing worktrees and whether a subagent is already alive before retrying dispatch. Do not dispatch duplicate work because a wait timed out. When recovering after interruption, first verify completed commits and publication results. Continue only the remaining work, without repeating implementation, merging, or cleanup.

Preserve failure results and progress. Follow [subagent dispatch](subagents.md#messages-and-lifecycle) to close out finished roles, then return to the main scheduler.
