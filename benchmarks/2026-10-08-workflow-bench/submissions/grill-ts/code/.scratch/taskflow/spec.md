# taskflow: dependency-aware async task scheduler

Status: ready-for-agent

## Problem Statement

A TypeScript developer has a set of async jobs that depend on each other: fetch this, then transform
it, then upload. Running them by hand with `Promise.all` and ad-hoc retry loops is error-prone.
Ordering, limiting how many run at once, retrying flaky work with backoff, timing out hung attempts
and cancelling work all have to be rebuilt every time.

When one job fails, every job downstream of it must stop cleanly. Nothing may leak: no timers, no
unhandled promise rejections. Code that does all this by hand is also very hard to test
deterministically, because it is tied to real time.

The developer needs a small library with no runtime dependencies (Node 22, ESM) that does this with
precisely defined semantics, so that both their own code and an automated acceptance suite can rely
on exact states, results, event order and timer hygiene.

## Solution

`taskflow` provides a `Scheduler`. The developer adds tasks, each with an id, an async `run` function
and optional dependencies, priority, retries, backoff and timeout, then calls `start()`.

- **Ordering:** a task runs only after all of its dependencies succeed. Ready tasks start in priority
  order, never more than the concurrency limit at a time.
- **Retries and timeouts:** failed attempts are retried with exponential backoff, and attempts that
  run too long are timed out.
- **Cancellation:** cancelling a task, or a task failing, cancels everything downstream of it.
- **Observability:** every step is reported through synchronous events, every task's outcome is
  available as a promise, and `onIdle()` tells the developer when all work has drained.
- **Deterministic time:** all time goes through an injected `Clock`, so tests can drive the scheduler
  with a fake clock.

The public API (names, types and signatures) is fixed in advance. The behaviour is defined by the
brief plus the decisions recorded below (D1–D16).

## User Stories

### Defining and adding tasks

1. As a library user, I want to add a task with a unique id and an async `run` function, so that the
   scheduler can execute it for me.
2. As a library user, I want adding a task with an id that was already used to throw an `Error`, so
   that I can't accidentally shadow or replace a task.
3. As a library user, I want ids to stay unique for the whole life of the scheduler, finished tasks
   included, so that `state(id)` and `result(id)` are never ambiguous.
4. As a library user, I want `add` to reject a malformed spec with a `TypeError` or `RangeError`
   before anything changes, so that mistakes surface immediately rather than as odd behaviour later.
5. As a library user, I want negative and fractional priorities to be accepted, so that I can use
   whatever priority scale suits me.
6. As a library user, I want repeated entries in `deps` to be ignored, so that a sloppy dependency
   list doesn't break anything.

### Dependencies

7. As a library user, I want a task to wait until every one of its dependencies has succeeded, so
   that it never runs on incomplete inputs.
8. As a library user, I want `ctx.deps` to give me each direct dependency's result value by id, so
   that I can use upstream results without wiring them up myself.
9. As a library user, I want to declare a dependency on a task I haven't added yet, so that I can add
   tasks in any order.
10. As a library user, I want `add` to throw a `CycleError` naming the ids on the cycle when a new task
    would close a dependency cycle (including depending on itself), and leave the scheduler
    unchanged, so that a graph that could never finish is never built.
11. As a library user, I want the reported cycle to start at the task I was adding and follow
    dependency edges, so that I can see exactly which declarations to fix.
12. As a library user, I want cycle detection to stay fast and safe with very long dependency chains,
    so that big graphs neither slow down nor crash.

### Scheduling and lifecycle

13. As a library user, I want a new scheduler to start paused, so that I can add a whole graph before
    anything runs.
14. As a library user, I want `start()` to begin running ready tasks straight away, during the call
    itself, so that the behaviour is predictable and easy to test.
15. As a library user, I want `pause()` to stop new tasks from starting while running ones finish,
    and `start()` to resume, so that I can throttle or suspend work.
16. As a library user, I want calling `start()` or `pause()` twice to be harmless, so that I don't
    have to track the current mode myself.
17. As a library user, I want at most `concurrency` tasks running at once, so that I don't overload
    downstream resources.
18. As a library user, I want the constructor to throw a `RangeError` when `concurrency` isn't an
    integer of at least 1, so that a misconfiguration is caught immediately.
19. As a library user, I want higher-priority ready tasks to start first, so that urgent work jumps
    the queue.
20. As a library user, I want ready tasks of equal priority to start in the order they became ready,
    and tasks that became ready together to start in the order they were added, so that ordering is
    fair and deterministic.
21. As a library user, I want a freed slot to be refilled as soon as a task settles, without waiting
    on a timer, so that throughput isn't lost to scheduling delays.

