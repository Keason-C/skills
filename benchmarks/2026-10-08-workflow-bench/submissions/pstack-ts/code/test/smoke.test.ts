import { describe, expect, it } from "vitest";
import { CycleError, Scheduler, TaskError, type Clock, type TaskContext } from "../src/index.js";

class FakeClock implements Clock {
  private time = 0;
  private nextId = 1;
  private readonly timers = new Map<number, { at: number; callback: () => void }>();

  now(): number {
    return this.time;
  }

  setTimeout(callback: () => void, ms: number): unknown {
    const id = this.nextId++;
    this.timers.set(id, { at: this.time + ms, callback });
    return id;
  }

  clearTimeout(handle: unknown): void {
    if (typeof handle === "number") this.timers.delete(handle);
  }

  get pending(): number {
    return this.timers.size;
  }

  advance(ms: number): void {
    const target = this.time + ms;
    for (;;) {
      let due: [number, { at: number; callback: () => void }] | undefined;
      for (const entry of this.timers) {
        if (entry[1].at <= target && (due === undefined || entry[1].at < due[1].at)) due = entry;
      }
      if (due === undefined) break;
      this.timers.delete(due[0]);
      this.time = due[1].at;
      due[1].callback();
    }
    this.time = target;
  }
}

async function settle(): Promise<void> {
  for (let i = 0; i < 20; i++) await Promise.resolve();
}

interface Gate<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
  reject: (error: unknown) => void;
}

