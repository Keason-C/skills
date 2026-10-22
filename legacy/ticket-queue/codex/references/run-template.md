# Launch template

Read this when the user needs to provide run configuration. Keep values the user has already supplied, and infer omitted values under the [main entry](../SKILL.md#1-confirm-the-plan); do not ask again for values that can be inferred.

```text
$ticket-queue

Repository: <path>
Target branch / existing PR: <branch and link>
Ticket source and scope: <directory or GitHub filter, included and excluded tickets>
Mode: <serial, or parallel with concurrency limit N>
Implementation / diagnosis model: <model>
Fallback implementation model: <model>
Authorization for this run: <scope of commits, pushes, and remote ticket updates>

Show the execution order or parallel waves first, and wait for my confirmation before starting.
```

Add role configuration, a private run directory, a check interval, or an expected HEAD only when overriding defaults. The launch request is for planning; actual dispatches use the task templates in their respective steps.
