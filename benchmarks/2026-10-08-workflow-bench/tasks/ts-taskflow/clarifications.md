# taskflow — product owner's decisions (NOT shown to developers; answer only what is asked)

1. `backoffMs` 0 (or a computed delay of 0): no timer is created; the task is re-queued
   synchronously right after the `retry` event (which still fires, with `delayMs` 0).
2. Exceptions thrown by event listeners are caught and ignored; the remaining listeners still run
   and the scheduler state is unaffected. Unsubscribing twice is harmless.
3. `result(id)` for an id that has never been added throws an `Error` synchronously (no forward
   references for results). Calling `result(id)` several times returns promises that settle the same
   way (may or may not be the same promise object).
4. `onIdle()` on a scheduler that has no unfinished tasks resolves even if it was never started.
   A paused scheduler with queued tasks is NOT idle. Tasks waiting on dependencies that were never
   added keep the scheduler from being idle. `idle` event fires on each transition from busy to idle
   (not on construction, not repeatedly while already idle). `start()` on an empty scheduler emits no
   `idle` event.
5. Cancelling a task that is `retrying` clears its pending backoff timer. Every attempt that settles
   (or is cancelled) before its timeout clears its timeout timer. After everything is finished the
   clock must have zero pending timers created by the scheduler.
6. Event order on a final failure: `failure(id)` first, then `cancel` events for cascaded dependents
   (add order), then `start` events for newly dispatched tasks, then `idle`. A failed attempt that
   will be retried emits only `retry` (never `failure`).
7. `TaskError` details:
   - `name` is `"TaskError"`; it is an `instanceof Error`. `message` is free text.
   - kind `"failed"`: `cause` is what the last attempt rejected/threw with; `attempts` = attempts started.
   - kind `"timeout"`: `cause` is undefined or a timeout description (not checked); `attempts` counted the same.
   - kind `"cancelled"`: `cause` is the `reason` passed to `cancel` (undefined if none); `attempts` = attempts started so far (0 if never started).
   - kind `"dependency"`: `cause` is the `TaskError` of the dependency that caused the cascade (the direct
     dependency through which it arrived, i.e. for A→B→C with A failing, C's cause is B's TaskError);
     `attempts` 0.
   - For a cancelled or timed-out running attempt, `ctx.signal.reason` is the corresponding `TaskError`
     (for a timeout that is retried, an error of kind `"timeout"` describing that attempt).
8. `priority` may be negative or fractional. Non-finite priority → `add` throws `RangeError`.
   `retries` must be an integer ≥ 0, `backoffMs` ≥ 0, `timeoutMs` > 0 if given; otherwise `RangeError`.
9. `cancel` on a `waiting` task whose dependencies were never added works (returns true).
10. `CycleError.cycle` contains exactly the ids on one cycle created by the new task (order not
    important); it is `instanceof Error` with `name` `"CycleError"`. A self-dependency gives `[id]`.
11. When a running task is cancelled or times out, the freed slot is refilled synchronously within the
    same `cancel` call / timer callback (after the `cancel`/`retry`/`failure` events).
12. `start()` while already started, or `pause()` while paused, does nothing.