function gate<T = unknown>(): Gate<T> {
  let resolve: (value: T) => void = () => {};
  let reject: (error: unknown) => void = () => {};
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

async function rejectionOf(promise: Promise<unknown>): Promise<TaskError> {
  const error: unknown = await promise.then(
    () => undefined,
    (e: unknown) => e,
  );
  if (!(error instanceof TaskError)) throw new Error(`expected TaskError, got ${String(error)}`);
  return error;
}

function setup(concurrency = 1) {
  const clock = new FakeClock();
  const scheduler = new Scheduler({ concurrency, clock });
  const log: string[] = [];
  scheduler.on("start", (id, attempt) => log.push(`start ${id}#${attempt}`));
  scheduler.on("success", (id) => log.push(`success ${id}`));
  scheduler.on("retry", (id, next, delay) => log.push(`retry ${id}#${next} +${delay}`));
  scheduler.on("failure", (id, e) => log.push(`failure ${id} ${e.kind}`));
  scheduler.on("cancel", (id, e) => log.push(`cancel ${id} ${e.kind}`));
  scheduler.on("idle", () => log.push("idle"));
  return { clock, scheduler, log };
}

describe("taskflow smoke", () => {
  it("runs a task and resolves its result once started", async () => {
    const { scheduler, log } = setup();
    scheduler.add({ id: "a", run: async () => 42 });
    expect(scheduler.state("a")).toBe("queued");
    expect(log).toEqual([]);
    scheduler.start();
    expect(scheduler.state("a")).toBe("running");
    await expect(scheduler.result("a")).resolves.toBe(42);
    expect(scheduler.state("a")).toBe("succeeded");
    expect(log).toEqual(["start a#1", "success a", "idle"]);
  });

  it("passes dependency values and waits on forward references", async () => {
    const { scheduler } = setup(2);
    const seen: Array<Record<string, unknown>> = [];
    scheduler.start();
    scheduler.add({
      id: "sum",
      deps: ["x", "y"],
      run: async (ctx: TaskContext) => {
        seen.push(ctx.deps);
        return Number(ctx.deps.x) + Number(ctx.deps.y);
      },
    });
    expect(scheduler.state("sum")).toBe("waiting");
    scheduler.add({ id: "x", run: async () => 1 });
    scheduler.add({ id: "y", run: async () => 2 });
    await expect(scheduler.result("sum")).resolves.toBe(3);
    expect(seen).toEqual([{ x: 1, y: 2 }]);
  });

  it("never runs more than `concurrency` tasks at once", async () => {
    const { scheduler } = setup(2);
    const gates = { a: gate(), b: gate(), c: gate() };
    for (const id of ["a", "b", "c"] as const) scheduler.add({ id, run: () => gates[id].promise });
    scheduler.start();
    expect(["a", "b", "c"].map((id) => scheduler.state(id))).toEqual(["running", "running", "queued"]);
    gates.a.resolve("A");
    await settle();
    expect(scheduler.state("c")).toBe("running");
    gates.b.resolve("B");
    gates.c.resolve("C");
    await scheduler.onIdle();
  });

  it("starts ready tasks by priority, then readiness moment, then add order", async () => {
    const { scheduler, log } = setup(1);
    const blocker = gate();
    scheduler.add({ id: "low", run: async () => "low" });
    scheduler.add({ id: "hi1", priority: 5, run: async () => "hi1" });
    scheduler.add({ id: "hi2", priority: 5, run: async () => "hi2" });
    scheduler.add({ id: "first", priority: 9, run: () => blocker.promise });
    scheduler.start();
    blocker.resolve(undefined);
    await scheduler.onIdle();
    expect(log.filter((line) => line.startsWith("start"))).toEqual([
      "start first#1",
      "start hi1#1",
      "start hi2#1",
      "start low#1",
    ]);
  });

  it("starts dependents released in the same step in add order", async () => {
    const { scheduler, log } = setup(1);
    scheduler.add({ id: "root", run: async () => "root" });
    scheduler.add({ id: "b", deps: ["root"], run: async () => "b" });
    scheduler.add({ id: "c", deps: ["root"], run: async () => "c" });
    scheduler.add({ id: "d", deps: ["root"], run: async () => "d" });
    scheduler.start();
    await scheduler.onIdle();
    expect(log.filter((line) => line.startsWith("start"))).toEqual([
      "start root#1",
      "start b#1",
      "start c#1",
      "start d#1",
    ]);
  });

  it("retries with exponential backoff on the clock, then fails", async () => {
    const { clock, scheduler, log } = setup();
    const errors = [new Error("e1"), new Error("e2"), new Error("e3"), new Error("e4")];
    scheduler.add({
      id: "flaky",
      retries: 3,
      backoffMs: 100,
      run: async ({ attempt }) => {
        throw errors[attempt - 1];
      },
    });
    scheduler.start();
    for (const delay of [100, 200, 400]) {
      await settle();
      expect(scheduler.state("flaky")).toBe("retrying");
      expect(clock.pending).toBe(1);
      clock.advance(delay - 1);
      expect(scheduler.state("flaky")).toBe("retrying");
      clock.advance(1);
      expect(scheduler.state("flaky")).toBe("running");
    }
    await settle();

    expect(scheduler.state("flaky")).toBe("failed");
    const error = await rejectionOf(scheduler.result("flaky"));
    expect(error).toMatchObject({ taskId: "flaky", kind: "failed", attempts: 4, cause: errors[3] });
    expect(log).toEqual([
      "start flaky#1",
      "retry flaky#2 +100",
      "start flaky#2",
      "retry flaky#3 +200",
      "start flaky#3",
      "retry flaky#4 +400",
      "start flaky#4",
      "failure flaky failed",
      "idle",
    ]);
    expect(clock.pending).toBe(0);
  });

  it("times out an attempt: aborts its signal, frees its slot, ignores the late result", async () => {
    const { clock, scheduler, log } = setup(1);
    const slow = gate<string>();
    let signal: AbortSignal | undefined;
    scheduler.add({
      id: "slow",
      timeoutMs: 50,
      run: (ctx) => {
        signal = ctx.signal;
        return slow.promise;
      },
    });
    scheduler.add({ id: "next", timeoutMs: 1000, run: async () => "next" });
    scheduler.start();
    expect(clock.pending).toBe(1);

    clock.advance(50);
    expect(scheduler.state("slow")).toBe("failed");
    expect(signal?.aborted).toBe(true);
    expect(scheduler.state("next")).toBe("running");
    const error = await rejectionOf(scheduler.result("slow"));
    expect(error).toMatchObject({ kind: "timeout", attempts: 1, cause: undefined });
    expect(signal?.reason).toBe(error);

    slow.resolve("too late");
    await scheduler.onIdle();
    expect(scheduler.state("slow")).toBe("failed");
    expect(log.filter((line) => line.startsWith("success"))).toEqual(["success next"]);
    expect(clock.pending).toBe(0);
  });

  it("cancels a running task and cascades to dependents with kind and cause", async () => {
    const { scheduler, log } = setup(2);
    let signal: AbortSignal | undefined;
    scheduler.add({
      id: "root",
      run: (ctx) => {
        signal = ctx.signal;
        return new Promise(() => {});
      },
    });
    scheduler.add({ id: "mid", deps: ["root"], run: async () => "mid" });
    scheduler.add({ id: "leaf", deps: ["mid"], run: async () => "leaf" });
    scheduler.start();

    expect(scheduler.cancel("root", "stop")).toBe(true);
    expect(scheduler.cancel("root")).toBe(false);
    expect(scheduler.cancel("nope")).toBe(false);
    expect(log).toEqual(["start root#1", "cancel root cancelled", "cancel mid dependency", "cancel leaf dependency", "idle"]);

    const rootError = await rejectionOf(scheduler.result("root"));
    expect(rootError).toMatchObject({ kind: "cancelled", attempts: 1, cause: "stop" });
    expect(signal?.reason).toBe(rootError);
    const midError = await rejectionOf(scheduler.result("mid"));
    expect(midError).toMatchObject({ kind: "dependency", attempts: 0, cause: rootError });
    const leafError = await rejectionOf(scheduler.result("leaf"));
    expect(leafError.cause).toBe(midError);

    scheduler.add({ id: "late", deps: ["leaf"], run: async () => "late" });
    expect(scheduler.state("late")).toBe("cancelled");
    expect((await rejectionOf(scheduler.result("late"))).cause).toBe(leafError);
  });

  it("rejects a cycle with CycleError and leaves the scheduler unchanged", () => {
    const { scheduler } = setup();
    scheduler.add({ id: "A", deps: ["B"], run: async () => 1 });
    scheduler.add({ id: "B", deps: ["C"], run: async () => 1 });
    let thrown: unknown;
    try {
      scheduler.add({ id: "C", deps: ["A"], run: async () => 1 });
    } catch (error) {
      thrown = error;
    }
    expect(thrown).toBeInstanceOf(CycleError);
    expect(thrown instanceof CycleError ? thrown.cycle : undefined).toEqual(["C", "A", "B"]);
    expect(() => scheduler.state("C")).toThrow(Error);
    expect(() => scheduler.add({ id: "self", deps: ["self"], run: async () => 1 })).toThrow(
      expect.objectContaining({ cycle: ["self"] }),
    );
  });

  it("emits idle on busy-to-idle only and resolves onIdle", async () => {
    const { scheduler, log } = setup();
    scheduler.start();
    expect(log).toEqual([]);
    let resolved = false;
    void scheduler.onIdle().then(() => {
      resolved = true;
    });
    await settle();
    expect(resolved).toBe(true);

    const work = gate();
    scheduler.add({ id: "a", run: () => work.promise });
    resolved = false;
    void scheduler.onIdle().then(() => {
      resolved = true;
    });
    await settle();
    expect(resolved).toBe(false);
    work.resolve(1);
    await settle();
    expect(resolved).toBe(true);
    expect(log).toEqual(["start a#1", "success a", "idle"]);
  });
});
