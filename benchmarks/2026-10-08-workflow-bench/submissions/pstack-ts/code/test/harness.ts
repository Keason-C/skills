import { expect } from "vitest";
import {
  Scheduler,
  type SchedulerOptions,
  type TaskContext,
  type TaskError,
  type TaskErrorKind,
  type TaskSpec,
} from "../src/index.js";
import { FakeClock } from "./fakeClock.js";

export type Ev =
  | ["start", string, number]
  | ["success", string, unknown]
  | ["retry", string, number, number, unknown]
  | ["failure", string, TaskError]
  | ["cancel", string, TaskError]
  | ["idle"];

export interface Harness {
  s: Scheduler;
  clock: FakeClock;
  events: Ev[];
  take(): Ev[];
  flush(): Promise<void>;
}

export function setup(options: Partial<SchedulerOptions> = {}): Harness {
  const clock = new FakeClock();
  const s = new Scheduler({ concurrency: 1, ...options, clock });
  const events: Ev[] = [];
  s.on("start", (id, attempt) => {
    events.push(["start", id, attempt]);
  });
  s.on("success", (id, value) => {
    events.push(["success", id, value]);
  });
  s.on("retry", (id, nextAttempt, delayMs, error) => {
    events.push(["retry", id, nextAttempt, delayMs, error]);
  });
  s.on("failure", (id, error) => {
    events.push(["failure", id, error]);
  });
  s.on("cancel", (id, error) => {
    events.push(["cancel", id, error]);
  });
  s.on("idle", () => {
    events.push(["idle"]);
  });
  return { s, clock, events, take: () => events.splice(0), flush: () => clock.flush() };
}

export function taskError(
  taskId: string,
  kind: TaskErrorKind,
  attempts: number,
  cause?: unknown,
): unknown {
  return expect.objectContaining({ taskId, kind, attempts, cause });
}

export interface Deferred<T> {
  promise: Promise<T>;
  resolve(value: T): void;
  reject(error: unknown): void;
}

export function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

export interface Controlled<T> {
  calls: TaskContext[];
  resolve(value: T, attempt?: number): void;
  reject(error: unknown, attempt?: number): void;
  ctx(attempt?: number): TaskContext;
}

export function controlled<T = unknown>(
  s: Scheduler,
  spec: Omit<TaskSpec<T>, "run">,
): Controlled<T> {
  const calls: TaskContext[] = [];
  const settles: Deferred<T>[] = [];
  s.add<T>({
    ...spec,
    run: (ctx) => {
      calls.push(ctx);
      const d = deferred<T>();
      settles.push(d);
      return d.promise;
    },
  });
  const pick = <U>(list: U[], attempt: number | undefined): U => {
    const item = list[(attempt ?? list.length) - 1];
    if (item === undefined) throw new Error(`attempt ${String(attempt ?? list.length)} not started`);
    return item;
  };
  return {
    calls,
    resolve: (value, attempt) => pick(settles, attempt).resolve(value),
    reject: (error, attempt) => pick(settles, attempt).reject(error),
    ctx: (attempt) => pick(calls, attempt),
  };
}

export type Outcome = { ok: unknown } | { reject: unknown } | { throw: unknown };

export function scripted(
  s: Scheduler,
  spec: Omit<TaskSpec<unknown>, "run">,
  outcomes: Outcome[],
): { calls: TaskContext[] } {
  const calls: TaskContext[] = [];
  s.add({
    ...spec,
    run: (ctx) => {
      calls.push(ctx);
      const o = outcomes[ctx.attempt - 1];
      if (!o) throw new Error(`unscripted attempt ${ctx.attempt}`);
      if ("throw" in o) throw o.throw;
      if ("reject" in o) return Promise.reject(o.reject);
      return Promise.resolve(o.ok);
    },
  });
  return { calls };
}

export function instant(
  s: Scheduler,
  id: string,
  value: unknown = id,
  extra: Omit<TaskSpec<unknown>, "run" | "id"> = {},
): { calls: TaskContext[] } {
  const calls: TaskContext[] = [];
  s.add({
    id,
    ...extra,
    run: (ctx) => {
      calls.push(ctx);
      return Promise.resolve(value);
    },
  });
  return { calls };
}

export function trapUnhandled(): { seen: unknown[]; stop(): void } {
  const seen: unknown[] = [];
  const handler = (reason: unknown) => {
    seen.push(reason);
  };
  process.on("unhandledRejection", handler);
  return { seen, stop: () => void process.off("unhandledRejection", handler) };
}

/**
 * Node reports unhandled rejections only after the microtask queue has drained for the current
 * macrotask, so detecting one needs a real macrotask turn.
 */
export function macrotask(): Promise<void> {
  return new Promise((resolve) => setImmediate(resolve));
}
