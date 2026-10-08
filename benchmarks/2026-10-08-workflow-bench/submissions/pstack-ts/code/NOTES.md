# taskflow notes

## Design

The whole library is in `src/index.ts`.

**Task state.** Each task holds one `Phase` value, a discriminated union of the seven public
states. Phases that need data carry it. `queued` has its ready moment, `running` has its
`Attempt`, `retrying` has its backoff timer handle, and the terminal phases have the value or the
`TaskError`. `state(id)` returns `phase.kind`.

**Stale work.** An `Attempt` holds the attempt number, its `AbortController` and its timeout
timer. A settle reaction or timeout callback first checks that its attempt is still the task's
current running attempt. If it is not, the callback does nothing. This one check covers
cancellation, timeouts and late settles.

**Ready order.** Ready tasks go in a binary heap ordered by priority (highest first), then ready
moment, then add order. A moment is one synchronous step, such as one `add`, one settle reaction
or one timer callback. Entries for tasks that left `queued` are skipped when they reach the top.

**Transactions.** `add`, `start`, `cancel`, timer callbacks and settle reactions each run inside
`transaction()`. Events are queued during the transaction and delivered in order. Then the
outermost transaction dispatches tasks while slots are free, and checks whether the scheduler
became idle. The event queue preserves the documented order (own event, cascade in add order,
`start` events, `idle`) when listeners call back into the scheduler.

**Results.** Every task gets one result promise when it is added. A no-op `catch` is attached,
so a rejection is never unhandled, whether or not anyone calls `result`.

**Timers.** The scheduler creates only two kinds of clock timer: backoff delays above 0 and
per-attempt timeouts. A timeout timer is cleared when its attempt settles or is cancelled. A
backoff timer is cleared when its retrying task is cancelled. A timer that has fired is dropped
without calling `clearTimeout`.

## Behaviour decisions

The product owner answered these questions.

- **Cycle shape.** `CycleError.cycle` starts at the new task and lists each id once, with no
  repeat at the end. Adding C with deps [A], where A depends on B and B depends on C, gives
  `["C", "A", "B"]`. A self-dependency gives `["a"]`. The check only looks at the graph, not task
  states, and it runs before the failed-dependency check.
- **`add` errors.** `add` checks in this order: duplicate id (`Error`), option validation
  (`RangeError`), then cycles (`CycleError`). Validation rejects a non-finite `priority`,
  `retries` that is not an integer of 0 or more, `backoffMs` below 0, and a `timeoutMs` that is
  given and not above 0.
- **Cascade cause.** A task cancelled by a cascade gets kind `"dependency"` with `attempts` 0.
  Its `cause` is the `TaskError` of the direct dependency the cascade came through. In A to B to
  C, when A fails, C's cause is B's error.
- **Timeouts.** A timed-out attempt aborts its signal with a `TaskError` of kind `"timeout"` and
  no cause. The same object is the `retry` event's error, or the final error when no retries are
  left.
- **Cancel.** `cancel(id, reason)` makes a `TaskError` of kind `"cancelled"` with `reason` as its
  cause. A running task's signal is aborted with that error, not with the raw reason.
- **Zero backoff.** A computed delay of 0 creates no timer. The `retry` event fires with
  `delayMs` 0 and the task is queued again in the same step.
- **Idle event.** `idle` fires only when one outermost call starts busy and ends idle. It does
  not fire on construction, on `start()` of an empty scheduler, or when `add` cancels a task at
  once on an idle scheduler. `onIdle()` promises resolve whenever no task is unfinished.
- **Unknown ids.** `result(id)` for an unknown id throws synchronously, like `state`.
- **Listeners.** A listener that throws is ignored, and the remaining listeners still run. Calling
  an unsubscribe function twice does nothing.
- **Cancel from `start`.** A `cancel` in a `start` listener takes effect before `run` is called,
  so `run` never runs. The attempt still counts in `attempts`.
- **Re-entrant calls.** A call made from a listener finishes after the outer event and its
  cascade. Then the scheduler dispatches what is ready and emits `idle`. All of this happens
  before the outermost call returns.
- **Ready moment.** "At the same moment" means the same synchronous step, not the same
  `clock.now()`. Two tasks that settle in separate microtasks at the same clock time are separate
  moments.

I made these decisions myself.

- Duplicate ids in `deps` are removed. `ctx.deps` maps each direct dependency to its value. It is
  built with `Object.fromEntries`, so an id such as `__proto__` is safe.
- When a cascade reaches a task by several paths, the cause comes from the dependency that a
  breadth-first walk from the finished task reaches first.
- Events are delivered when the step that caused them has finished its state changes, still
  inside the same call. So a listener sees the step already applied. A `success` listener sees
  the task's released dependents as `queued`. A `failure` or `cancel` listener sees the whole
  cascade as `cancelled`. Events from a call made inside a listener are delivered after the
  outer step's events, so that call returns before its own events reach listeners. The
  event order is the documented one either way.
- On a timeout or a cancel of a running task, the scheduler updates its state first, then aborts
  the signal, then delivers events.
- For a zero-delay retry, a `retry` listener sees the task as `queued`. For a longer delay, it
  sees `retrying`.
- `timeoutMs: Infinity` passes validation and means no timeout, so no timer is created.
- `pause()` only stops new dispatches. Backoff timers keep running. When one fires, the task
  becomes `queued` and waits for `start()`.
- Registering the same listener twice gives two subscriptions, and each unsubscribe removes only
  its own subscription.

## Tests

`test/` holds a black-box suite written from the brief and the decisions above, by an agent that
did not read the implementation. After merging, two of its cascade expectations were corrected
to include the `idle` event that follows cancelling the last unfinished task. `test/smoke.test.ts`
came with the implementation. It uses a fake clock in `test/fakeClock.ts` and an event recorder in
`test/harness.ts`. `scripts/mutate.mjs` applies 18 targeted defects to `src/index.ts`, one at a
time, and checks that the suite catches each one. Run it with `node scripts/mutate.mjs`.
