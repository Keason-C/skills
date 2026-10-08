# taskflow reference — notes

## Design
- Single module (`src/index.ts`). Tasks live in an insertion-ordered `Map`; a reverse index
  `dep id -> dependents` is filled at add time, so forward references work without special cases.
  Each task tracks `remaining` (distinct deps not yet succeeded).
- Ready queue: array scanned for max of (priority desc, readySeq asc, addSeq asc). `readySeq` is a
  global counter assigned each time a task becomes ready; tasks made ready by one transition are
  numbered in add order, which implements "same moment -> add order".
- Every externally triggered operation (public mutators, clock callbacks, settled-attempt
  reactions) runs inside an enter/exit pair. Only the outermost exit dispatches (pump) and checks
  for the busy->idle transition, then loops in case an idle listener added work. This gives the
  event order own-event -> cascades -> starts -> idle, and keeps dispatch synchronous for the
  caller.
- Each attempt is an object (AbortController + timeout handle); settlements compare against
  `task.current`, so late results after timeout/cancel are ignored. Settlement reactions are plain
  promise `.then` callbacks (microtasks only); the only timers are backoff and timeout timers,
  always cleared when no longer needed.
- `result()` returns one per-task promise created at add time with a no-op `.catch` attached, so
  no rejection is ever unhandled.

## Decisions on open points
- "Became ready at the same moment" = in the same scheduler transition, not "same clock time".
- Nested calls (from listeners or a `run` body) do not dispatch themselves; the enclosing
  outermost operation dispatches before it returns.
- A `start` listener that cancels the task prevents `run` from being invoked.
- Cascade cause with several failed paths: breadth-first from the finished task, the first direct
  dependency (ties by add order) through which the cancellation arrives. Events in add order.
- Cycle detection is structural (includes finished tasks). Duplicate-id check precedes validation,
  which precedes cycle detection. Duplicate deps are de-duplicated.
- `timeoutMs: Infinity` is accepted and means no timer; `backoffMs` must be finite.
- Running-task cancel/timeout: slot released, then signal aborted, then events.
