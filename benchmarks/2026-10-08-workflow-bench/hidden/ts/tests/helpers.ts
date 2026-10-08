// Shared helpers for the hidden taskflow acceptance suite.
// Everything here is deterministic: time only moves through FakeClock.advance / runNext.
import { expect } from "vitest";
import { Scheduler, TaskError } from "../src/index.js";
import type { Clock, TaskContext, TaskSpec } from "../src/index.js";

interface FakeTimer {
  id: number;
  due: number;
  seq: number;
  callback: () => void;
}

/** Drains microtasks and promise chains thoroughly (uses setImmediate, never timers). */
export async function flush(rounds = 20): Promise<void> {
  for (let i = 0; i < rounds; i++) {
    await new Promise<void>((r) => setImmediate(r));
  }
}

export class FakeClock implements Clock {
  private current: number;
  private timers = new Map<number, FakeTimer>();
  private nextId = 1;
  private nextSeq = 0;
  /** Total number of timers ever created through this clock. */
  created = 0;

  constructor(start = 1000) {
    this.current = start;
    // bound, so an implementation may call them detached from the clock object
    this.now = this.now.bind(this);
    this.setTimeout = this.setTimeout.bind(this);
    this.clearTimeout = this.clearTimeout.bind(this);
  }

  now(): number {
    return this.current;
  }

  setTimeout(callback: () => void, ms: number): unknown {
    const delay = Number.isFinite(ms) && ms > 0 ? ms : 0;
    const id = this.nextId++;
    this.timers.set(id, { id, due: this.current + delay, seq: this.nextSeq++, callback });
    this.created++;
    return { fakeTimerId: id };
  }

  clearTimeout(handle: unknown): void {
    if (handle && typeof handle === "object" && "fakeTimerId" in handle) {
      this.timers.delete((handle as { fakeTimerId: number }).fakeTimerId);
    }
  }

  /** Number of live (scheduled, not yet fired, not cleared) timers. */
  get pending(): number {
    return this.timers.size;
  }

  /** Due times (absolute) of live timers, ascending. */
  dueTimes(): number[] {
    return [...this.timers.values()].map((t) => t.due).sort((a, b) => a - b);
  }

  private earliest(limit: number): FakeTimer | undefined {
    let best: FakeTimer | undefined;
    for (const t of this.timers.values()) {
      if (t.due > limit) continue;
      if (!best || t.due < best.due || (t.due === best.due && t.seq < best.seq)) best = t;
    }
    return best;
  }

  /**
   * Advances time by `ms`, firing due timers in time order (FIFO for equal due times),
   * setting now() to each timer's due time and flushing microtasks after each fired timer.
   */
  async advance(ms: number): Promise<void> {
    const target = this.current + ms;
    for (;;) {
      const t = this.earliest(target);
      if (!t) break;
      this.timers.delete(t.id);
      this.current = Math.max(this.current, t.due);
      t.callback();
      await flush();
    }
    this.current = target;
    await flush();
  }

  /**
   * Synchronously fires the single earliest live timer (moving now() to its due time) without
   * flushing microtasks. Lets tests observe what a timer callback did synchronously.
   * Returns false if there is no live timer.
   */
  runNext(): boolean {
    const t = this.earliest(Number.POSITIVE_INFINITY);
    if (!t) return false;
    this.timers.delete(t.id);
    this.current = Math.max(this.current, t.due);
    t.callback();
    return true;
  }
}

export interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (reason: unknown) => void;
}

