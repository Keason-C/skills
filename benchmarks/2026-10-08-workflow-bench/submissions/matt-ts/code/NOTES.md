# taskflow: notes

## Design overview

Everything lives in `Scheduler` (`src/index.ts`), with a few dependency-free helpers in
`src/internal.ts` (a deferred whose rejection is pre-handled, cycle search, `TimeoutError`).

- **Tasks** are records holding their spec, state, attempt count, the current attempt's
  `AbortController`/timers, and a pre-created result deferred. `result(id)` returns that deferred's
  promise. It has a no-op `catch` attached, so a failed or cancelled task never causes an unhandled
  rejection, whether or not anyone calls `result`.
- **Dependents index**: `dependents: Map<id, Task[]>` maps every dependency id, including ids that
  have not been added yet, to the tasks that depend on it, in add order. That one index handles
  forward references, readiness after a success and cascades.
- **Ready queue**: a set of queued tasks. Dispatch picks the best one by priority (higher first),
  then by the *ready transition* sequence number (earlier first), then by add index. Each transition
  that makes tasks ready (an `add`, one success unblocking its dependents, a retry re-queue, a
  backoff timer firing) gets a new sequence number. So "became ready at the same moment" means
  "in the same synchronous transition", not the same `clock.now()`.
- **Attempts** get a fresh token. The reaction to the `run` promise (one `.then`, with no extra
  microtask hops) and the timeout timer both check the token, so anything a timed-out or cancelled
  attempt settles with afterwards is ignored. A synchronous throw from `run` becomes a rejected
  promise.
- **Operations and re-entrancy**: every entry point (`add`, `start`, `cancel`, a timer callback, a
  settled-attempt reaction) runs through `operate()`. Nested calls (from event listeners, abort
  listeners or a task's `run`) apply their state changes and emit their own events immediately.
  Dispatch and the idle check run only when the outermost operation finishes its step. That keeps
  the documented event order for the outer operation: own event, then cascaded cancels, then
  `start`s, then `idle`. A nested call may return before a task it made ready has started, but that
  task always starts before the outermost call returns. (The PO agreed to this.)
- **Timers**: the only timers are retry backoffs (only when the delay is > 0) and per-attempt
  timeouts. A timeout timer is cleared when its attempt settles or is cancelled, and a backoff timer
  is cleared on cancel. Timers that fire are not cleared again.

## Decisions on behaviour the brief leaves open (confirmed with the PO)

- **"Became ready at the same moment"** means "in the same synchronous transition", not the same
  `clock.now()`. Ready order is the sequence of ready transitions. Add order breaks ties only among
  tasks made ready by one transition. Example: with C running, E depending on C added before D,
  and D queued, D starts before E.
- **Re-entrant calls** (from listeners or `run`) apply their changes immediately. Dispatch and the
  idle check are deferred to the end of the outermost operation (see above).
- **`onIdle()` called mid-operation**, once the last task has just finished but before `idle` has
  been emitted, resolves with that `idle` transition rather than ahead of it.
- **Zero backoff**: no timer. After the `retry` event (with `delayMs` 0) the task goes straight back
  to `queued`, or to `running` if a slot is free, within the same call.
- **Validation in `add`**. The task is not added if any check fails:
  - `run` missing or not a function: `TypeError`.
  - `RangeError` for a non-finite `priority`, `retries` that is not an integer ≥ 0, `backoffMs` < 0
    (or NaN or Infinity), or `timeoutMs` ≤ 0 (or NaN) when given. `timeoutMs: Infinity` is accepted
    and means no timeout timer.
  - Duplicate id: `Error`. Cycle: `CycleError`.
- **Duplicate deps** in a spec are de-duplicated.
- **`CycleError.cycle`** lists each id on the cycle once, starting at the task being added and
  following "depends on" edges: `['X','a','b']` for X→a→b→X, and `['X']` for a self-dependency.
- **`result(id)` for an unknown id** throws an `Error` synchronously. It does not accept forward
  references.
- **Listener exceptions** are caught and ignored. The other listeners still run and scheduler state
  is unaffected.
- **`idle`** fires only on a transition from busy to idle. It never fires on construction, on
  `start()` of an empty scheduler, or for an `add` whose task is cancelled immediately while the
  scheduler is already idle. A task waiting on a dependency that is never added keeps the scheduler
  busy.
- **Timeout errors**: a timed-out attempt's signal is aborted with a `TaskError` of kind `"timeout"`
  (with `attempts` = attempts started, and `cause` = a `TimeoutError`). The same object is the
  `retry` event's `error` if the task is retried, and is the final `TaskError` if it was the last
  attempt.
- **Failed attempts**: the `retry` event's `error` is the raw error thrown by `run`. The final
  `TaskError` has kind `"failed"` and `cause` = that raw error.
- **Explicit cancel**: `TaskError` kind `"cancelled"`, `cause` = the given reason (or undefined),
  `attempts` = attempts started so far. A running attempt's signal is aborted with that `TaskError`.
- **Dependency cancels**: kind `"dependency"`, `attempts` 0, and `cause` = the `TaskError` of the
  *direct* dependency through which the cascade arrived (so for A→B→C with A failing, C's cause is
  B's error). All cascaded tasks change state first, then their `cancel` events are emitted in add
  order.
- **Order within a transition**:
  - On success, the `success` event is emitted, then dependents become ready.
  - On cancel or timeout, the task's state changes first, then its signal is aborted, then events are
    emitted.
  - A delayed retry's backoff timer is created before the `retry` event.
- **Re-entrant `pause()`** from a `start` listener stops the remaining dispatches in that pass. The
  attempt whose `start` already fired still runs. If a `start` listener cancels that same task, its
  `run` is not invoked.
