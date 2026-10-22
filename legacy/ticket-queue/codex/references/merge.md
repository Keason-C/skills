# Merge the wave

Read this only when the wave's deliverable tickets are ready. One merge subagent has exclusive write access to the target branch and receives every ticket to be merged in this wave.

## The only task templates

`x` and `y` are ticket numbers; `<worktree_x>` and `<worktree_y>` are their absolute paths. `<merge_reference>` is the absolute path of this file.

One ticket:

```text
Merge issue x into this branch; clean up the worktree after successful delivery.
Worktree for issue x: <worktree_x>
Merge rules: <merge_reference>
```

Multiple tickets:

```text
Merge issue x & issue y into this branch; clean up the worktrees after successful delivery.
Worktree for issue x: <worktree_x>; worktree for issue y: <worktree_y>
Merge rules: <merge_reference>
```

Replace every variable in the planned order, extending the same format for additional tickets. List each actual ticket number and path individually, without ranges or ellipses, and include only deliverable tickets. Show the user the complete prompt being sent as a progress update. Apart from the path information, the merger locates the materials itself.

"This branch" must be the confirmed target branch. Attach this file's absolute path to the first dispatch and require the merger to read the delivery rules before acting under existing authorization. Begin integration if there is no conflict already in progress; otherwise resolve conflicts using the tickets, specifications, and the intent of both sides' changes, then validate.

## Delivery and completion criteria

The merger verifies that writing has stopped in each ticket's worktree and reads each final HEAD. Every change to be delivered must have a local commit; create missing commits only within the authorized scope. Squashing does not include uncommitted changes.

The same merge subagent squashes, validates, and commits tickets in order, with one commit on the target branch per ticket. Preserve unrelated user changes and complete ticket closeout under the project's conventions. Validation after the last ticket must cover the integrated result of the entire wave.

After the wave passes validation, perform authorized pushes and remote ticket operations, and verify delivery. Use only the existing target branch; do not create another remote branch or PR. After the entire wave is delivered successfully, clean up its merged worktrees and the temporary branches actually created.

The merger handles conflicts or validation failures introduced by merging. Allow at most two repair rounds in total for this wave's merge task, validating again after each round. If checks still fail, preserve the work and pause further merges into the target branch. Arrange a handoff before another role takes over, with only one writer per directory.

Recover a failed push once. If it still fails, mark it pending publication and pause further delivery. Preserve worktrees and branches if delivery fails partway through, recording which tickets were merged and which remain. On recovery, verify existing commits and continue only the remaining work; see [session recovery](recovery.md).

This branch ends when the entire wave is delivered and cleanup is complete, or when blocked or pending publication is explicitly reported. Preserve work that lacks authorization, has failed validation, or has not been delivered.