### Retries, backoff and timeouts

22. As a library user, I want to set `retries` so that a failed attempt is tried again up to that many
    extra times, so that flaky work can recover.
23. As a library user, I want each retry to wait `backoffMs * 2^(n-1)` ms on the clock, so that
    retries back off exponentially.
24. As a library user, I want a retry with zero delay to become ready again immediately, without a
    timer, so that retries with the default backoff of 0 never need the clock to advance.
25. As a library user, I want a task that has served its backoff to rejoin the ready order behind
    tasks that were already waiting, so that retries don't jump the queue.
26. As a library user, I want `ctx.attempt` to tell me which attempt this is, counting from 1, so that
    my code can change its behaviour on retries.
27. As a library user, I want an attempt that runs longer than `timeoutMs` to fail with a timeout at
    that moment, with its signal aborted and its slot released, so that a hung task can't block the
    scheduler.
28. As a library user, I want anything a timed-out or cancelled `run` later resolves or rejects with
    to be ignored, without causing an unhandled rejection, so that late results can't corrupt state.
29. As a library user, I want a timeout to count as a failed attempt that can be retried, so that a
    transient hang can recover.
30. As a library user, I want each attempt to get a fresh `AbortSignal`, so that cancelling one
    attempt never affects the next.
31. As a library user, I want a `run` that throws synchronously to be treated like one that rejects,
    so that I don't need to write my tasks defensively.

### Failure, cancellation and results

32. As a library user, I want `result(id)` to resolve with the task's value when it succeeds, so that
    I can await individual outcomes.
33. As a library user, I want `result(id)` to reject with a `TaskError` that carries the task id, the
    kind (`failed`, `timeout`, `cancelled` or `dependency`), the number of attempts started and the
    underlying cause, so that I can tell exactly why a task didn't succeed.
34. As a library user, I want every task that depends, even transitively, on a failed or cancelled
    task to end `cancelled` without ever running, so that downstream work stops cleanly.
35. As a library user, I want such a dependency cancellation's cause to be the error of the direct
    dependency that brought it down, so that I can follow the chain of causes back to the original
    failure.
36. As a library user, I want a task added after one of its dependencies has already failed or been
    cancelled to be cancelled during `add`, so that dead branches never wait forever.
37. As a library user, I want `cancel(id, reason)` to cancel a task that is waiting, queued, running
    or retrying and return `true`, and to return `false` for finished or unknown tasks, so that I can
    stop work safely and know whether it took effect.
38. As a library user, I want cancelling a running task to abort its signal and free its slot at
    once, so that the next task starts immediately.
39. As a library user, I want the signal's abort reason to be the same `TaskError` that the result
    rejects with, so that my `run` code can see why it was stopped.
40. As a library user, I want the library never to cause unhandled promise rejections, whether or not
    I call `result()`, so that my process isn't crashed or polluted with warnings.
41. As a library user, I want `state(id)` and `result(id)` to throw for an unknown id, so that typos
    are caught immediately.

### Observability

42. As a library user, I want `state(id)` to report `waiting`, `queued`, `running`, `retrying`,
    `succeeded`, `failed` or `cancelled`, so that I can inspect progress at any moment.
43. As a library user, I want `start`, `success`, `retry`, `failure`, `cancel` and `idle` events,
    emitted synchronously as each transition happens, so that I can log, measure and react.
44. As a library user, I want the events of one transition in a fixed order (the task's own event,
    then the cancellations it causes in add order, then the `start` events of newly dispatched tasks,
    then `idle`), so that logs and assertions are deterministic.
45. As a library user, I want listeners to see final states when they call `state()`, so that a
    listener never sees half-applied transitions.
46. As a library user, I want `on()` to return an unsubscribe function that is safe to call more than
    once, so that cleaning up is easy.
47. As a library user, I want a listener that throws to be unable to break the scheduler or stop the
    other listeners, so that a bug in my logging can't take down my pipeline.
48. As a library user, I want to call `add`, `cancel`, `pause` and `start` from inside `run` or a
    listener, so that I can build dynamic workflows.
