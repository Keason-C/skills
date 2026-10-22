# Repair and diagnosis

Read this only when the ticket is unfinished or required checks fail. Roles use the confirmed configuration and work in the ticket's existing worktree.

If the reply explicitly identifies unfinished ticket work, resume the implementer to complete it; see [session recovery](recovery.md) for continuation. Handle failing checks through the following bounded sequence, rerunning validation after every repair:

1. The primary implementer repairs the failure, for at most two rounds, using the ticket's original configuration. Task:

   ```text
   Fix the failing checks in this worktree.
   ```

2. If checks still fail, dispatch a new read-only diagnostic subagent. Task:

   ```text
   Determine whether the failing checks are caused by the tests themselves or by the implementation; report which, or explain why the evidence is insufficient.
   ```

3. If the tests are defective, resume the diagnostic subagent in an implementation role for one repair and validation:

   ```text
   Fix the test defects you identified and rerun the required checks.
   ```

4. If the implementation is defective, the causes are mixed, or checks still fail after repairing tests, dispatch the fallback implementer for one repair using the task prompt from step 1.
5. If checks still fail, diagnosis is impossible, or the fallback model is unavailable, mark the ticket blocked. Preserve its worktree, commits, and existing branches; record the failure and stages already attempted, then return to queue scheduling.

The diagnostic role determines the cause from the ticket, specification, implementation, and tests; the commander dispatches work based on that conclusion. Ask for supporting evidence if the conclusion is unclear rather than guessing whether tests should change.

When changing a read-only diagnostic role to repair work, explicitly lift its read-only task restriction through `followup_task` and specify the ticket directory and existing write authorization. This does not change host permissions. If the host enforces separate read-only isolation, first obtain the required write permissions through that mechanism, or dispatch a new subagent with the necessary permissions and the diagnostic evidence. Handle invocation failures under [session recovery](recovery.md); they do not count as failed code repairs.

This branch ends when the ticket is complete and validation passes, or when it is explicitly blocked.
