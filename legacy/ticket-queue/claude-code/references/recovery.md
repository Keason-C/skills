# Session recovery

Read this only for continuation, runtime failures, or recovery after interruption. First inspect the run log, live processes, worktrees, and Git status to determine which role still owns write access.

For normal continuation, use the session UUID registered during dispatch and run `claude -p -r <session-uuid>` in the role's registered directory. Check the local help and pass the resolved configuration, log output, and appropriate permissions again. Do not add `--worktree` when resuming, or use `--continue` or `--fork-session`.

Wait while a process is still writing, or verify its identity before stopping it. Stop only processes belonging to this task. The session UUID was generated and registered before dispatch; if no matching record exists in the log, treat that invocation as not established rather than guessing an ID.

Allow one recovery attempt for the same startup, authentication, connection, or process interruption failure. If recovery also fails, mark that task blocked; changing the invocation does not reset the count. This count is separate from application repair attempts. Evaluate the process exit code, `is_error`, `terminal_reason`, and final reply together to determine whether an invocation ended normally.

Replacement invocations must reuse the registered worktree. Before retrying a first invocation that failed to create its worktree, verify that no process or worktree was left behind. Do not dispatch duplicate work because a tool wait timed out. Unlock a leftover managed worktree with `git worktree unlock <path>` before handling it.

When recovering after interruption, first verify completed commits and publication results, then resume only the remaining work without repeating implementation, merging, or cleanup. Preserve failure output and progress, then return to the main scheduler.
