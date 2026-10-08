import { Scheduler, type SchedulerEvents } from "../../src/index.js";
import { FakeClock } from "./fake-clock.js";

/** A promise you settle from outside, for controlling when a task's `run` finishes. */
export function deferred<T = unknown>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

const EVENTS: (keyof SchedulerEvents)[] = ["start", "success", "retry", "failure", "cancel", "idle"];

/** A scheduler on a fake clock, with every event recorded as `[event, ...args]`. */
export function setup(concurrency = 1) {
  const clock = new FakeClock();
  const s = new Scheduler({ concurrency, clock });
  const log: unknown[][] = [];
  for (const event of EVENTS) {
    s.on(event, ((...args: unknown[]) => log.push([event, ...args])) as SchedulerEvents[typeof event]);
  }
  return { clock, s, log };
}
