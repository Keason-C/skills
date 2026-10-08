# taskflow: a dependency-aware async task scheduler (TypeScript)

Build `taskflow`, a TypeScript library (Node 22, ESM, no runtime dependencies) that runs async
tasks with dependencies, bounded concurrency, priorities, retries with exponential backoff,
per-attempt timeouts and cancellation.

The public API is fixed in `src/index.ts` (types and signatures are already there; keep them).
An automated acceptance suite you cannot see will import from `src/index.ts` using vitest, drive
time with its own fake `Clock`, and check states, results, events and timer hygiene, so follow the
semantics below precisely. `npm test` (vitest) and `npm run typecheck` (tsc, strict) are set up.

## Time

All time goes through the injected `Clock` (`now`, `setTimeout`, `clearTimeout`). The scheduler
must never use real timers or `Date.now()` directly, and must never defer its own internal
bookkeeping to a timer: reacting to a settled task promise may only take microtasks. The only
timers the scheduler creates are retry backoff delays and per-attempt timeouts, and it must clear
every timer it no longer needs (a fake clock's pending-timer count is checked).

## Tasks

```ts
const s = new Scheduler({ concurrency: 2, clock });
s.add({ id: "fetch", run: async (ctx) => ..., deps: [], priority: 0, retries: 0, backoffMs: 0, timeoutMs: undefined });
s.start();
await s.result("fetch");
```

- `id` is unique for the scheduler's lifetime: adding a duplicate id throws an `Error`.
- `deps` are ids of tasks that must **succeed** before this one may start. They may refer to tasks
  that have not been added yet (forward references); the task waits until they are added and
  succeed. If adding a task would create a dependency cycle (including depending on itself),
  `add` throws a `CycleError` whose `cycle` property lists the ids on the cycle, and the task is not
  added (the scheduler is unchanged).
- `run(ctx)` receives `ctx.signal` (an `AbortSignal` for this attempt), `ctx.attempt` (1-based) and
  `ctx.deps` (an object mapping each dependency id to its result value). A `run` that throws
  synchronously is treated like one that rejects.
- `priority` (default 0, any finite number): among ready tasks, higher priority starts first; equal
  priority starts in the order the tasks became ready; tasks that became ready at the same moment
  start in the order they were added.
- `retries` (default 0): how many extra attempts after a failed attempt. Before retry attempt `n+1`
  following failed attempt `n`, the task waits `backoffMs * 2^(n-1)` ms (on the clock), then becomes
  ready again (re-entering the ready order at that moment).
- `timeoutMs` (optional): an attempt still running after `timeoutMs` fails with a timeout; its
  signal is aborted and its concurrency slot is released at that moment. Anything the timed-out
  `run` later resolves or rejects with is ignored. A timeout counts as a failed attempt and may be
  retried.

## States

`state(id)` returns one of `"waiting"` (dependencies not yet succeeded), `"queued"` (ready, waiting
for a slot or for `start()`), `"running"`, `"retrying"` (waiting out a backoff), `"succeeded"`,
`"failed"`, `"cancelled"`. Unknown id: throws an `Error`.

## Scheduler lifecycle

- A new scheduler is paused: tasks may be added but none start until `start()`. `pause()` stops
  starting new tasks (running ones continue); `start()` resumes.
- Dispatch is synchronous: whenever a slot is free and a task is ready while the scheduler is
  started, the task's `run` is invoked before the call that caused it (`start`, `add`, `cancel`, a
  clock timer callback, or the internal reaction to a settled task) returns.
- `concurrency` must be an integer ≥ 1, otherwise the constructor throws a `RangeError`.

## Failure, cancellation and results

- A task whose final attempt fails ends `"failed"`. Every task that (transitively) depends on a
  failed or cancelled task ends `"cancelled"` (its `run` never starts). A task added later whose
  dependency has already failed or been cancelled is cancelled immediately during `add`.
- `cancel(id, reason?)` cancels a task that is not yet finished (waiting, queued, running or
  retrying) and returns `true`; for finished or unknown tasks it returns `false`. Cancelling a
  running task aborts its signal and releases its slot immediately; whatever its `run` later
  settles with is ignored. Cancelling also cascades to dependents as above.
- `result(id)` returns a promise that resolves with the task's value when it succeeds, or rejects
  with a `TaskError` when it ends failed or cancelled. `TaskError` has `taskId`, `kind`
  (`"failed"`, `"timeout"`, `"cancelled"` or `"dependency"`), `attempts` (attempts started) and
  `cause` (the underlying error / reason, if any). Use `"timeout"` when the final failed attempt
  timed out, `"dependency"` when the task was cancelled because of a dependency, and
  `"cancelled"` for an explicit `cancel`.
- The library must never cause unhandled promise rejections, whether or not anyone calls
  `result`.
- `onIdle()` returns a promise that resolves once no task is waiting, queued, running or retrying
  (immediately, i.e. in a microtask, if that is already true).

## Events

`on(event, listener)` subscribes and returns an unsubscribe function. Events and their listener
arguments:

| event     | arguments                                   | when                                        |
|-----------|---------------------------------------------|---------------------------------------------|
| `start`   | `(id, attempt)`                             | an attempt's `run` is about to be invoked   |
| `success` | `(id, value)`                               | the task succeeded                          |
| `retry`   | `(id, nextAttempt, delayMs, error)`         | an attempt failed and a retry is scheduled  |
| `failure` | `(id, error: TaskError)`                    | the task ended failed                       |
| `cancel`  | `(id, error: TaskError)`                    | the task ended cancelled                    |
| `idle`    | `()`                                        | the scheduler became idle                   |

Events are emitted synchronously at the moment the corresponding transition happens. When a task
finishes, its own event (`success` / `failure` / `cancel`) comes first, then the cancellations it
cascades (in the order the affected tasks were added), then the `start` events of whatever gets
dispatched next, then `idle` if the scheduler became idle.

## Deliverables

- The library in `src/` with the fixed public API exported from `src/index.ts`.
- Your own tests in `test/` (vitest), passing `npm test`; `npm run typecheck` clean.
- A short `NOTES.md`: design overview and any decisions you made about behaviour this brief leaves
  open.
