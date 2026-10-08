# taskflow hidden acceptance suite

Put this folder at `<project>/hidden-test/` next to the contestant's `src/`, then run
`npx vitest run hidden-test`. To type-check, add `"hidden-test"` to the tsconfig `include`.

Tests import `../src/index.js` and `./helpers.js`. The `.js` suffix is deliberate. With the
starter tsconfig (NodeNext, no `allowImportingTsExtensions`), a `.ts` suffix fails tsc with
TS5097. tsc maps `.js` to `src/index.ts`, and Vite/vitest resolves it the same way.

All time goes through `FakeClock` in `helpers.ts`. Tests never use real time and never use
vitest fake timers. `flush()` drains microtasks with `setImmediate`.

| file                 | tests | covers                                                                                  |
|----------------------|------:|-----------------------------------------------------------------------------------------|
| basics.test.ts       | 14 | add/start/pause, states, results, `ctx.signal`/`attempt`/`deps`, sync-throwing `run`        |
| deps.test.ts         | 13 | forward references, waiting, multi-dep/diamond, cascades, add after dep failed/cancelled   |
| order.test.ts        | 15 | concurrency limit, priority, ready order, add-order tie-break, synchronous dispatch        |
| retry.test.ts        | 10 | backoff schedule on the clock, retry events, re-entering ready order, attempts (backoff > 0 only) |
| timeout.test.ts      | 13 | signal abort, slot released and refilled in the timer callback, late settle ignored, retried timeouts |
| cancel.test.ts       | 12 | cancel queued/running/waiting/retrying, return values, late settle ignored, cascades       |
| events.test.ts       | 14 | exact event sequences, including the order within one completion                         |
| cycle.test.ts        |  8 | self/2/3-cycles via forward refs, scheduler unchanged, no false positives (set comparison) |
| idle.test.ts         |  8 | `onIdle()` and the `idle` event for ordinary busy-to-idle transitions                    |
| hygiene.test.ts      | 11 | no unhandled rejections (process listener), zero pending timers, no timers when none are needed |
| validation.test.ts   | 12 | concurrency `RangeError` (5 cases), duplicate ids, unknown-id `state`, accepted defaults/priorities |
| po.test.ts           | 42 | only outcomes fixed by clarifications.md (decisions 1, 2, 3, 4, 5, 7, 8, 9, 10, 11, 12)  |
| **total**            | **172** | (counts include `it.each` expansions)                                              |

## Notes for graders

- If an implementation leaks unhandled rejections, vitest also reports them as "Unhandled
  Errors" and may attribute them to whichever test is running. Read per-test results.
- `FakeClock.runNext()` fires one timer without flushing microtasks. Tests use it to check that
  dispatch inside a timer callback is synchronous.
