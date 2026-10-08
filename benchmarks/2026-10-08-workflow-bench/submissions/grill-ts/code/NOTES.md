# taskflow: design notes

## Design overview

Everything public is defined in `src/index.ts`. Two small internals live in `src/internal/`:
`heap.ts` (a binary min-heap) and `emitter.ts` (a synchronous event emitter).

- **Task records.** Each added task has one record holding:
  - its state
  - its de-duplicated `deps` and its `dependents` (in add order)
  - an `unmet` count of dependencies that haven't succeeded yet
  - the current attempt and the backoff timer
  - a result promise, created at `add` time with a no-op `catch` attached so it can never become
    an unhandled rejection

  A dependency on an id that hasn't been added yet is parked in `forwardRefs`. When that id is
  added, the parked tasks become its dependents.
- **Ready queue.** A heap ordered by priority (higher first), then by a ready sequence number.
  `makeReady` assigns sequence numbers in the order tasks become ready. A task finishing makes its
  dependents ready in add order, so tasks that become ready together keep add order. Cancelled
  tasks are left in the heap and skipped when popped.
- **Operations and dispatch.** Every state change (`add`, `start`, `cancel`, a timer callback, a
  settle reaction) runs inside `op()`. Calls nested from `run` or from listeners increase a depth
  counter. Only the outermost `op` drains: it starts ready tasks while slots are free, then emits
  `idle` if the scheduler has just gone from not-idle to idle. It repeats if an `idle` listener added
  work. Dispatch is therefore synchronous, and the event order is always: the task's own event,
  then cascaded cancellations, then `start` events, then `idle`.
- **Commit, then emit.** A transition applies every state change first: the outcome, the cascade,
  the freed slot, and the `AbortSignal` abort. Only then does it emit events. Listeners always see
  the final states.
- **Attempts.** Each attempt gets an object with its own `AbortController` and timeout timer.
  Settle reactions and timeout callbacks compare that object with `task.current`, so the outcome
  of a timed-out or cancelled attempt is ignored.
- **Time.** Only `clock.setTimeout` and `clock.clearTimeout` are used, and only for backoff delays
  above 0 and per-attempt timeouts. Each timer is cleared as soon as it is no longer needed: on
  settle, on cancel, or when it fires.
- **Graph walks are iterative**, so chains of 100k tasks work. Cycle detection only searches when
  an existing task already references the new id (or the task depends on itself), so a normal
  `add` costs O(number of deps).

## Decisions on behaviour the brief leaves open

The full record is in `.scratch/taskflow/spec.md` (D1–D16). In short:

1. **Zero backoff:** no timer is created. The task is `"retrying"` while the `retry` event is
   emitted, then becomes `"queued"` immediately; that moment sets its place in the ready order.
2. **Error objects:**
   - A timed-out attempt produces one `TaskError(kind "timeout", cause undefined)`. That same
     object is the signal's abort reason and the `retry` error, and the final error if it was the
     last attempt.
   - An explicit cancel produces one `TaskError(kind "cancelled", cause: reason)`. That same object
     is the abort reason, the `cancel` event argument and the `result()` rejection.
   - An attempt that rejects reports the raw error in `retry`. If it was the last attempt, the
     task's error is `TaskError(kind "failed", cause: error)`.
3. **Dependency cancellations:** `attempts` is 0 and `cause` is the `TaskError` of the direct
   dependency. If several dependencies are dead, the first one in `deps` order is used.
4. **`result(id)` for an unknown id** throws synchronously, the same as `state()`. Each task always
   returns the same promise.
5. **Cycles:** detection is structural and ignores task states. `cycle` starts at the new task and
   lists each id once (`["c","a","b"]`; a self-dependency gives `["a"]`). `add` checks in this
   order: validation, duplicate id, cycle.
6. **Validation:**
   - `TypeError` for a bad `id`, `run` or `deps`.
   - `RangeError` for a non-finite `priority`, `retries` that isn't an integer ≥ 0, `backoffMs`
     that isn't finite and ≥ 0, or `timeoutMs` that isn't finite and > 0.
   - Duplicate entries in `deps` are dropped. Backoff growth has no cap.
7. **Idle:**
   - `idle` fires only on a not-idle → idle transition, so `start()` on an empty scheduler emits
     nothing.
   - An `add` that is cancelled immediately while the scheduler is idle emits no `idle`.
   - A paused scheduler with queued tasks is not idle.
   - A task waiting on an id that is never added keeps the scheduler busy until it is cancelled.
8. **Listener exceptions** are swallowed. The other listeners still run and the scheduler carries
   on.
9. **Re-entrancy:**
   - Calling `add`, `cancel`, `pause` or `start` from `run` or a listener takes effect immediately
     and emits its events inline. Dispatch waits until the outermost operation ends.
   - If a `start` listener cancels the task, its `run` is not invoked, but the attempt still counts.
10. **Listeners:**
    - Each registration is independent, and calling an unsubscribe function again does nothing.
    - An emit works from a snapshot of the listeners taken when it begins.
    - An unknown event name throws.
11. **Pause** only stops dispatch. Timeouts and backoff timers keep running, and a backoff that ends
    while paused leaves the task `"queued"`.
12. **`run`:**
    - A synchronous throw is handled in the same microtask reaction as a rejection.
    - A non-promise return value is accepted.
    - A signal is never aborted after its attempt finishes normally.
13. **"The same moment"** in the brief's ready-order rule means one synchronous transition (one
    `add`, one settled task, one `cancel`, one timer callback), not one `clock.now()` value. Tasks
    made ready by separate events queue in event order even when the clock time is equal. The
    product owner confirmed this, and also confirmed decisions 1, 4 and 7 above.