49. As a library user, I want `onIdle()` to resolve once nothing is waiting, queued, running or
    retrying (in a microtask if that's already the case), so that I can await completion of
    everything.
50. As a library user, I want `idle` to fire only when the scheduler goes from busy to idle, so that I
    get exactly one notification each time work drains.

### Time and testability

51. As a test author, I want to inject a `Clock` so that the scheduler never uses real timers or
    `Date.now()`, so that my tests are fast and deterministic.
52. As a test author, I want the scheduler's only timers to be backoff delays and attempt timeouts,
    each cleared as soon as it isn't needed, so that a pending-timer count of zero proves nothing
    leaked.
53. As a test author, I want everything the scheduler does in response to a settled task to happen in
    microtasks rather than timers, so that I only advance the clock for real delays.

## Implementation Decisions

The brief defines the base behaviour. The decisions below settle what the brief left open.

### Behaviour

- **D1. Zero-length backoff:** a retry whose computed delay is 0 creates no timer. The task enters
  `retrying`, the `retry(id, n+1, 0, error)` event fires (listeners see `retrying`), and only then
  does the task become `queued`. That moment sets its place in the ready order. Any delay above 0
  goes through the clock.
- **D2. Error objects:**
  - An attempt that rejects or throws `e`: the `retry` event carries the raw `e`. If it was the final
    attempt, the task's error is a `TaskError` of kind `failed` with cause `e`.
  - A timed-out attempt produces one `TaskError` of kind `timeout` with no cause. That same object is
    the attempt's abort reason and the `retry` event's error. If the attempt was final, it is also the
    `result()` rejection and the `failure` argument.
  - An explicit cancel produces one `TaskError` of kind `cancelled` whose cause is the given reason.
    That same object is the abort reason (if the task was running), the `cancel` event argument and
    the `result()` rejection.
- **D3. Dependency cancellations** have kind `dependency`, report 0 attempts, and take as their cause
  the `TaskError` of the direct dependency that brought them down. If several dependencies are dead,
  the first in `deps` order is used. All errors in a cascade are built before any event is emitted.
- **D4. `result(id)`** throws synchronously for an unknown id. For a known task it returns the same
  promise every time, and that promise has an internal no-op rejection handler.
- **D5. Cycles:**
  - Detection is structural and ignores task states.
  - The reported cycle starts at the task being added, follows dependency edges and lists each id
    once without repeating the first. A self-dependency reports just that id.
  - When there are several cycles, the first found by a depth-first search in declared `deps` order
    is reported.
  - `add` checks in this order: validation, duplicate id, cycle.
- **D6. Validation:** `add` throws without changing the scheduler.
  - `TypeError` when `id` isn't a non-empty string, `run` isn't a function, or `deps` isn't an array
    of strings.
  - `RangeError` when `priority` isn't finite, `retries` isn't an integer ≥ 0, `backoffMs` isn't
    finite and ≥ 0, or `timeoutMs` is given but isn't finite and > 0.
  - Backoff growth is not capped.
- **D7. Idle:**
  - `idle` fires only on a busy-to-idle transition, so `start()` on an empty scheduler emits nothing.
  - An `add` that is cancelled immediately while the scheduler is idle emits no `idle`.
  - A paused scheduler with queued tasks is not idle.
  - A task waiting on an id that is never added keeps the scheduler busy until that task is
    cancelled.
  - Pending `onIdle()` promises resolve when `idle` fires.
- **D8. Listener exceptions** are caught and ignored. The remaining listeners still run and the state
  machine continues.
- **D9. Re-entrancy:**
  - Calls to `add`, `cancel`, `pause` and `start` made from `run` or a listener take effect
    immediately and emit their own events inline. Only the outermost operation dispatches.
  - If a `start` listener cancels the task about to start, its `run` is not invoked, but the attempt
    still counts.
- **D10. Listeners:**
  - Each registration is independent, so the same function registered twice is called twice.
  - Each unsubscribe removes only its own registration, and calling it again does nothing.
  - Each emit iterates over a snapshot of the listeners taken when it begins.
  - An unknown event name throws.
- **D11. Pause** only stops dispatch. Timeouts and backoff timers keep running, and a backoff that ends
  while paused leaves the task `queued`.
- **D12. `run`:**
  - A synchronous throw becomes a rejection, handled in the same microtask reaction.
  - A non-promise return value is accepted as if it were resolved.
  - A normally completed attempt's signal is never aborted.
- **D16. Commit, then emit:** a transition applies all of its state changes before emitting any
  event: the task's outcome, the cascaded cancellations, the freed slot and the signal abort.
  Dispatch then runs and emits `start` events, and a task shows `running` inside its `start`
  listener.
- **D17. "The same moment" (confirmed by the product owner):** one synchronous transition, such as
  one task succeeding, one `add`, one `cancel` or one timer callback. Tasks made ready by that one
  event tie-break by add order. Tasks made ready by separate events are ordered by which event
  happened first, even when `clock.now()` is equal. That includes two backoff timers due at the same
  clock time, whose tasks queue in the order the timers fire.

### Modules and architecture

- **D13. Modules:**
  - **Public module:** the fixed API (`Clock`, `systemClock`, `TaskState`, `TaskContext`,
    `TaskSpec`, `TaskErrorKind`, `TaskError`, `CycleError`, `SchedulerEvents`, `SchedulerOptions`,
    `Scheduler`). All exports stay defined here unchanged, including `Scheduler`.
  - **Ready queue (internal):** a binary min-heap ordered by priority (higher first), then by a ready
    sequence number. Sequence numbers are handed out in the order tasks become ready. A finishing
    task makes its dependents ready in add order, which gives the add-order tie-break. Cancelled
    entries are left in the heap and skipped when popped.
  - **Emitter (internal):** synchronous, iterates a snapshot on each emit, swallows listener
    exceptions, and rejects unknown event names.
- **Task record:** each task keeps:
  - its state and attempt count
  - its de-duplicated deps and its dependents in add order
  - a count of dependencies that haven't succeeded yet
  - its current attempt and pending backoff timer
  - its result promise and its final value or error

  Forward references are parked under the id they refer to until that id is added.
- **Operation wrapper:** every state change runs through one wrapper: public calls, timer callbacks
  and settle reactions. A depth counter ensures only the outermost call drains. Draining dispatches
  while slots are free and the scheduler is started, then emits `idle` on the busy-to-idle edge, and
  repeats if an `idle` listener added work.
- **Attempt identity:** each attempt is its own object holding an `AbortController` and a timeout
  timer. Settle reactions and timeout callbacks act only while their attempt is still the task's
  current one.
- **Performance:**
  - Cycle search only runs when an existing task already forward-references the new id or the task
    lists itself, so an ordinary `add` costs time proportional to its number of deps.
  - Cascades and cycle searches use loops rather than recursion, so chains of 100k tasks work.

## Testing Decisions

- **One seam:** the public API, driven by an injected fake clock. Tests construct a `Scheduler`, call
  only its public methods, record every event in order, and check states, results, error fields,
  abort signals and the clock's pending-timer count. This is the same boundary the hidden acceptance
  suite uses. No test reaches into internal modules. Ready-queue ordering at scale is covered at the
  public seam by a 300-task mixed-priority test compared against a sorted-array model.
- **What a good test is here:**
  - It asserts externally observable behaviour: states, event sequences, values and errors, signal
    aborts, timer counts.
  - It uses expected values from the brief or this spec, never recomputed the way the code computes
    them.
  - It controls when tasks settle with deferred promises.
  - It controls time only through the fake clock.
  - It ends with no pending timers where relevant.
  - Files that touch failures also assert that no unhandled rejections occurred.
- **D14. Test helpers:**
  - A fake clock. Its `advance(ms)` fires due timers in due-time order, then creation order, and
    flushes microtasks before and after each one. It also exposes `pendingCount()`.
  - A setup helper that builds a scheduler on the fake clock with an event log.
  - A deferred-promise helper.
- **Coverage, one test file per area:**
  - lifecycle and validation of concurrency
  - events and listener semantics
  - dependencies and forward references
  - priority and ready order
  - failure, cascades and unhandled-rejection hygiene, including a 20k-deep chain
  - retries and backoff, including zero delay and pause during backoff
  - timeouts
  - cancellation
  - cycles and spec validation
  - idle, re-entrancy and state visibility
- **Prior art:** the starter repo had no tests. The suite was built test-first (TDD, one vertical
  slice per behaviour) and is the reference for further tests.

## Out of Scope

- Changing the public API in any way: new methods, options or event types, or different signatures.
- Real-time behaviour beyond the default `systemClock`, including the Node timer-overflow behaviour
  for delays over about 24.8 days.
- Removing or replacing a task once added, resetting the scheduler, or reusing an id.
- Persistence, distributed execution, worker threads or progress reporting within a task.
- Unbounded concurrency (`concurrency: Infinity` is rejected, as the brief requires).
- Caps or jitter on backoff, or per-task concurrency groups.
- Logging or reporting of listener exceptions; they are deliberately swallowed.
- Glossary and ADR documents; the notes document is the only design write-up.

## Further Notes

- **D15.** Work happens on the `taskflow` branch in small commits. Nothing is pushed and no PR is opened
  unless requested.
- The notes document summarises the design and these decisions for readers of the deliverable.
- Implementation status: done. The full suite and the strict typecheck pass. A follow-up
  `/code-review` against this spec is optional.
- A task that depends on an id that is never added keeps the scheduler busy indefinitely (D7).
  Callers who might hit this should cancel the waiting task.

## Comments

- Product owner confirmed D1 (no timer for zero-delay retries), D4 (`result()` throws for an unknown
  id) and D7 (no `idle` for an immediate cancel during `add` while already idle), and chose D17.

- Implemented on branch `taskflow` (TDD at the public API seam). Design overview in `NOTES.md`.