export function deferred<T = unknown>(): Deferred<T> {
  let resolve!: (value: T) => void;
  let reject!: (reason: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

/** Tracks a promise's settlement without leaving it unhandled. */
export interface Tracked<T> {
  readonly settled: boolean;
  readonly status: "pending" | "fulfilled" | "rejected";
  readonly value: T | undefined;
  readonly error: unknown;
}

export function track<T>(p: Promise<T>): Tracked<T> {
  const t = { settled: false, status: "pending" as Tracked<T>["status"], value: undefined as T | undefined, error: undefined as unknown };
  p.then(
    (v) => {
      t.settled = true;
      t.status = "fulfilled";
      t.value = v;
    },
    (e) => {
      t.settled = true;
      t.status = "rejected";
      t.error = e;
    },
  );
  return t;
}

export interface RunCall {
  id: string;
  attempt: number;
  ctx: TaskContext;
  d: Deferred<unknown>;
}

/**
 * Controllable run functions. `runs.fn(id)` returns a run function that records each invocation
 * (pushing `run:<id>:<attempt>` to the shared log) and returns a fresh deferred per attempt.
 */
export class Runs {
  calls: RunCall[] = [];
  constructor(readonly log: string[] = []) {}

  fn(id: string): (ctx: TaskContext) => Promise<unknown> {
    return (ctx) => {
      const d = deferred<unknown>();
      this.calls.push({ id, attempt: ctx.attempt, ctx, d });
      this.log.push(`run:${id}:${ctx.attempt}`);
      return d.promise;
    };
  }

  /** Spec helper: a task whose run is controlled by this Runs instance. */
  task(id: string, extra: Partial<Omit<TaskSpec, "id" | "run">> = {}): TaskSpec {
    return { id, run: this.fn(id), ...extra };
  }

  /** Ids in the order their run functions were invoked (one entry per attempt). */
  get order(): string[] {
    return this.calls.map((c) => c.id);
  }

  callsOf(id: string): RunCall[] {
    return this.calls.filter((c) => c.id === id);
  }

  count(id: string): number {
    return this.callsOf(id).length;
  }

  last(id: string): RunCall {
    const cs = this.callsOf(id);
    const c = cs[cs.length - 1];
    if (!c) throw new Error(`run for ${id} was never invoked`);
    return c;
  }

  resolve(id: string, value?: unknown): void {
    this.last(id).d.resolve(value);
  }

  reject(id: string, error: unknown = new Error(`${id} failed`)): void {
    this.last(id).d.reject(error);
  }
}

/**
 * Subscribes to every event and records compact strings into `log`:
 *   start:<id>:<attempt> | success:<id> | retry:<id>:<nextAttempt>:<delayMs>
 *   failure:<id> | cancel:<id> | idle
 * Raw arguments are kept in `raw`.
 */
export function recordEvents(s: Scheduler, log: string[] = []) {
  const raw: { event: string; args: unknown[] }[] = [];
  s.on("start", (id, attempt) => {
    raw.push({ event: "start", args: [id, attempt] });
    log.push(`start:${id}:${attempt}`);
  });
  s.on("success", (id, value) => {
    raw.push({ event: "success", args: [id, value] });
    log.push(`success:${id}`);
  });
  s.on("retry", (id, nextAttempt, delayMs, error) => {
    raw.push({ event: "retry", args: [id, nextAttempt, delayMs, error] });
    log.push(`retry:${id}:${nextAttempt}:${delayMs}`);
  });
  s.on("failure", (id, error) => {
    raw.push({ event: "failure", args: [id, error] });
    log.push(`failure:${id}`);
  });
  s.on("cancel", (id, error) => {
    raw.push({ event: "cancel", args: [id, error] });
    log.push(`cancel:${id}`);
  });
  s.on("idle", () => {
    raw.push({ event: "idle", args: [] });
    log.push("idle");
  });
  return { log, raw };
}

/** Takes and clears everything currently in a log array. */
export function drain(log: string[]): string[] {
  return log.splice(0, log.length);
}

/** Builds a scheduler on a fresh FakeClock. Events are only subscribed when asked for. */
export function make(concurrency = 1, opts: { events?: boolean } = {}) {
  const clock = new FakeClock();
  const s = new Scheduler({ concurrency, clock });
  const log: string[] = [];
  const runs = new Runs(log);
  const events = opts.events ? recordEvents(s, log) : undefined;
  return { s, clock, runs, log, events };
}

/** Asserts `e` is a TaskError and returns its checkable fields. */
export function errInfo(e: unknown): { taskId: string; kind: string; attempts: number } {
  expect(e).toBeInstanceOf(TaskError);
  const t = e as TaskError;
  return { taskId: t.taskId, kind: t.kind, attempts: t.attempts };
}

/** Event entries of a shared log, without the `run:` entries pushed by Runs. */
export function evs(log: string[]): string[] {
  return log.filter((l) => !l.startsWith("run:"));
}
